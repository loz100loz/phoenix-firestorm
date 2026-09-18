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
        self.script_source = "default\n{\n    touch_start(integer total) { llOwnerSay(\"ready\"); }\n}\n"
        self.script_updates: list[str] = []
        self.fail_next_compile = False

    def discover_apis(self, *, timeout: float = 15.0) -> dict[str, Any]:
        return {
            "LLAgent": {"desc": "agent"},
            "LLViewerWindow": {"desc": "window"},
            "LLScriptAutomation": {"desc": "script automation"},
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
        if pump == "LLScriptAutomation" and data["op"] == "getTaskInventory":
            return {
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
        if pump == "LLScriptAutomation" and data["op"] == "getScriptSource":
            return {"source": self.script_source}
        if pump == "LLScriptAutomation" and data["op"] == "updateScriptSource":
            self.script_source = data["source"]
            self.script_updates.append(data["source"])
            compiled = not self.fail_next_compile
            self.fail_next_compile = False
            return {
                "compiled": compiled,
                "installed": compiled,
                "running": True,
                "target": "mono",
                "errors": [],
            }
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


def test_script_round_trip_is_exactly_restored_and_backed_up(service):
    original = service.leap.script_source

    scripts = service.list_test_hud_scripts()
    assert scripts == [
        {
            "name": "MCP POC Controller",
            "description": "Disposable proof script",
            "can_copy": True,
            "can_modify": True,
        }
    ]

    result = service.prove_test_hud_script_round_trip()

    assert result["proved"] is True
    assert result["marker_verified"] is True
    assert result["original_restored"] is True
    assert service.leap.script_source == original
    assert len(service.leap.script_updates) == 2
    assert "Firestorm MCP reversible proof" in service.leap.script_updates[0]
    assert service.leap.script_updates[1] == original
    assert Path(result["backup_path"]).read_text(encoding="utf-8") == original


def test_script_round_trip_restores_after_marked_compile_failure(service):
    original = service.leap.script_source
    service.leap.fail_next_compile = True

    with pytest.raises(LeapError, match="exact original source was restored"):
        service.prove_test_hud_script_round_trip()

    assert service.leap.script_source == original
    assert len(service.leap.script_updates) == 2
    assert service.leap.script_updates[1] == original


TWO_COLOR_TOUCH_SCRIPT = """integer toggled;

default
{
    touch_start(integer total_number)
    {
        toggled = !toggled;

        if (toggled)
            llSetColor(<1.0, 0.0, 0.0>, ALL_SIDES);
        else
            llSetColor(<0.0, 1.0, 0.0>, ALL_SIDES);

        llOwnerSay(\"Color changed\");
    }
}
"""


def test_add_third_touch_color_compiles_and_persists(service):
    service.leap.script_source = TWO_COLOR_TOUCH_SCRIPT
    original = service.leap.script_source

    result = service.add_third_touch_color()

    assert result["updated"] is True
    assert result["compiled"] is True
    assert result["source_verified"] is True
    assert result["third_color"] == {"name": "blue", "rgb": [0.0, 0.0, 1.0]}
    assert service.leap.script_source != original
    assert service.leap.script_source.count("llSetColor") == 3
    assert "llSetColor(<0.0, 0.0, 1.0>, ALL_SIDES);" in service.leap.script_source
    assert "toggled = (toggled + 1) % 3;" in service.leap.script_source
    assert len(service.leap.script_updates) == 1
    assert Path(result["backup_path"]).read_text(encoding="utf-8") == original


def test_add_third_touch_color_restores_after_compile_failure(service):
    service.leap.script_source = TWO_COLOR_TOUCH_SCRIPT
    original = service.leap.script_source
    service.leap.fail_next_compile = True

    with pytest.raises(LeapError, match="exact original source was restored"):
        service.add_third_touch_color()

    assert service.leap.script_source == original
    assert len(service.leap.script_updates) == 2
    assert service.leap.script_updates[1] == original
