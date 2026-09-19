from __future__ import annotations

import os
import threading
import uuid

from firestorm_mcp_bridge.leap import (
    LeapConnection,
    read_framed_llsd,
    write_framed_llsd,
)


def make_pipe_pair():
    viewer_to_bridge_read, viewer_to_bridge_write = os.pipe()
    bridge_to_viewer_read, bridge_to_viewer_write = os.pipe()
    return (
        os.fdopen(viewer_to_bridge_read, "rb", buffering=0),
        os.fdopen(bridge_to_viewer_write, "wb", buffering=0),
        os.fdopen(bridge_to_viewer_read, "rb", buffering=0),
        os.fdopen(viewer_to_bridge_write, "wb", buffering=0),
    )


def test_framed_llsd_round_trip_binary_and_notation(tmp_path):
    packet = {
        "pump": "reply-pump",
        "data": {"uuid": uuid.UUID("11111111-1111-1111-1111-111111111111")},
    }
    for binary in (False, True):
        path = tmp_path / f"packet-{binary}.llsd"
        with path.open("wb") as output:
            write_framed_llsd(output, packet, binary=binary)
        with path.open("rb") as input_stream:
            result = read_framed_llsd(input_stream)
        assert result["pump"] == "reply-pump"
        assert str(result["data"]["uuid"]) == "11111111-1111-1111-1111-111111111111"


def test_connection_correlates_request_and_sends_notification():
    bridge_input, bridge_output, viewer_input, viewer_output = make_pipe_pair()
    notification_seen = threading.Event()

    def viewer() -> None:
        write_framed_llsd(
            viewer_output,
            {
                "pump": "reply-pump",
                "data": {"command": "command-pump", "features": {}},
            },
            binary=True,
        )
        request = read_framed_llsd(viewer_input)
        assert request["pump"] == "command-pump"
        assert request["data"]["op"] == "getAPIs"
        write_framed_llsd(
            viewer_output,
            {
                "pump": "reply-pump",
                "data": {
                    "reqid": request["data"]["reqid"],
                    "LLAgent": {"desc": "agent"},
                },
            },
            binary=True,
        )
        notification = read_framed_llsd(viewer_input)
        assert notification == {
            "pump": "LLAgent",
            "data": {"op": "requestTouch", "obj_uuid": "target", "face": 0},
        }
        notification_seen.set()
        viewer_output.close()

    thread = threading.Thread(target=viewer, daemon=True)
    thread.start()
    leap = LeapConnection.accept(bridge_input, bridge_output)

    assert leap.discover_apis() == {"LLAgent": {"desc": "agent"}}
    leap.notify(
        "LLAgent",
        {"op": "requestTouch", "obj_uuid": "target", "face": 0},
    )
    assert notification_seen.wait(2)
    thread.join(timeout=2)

