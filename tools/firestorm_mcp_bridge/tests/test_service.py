from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest

from firestorm_mcp_bridge.leap import LeapError
from firestorm_mcp_bridge.service import Stage0Service

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class FakeLeap:
    connected = True
    features: dict[str, Any] = {}

    def __init__(self) -> None:
        self.notifications: list[tuple[str, dict[str, Any]]] = []

    def discover_apis(self, *, timeout: float = 15.0) -> dict[str, Any]:
        return {
            "LLAgent": {"desc": "agent"},
            "LLViewerWindow": {"desc": "window"},
        }

    def request(self, pump: str, data: dict[str, Any], *, timeout: float = 15.0):
        if pump == "LLAgent" and data["op"] == "getID":
            return {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}
        if pump == "LLAgent" and data["op"] == "getAttachedObjectsList":
            return {
                "attachments": [
                    {
                        "object_id": "11111111-1111-1111-1111-111111111111",
                        "inventory_item_id": "22222222-2222-2222-2222-222222222222",
                        "name": "MCP POC ROOT",
                        "attachment_point": "HUD Center",
                    }
                ]
            }
        if pump == "LLViewerWindow" and data["op"] == "saveSnapshot":
            Path(data["filename"]).write_bytes(PNG_1X1)
            return {"ok": True}
        raise AssertionError((pump, data))

    def notify(self, pump: str, data: dict[str, Any]) -> None:
        self.notifications.append((pump, data))


@pytest.fixture
def service(tmp_path):
    return Stage0Service(
        FakeLeap(),
        tmp_path / "captures",
        ("MCP POC ROOT",),
        touch_cooldown=0,
    )


def test_status_and_attachments(service):
    status = service.viewer_status()
    assert status["logged_in"] is True
    assert status["required_stage0"] == {"LLAgent": True, "LLViewerWindow": True}
    attachments = service.list_attachments()
    assert attachments[0]["name"] == "MCP POC ROOT"


def test_touch_is_limited_to_worn_allowlisted_attachment(service):
    result = service.touch_test_hud()
    assert result["sent"] is True
    assert result["confirmed"] is False
    assert service.leap.notifications == [
        (
            "LLAgent",
            {
                "op": "requestTouch",
                "obj_uuid": "11111111-1111-1111-1111-111111111111",
                "face": 0,
            },
        )
    ]

    with pytest.raises(LeapError, match="not allowlisted"):
        service.touch_test_hud(attachment_name="Production HUD")


def test_capture_creates_nonempty_png(service):
    snapshot = service.capture_viewer(width=800, height=600)
    assert snapshot.path.read_bytes() == PNG_1X1
    assert snapshot.metadata["show_ui"] is False
    assert snapshot.metadata["show_hud"] is True

