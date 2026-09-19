from __future__ import annotations

import asyncio
import base64
import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from firestorm_mcp_bridge.leap import read_framed_llsd, write_framed_llsd

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def unused_local_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_authenticated_http_bridge_end_to_end(tmp_path):
    port = unused_local_port()
    session_file = tmp_path / "session.json"
    capture_dir = tmp_path / "captures"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "firestorm_mcp_bridge",
            "--port",
            str(port),
            "--session-file",
            str(session_file),
            "--capture-dir",
            str(capture_dir),
            "--log-level",
            "WARNING",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None
    assert process.stdout is not None

    touch_seen = threading.Event()
    viewer_error: list[BaseException] = []
    script_source = ["default\n{\n    touch_start(integer total) { llOwnerSay(\"ready\"); }\n}\n"]

    def mock_viewer() -> None:
        try:
            write_framed_llsd(
                process.stdin,
                {
                    "pump": "mock-reply",
                    "data": {"command": "mock-command", "features": {}},
                },
                binary=True,
            )
            while True:
                packet = read_framed_llsd(process.stdout)
                pump = packet["pump"]
                data = packet["data"]
                op = data.get("op")
                response = None
                if pump == "mock-command" and op == "getAPIs":
                    response = {
                        "LLAgent": {"desc": "agent"},
                        "LLViewerWindow": {"desc": "window"},
                        "LLScriptAutomation": {"desc": "script automation"},
                    }
                elif pump == "LLAgent" and op == "getID":
                    response = {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}
                elif pump == "LLAgent" and op == "getAttachedObjectsList":
                    response = {
                        "attachments": [
                            {
                                "object_id": "11111111-1111-1111-1111-111111111111",
                                "inventory_item_id": "22222222-2222-2222-2222-222222222222",
                                "name": "MCP POC ROOT",
                                "attachment_point": "HUD Center",
                            }
                        ]
                    }
                elif pump == "LLAgent" and op == "requestTouch":
                    assert data["obj_uuid"] == "11111111-1111-1111-1111-111111111111"
                    touch_seen.set()
                elif pump == "LLViewerWindow" and op == "saveSnapshot":
                    Path(data["filename"]).write_bytes(PNG_1X1)
                    response = {"ok": True}
                elif pump == "LLScriptAutomation" and op == "getTaskInventory":
                    response = {
                        "items": [
                            {
                                "item_id": "33333333-3333-3333-3333-333333333333",
                                "name": "MCP POC Controller",
                                "description": "Disposable proof script",
                                "is_script": True,
                                "can_copy": True,
                                "can_modify": True,
                            }
                        ]
                    }
                elif pump == "LLScriptAutomation" and op == "getScriptSource":
                    response = {"source": script_source[0]}
                elif pump == "LLScriptAutomation" and op == "updateScriptSource":
                    script_source[0] = data["source"]
                    response = {
                        "compiled": True,
                        "installed": True,
                        "running": True,
                        "target": "mono",
                        "errors": [],
                    }
                else:
                    response = {"error": f"unexpected request {pump}/{op}"}

                if response is not None:
                    response["reqid"] = data["reqid"]
                    write_framed_llsd(
                        process.stdin,
                        {"pump": "mock-reply", "data": response},
                        binary=True,
                    )
        except BaseException as exc:
            if process.poll() is None:
                viewer_error.append(exc)

    viewer = threading.Thread(target=mock_viewer, daemon=True)
    viewer.start()

    deadline = time.monotonic() + 10
    while not session_file.exists() and time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read().decode("utf-8", errors="replace")
            raise AssertionError(f"bridge exited early: {stderr}")
        time.sleep(0.05)
    assert session_file.exists()
    descriptor = json.loads(session_file.read_text(encoding="utf-8"))

    unauthorized = httpx2.post(descriptor["endpoint"], json={}, timeout=5)
    assert unauthorized.status_code == 401

    async def exercise() -> None:
        http_client = httpx2.AsyncClient(
            headers={"Authorization": descriptor["authorization"]},
            timeout=httpx2.Timeout(10, read=30),
        )
        async with http_client:
            async with streamable_http_client(
                descriptor["endpoint"], http_client=http_client
            ) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    assert {tool.name for tool in listed.tools} == {
                        "viewer_status",
                        "discover_viewer_apis",
                        "list_attachments",
                        "viewer_context",
                        "inspect_selected_target",
                        "revalidate_selected_target",
                        "workspace_status",
                        "preview_workspace_push",
                        "apply_workspace_push",
                        "touch_test_hud",
                        "list_test_hud_scripts",
                        "prove_test_hud_script_round_trip",
                        "add_third_touch_color",
                        "preview_test_hud_script_edit",
                        "apply_test_hud_script_edit",
                        "capture_viewer",
                    }
                    status = await session.call_tool("viewer_status", {})
                    assert status.is_error is False
                    assert status.structured_content["logged_in"] is True
                    attachments = await session.call_tool("list_attachments", {})
                    assert attachments.structured_content["result"][0]["name"] == "MCP POC ROOT"
                    touched = await session.call_tool("touch_test_hud", {})
                    assert touched.structured_content["sent"] is True
                    proof = await session.call_tool("prove_test_hud_script_round_trip", {})
                    assert proof.structured_content["proved"] is True
                    screenshot = await session.call_tool(
                        "capture_viewer", {"width": 800, "height": 600}
                    )
                    assert [block.type for block in screenshot.content] == ["text", "image"]

    try:
        asyncio.run(exercise())
        assert touch_seen.wait(2)
        assert not viewer_error
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
    assert not session_file.exists()
