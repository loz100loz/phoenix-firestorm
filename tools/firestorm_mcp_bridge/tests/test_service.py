from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from firestorm_mcp_bridge.leap import LeapError
from firestorm_mcp_bridge.service import EDIT_CONFIRMATION, Stage0Service

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
        self.avatar_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        self.region_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        self.selected_root_id = "44444444-4444-4444-4444-444444444444"
        self.selected_object_id = self.selected_root_id
        self.selected_owner_id = self.avatar_id
        self.selected_group_owned = False
        self.selected_group_id = "00000000-0000-0000-0000-000000000000"
        self.selected_can_modify = True
        self.selected_name = "Disposable Selected Device"
        self.selection_object_count = 1
        self.selection_root_count = 1
        self.additional_link_ids: list[str] = []
        self.script_name = "MCP POC Controller"
        self.script_present = True
        self.duplicate_script_name = False
        self.duplicate_script_item_id = False
        self.script_can_copy = True
        self.script_can_modify = True
        self.script_source_requests = 0
        self.change_selection_on_source_read = False
        self.selected_is_attachment = False
        self.inspect_selection_error: str | None = None
        self.task_inventory_requests = 0

    def discover_apis(self, *, timeout: float = 15.0) -> dict[str, Any]:
        return {
            "LLAgent": {"desc": "agent"},
            "LLViewerWindow": {"desc": "window"},
            "LLScriptAutomation": {"desc": "script automation"},
        }

    def request(self, pump: str, data: dict[str, Any], *, timeout: float = 15.0):
        if pump == "LLAgent" and data["op"] == "getID":
            return {"id": self.avatar_id}
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
            self.task_inventory_requests += 1
            if not self.script_present:
                return {"items": []}
            items = [
                {
                    "item_id": "33333333-3333-3333-3333-333333333333",
                    "name": self.script_name,
                    "description": "Disposable proof script",
                    "is_script": True,
                    "can_copy": self.script_can_copy,
                    "can_modify": self.script_can_modify,
                }
            ]
            if self.duplicate_script_name:
                items.append(
                    {
                        "item_id": (
                            "33333333-3333-3333-3333-333333333333"
                            if self.duplicate_script_item_id
                            else "77777777-7777-7777-7777-777777777777"
                        ),
                        "name": self.script_name,
                        "description": "Duplicate synthetic script",
                        "is_script": True,
                        "can_copy": True,
                        "can_modify": True,
                    }
                )
            return {
                "items": items
            }
        if pump == "LLScriptAutomation" and data["op"] == "getViewerContext":
            return {
                "avatar_id": self.avatar_id,
                "avatar_name": "ninja.nova",
                "grid_id": "agni",
                "grid_label": "Second Life",
                "logged_in": True,
                "region_id": self.region_id,
                "region_name": "Synthetic Region",
                "agent_position_region": [128.0, 128.0, 25.0],
                "agent_position_global": [1000.0, 1000.0, 25.0],
            }
        if pump == "LLScriptAutomation" and data["op"] == "inspectSelection":
            if self.inspect_selection_error:
                raise LeapError(self.inspect_selection_error)
            return {
                "avatar_id": self.avatar_id,
                "avatar_name": "ninja.nova",
                "grid_id": "agni",
                "grid_label": "Second Life",
                "logged_in": True,
                "region_id": self.region_id,
                "region_name": "Synthetic Region",
                "selection_object_count": self.selection_object_count,
                "selection_root_count": self.selection_root_count,
                "root_id": self.selected_root_id,
                "object_id": self.selected_object_id,
                "object_name": self.selected_name,
                "object_description": "Synthetic selected-object fixture",
                "root_name": self.selected_name,
                "root_description": "Synthetic selected-object fixture",
                "is_root": self.selected_object_id == self.selected_root_id,
                "is_attachment": self.selected_is_attachment,
                "attachment_item_id": "00000000-0000-0000-0000-000000000000",
                "link_number": 0 if not self.additional_link_ids else 1,
                "link_count": 1 + len(self.additional_link_ids),
                "face_count": 6,
                "position_region": [130.0, 128.0, 25.0],
                "position_global": [1002.0, 1000.0, 25.0],
                "root_position_region": [130.0, 128.0, 25.0],
                "owner_id": self.selected_owner_id,
                "creator_id": self.avatar_id,
                "group_id": self.selected_group_id,
                "group_owned": self.selected_group_owned,
                "owner_is_logged_in_avatar": (
                    not self.selected_group_owned
                    and self.selected_owner_id == self.avatar_id
                ),
                "can_modify": self.selected_can_modify,
                "can_copy": True,
                "can_move": True,
                "can_transfer": True,
                "properties_complete": True,
                "link_ids": [self.selected_root_id, *self.additional_link_ids],
            }
        if pump == "LLScriptAutomation" and data["op"] == "getScriptSource":
            self.script_source_requests += 1
            if self.change_selection_on_source_read:
                self.selected_name = "Changed During Source Read"
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


def make_workspace_service(
    tmp_path: Path,
    *,
    local_source: str | None = None,
    remote_source: str | None = None,
    target_kind: str = "selected_object",
    target_name: str = "Disposable Selected Device",
) -> tuple[Stage0Service, Path]:
    leap = FakeLeap()
    if remote_source is not None:
        leap.script_source = remote_source
    if local_source is None:
        local_source = leap.script_source
    root = tmp_path / "workspace"
    source = root / "devices" / "fixture" / "controller.lsl"
    source.parent.mkdir(parents=True)
    source.write_text(local_source, encoding="utf-8")
    manifest = {
        "version": 1,
        "devices": {
            "fixture": {
                "target": {"kind": target_kind, "name": target_name},
                "scripts": {
                    "controller": {
                        "path": "devices/fixture/controller.lsl",
                        "task_script_name": "MCP POC Controller",
                        "sync_mode": "manual",
                    }
                },
            }
        },
    }
    (root / "firestorm-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
    return (
        Stage0Service(
            leap,
            tmp_path / "captures",
            ("MCP POC ROOT",),
            touch_cooldown=0,
            workspace_roots={"fixture-workspace": root},
        ),
        source,
    )


def test_status_and_attachments(service):
    status = service.viewer_status()
    assert status["logged_in"] is True
    assert status["required_stage0"] == {"LLAgent": True, "LLViewerWindow": True}
    attachments = service.list_attachments()
    assert attachments[0]["name"] == "MCP POC ROOT"


def test_viewer_context_is_bound_to_one_bridge_session(service):
    context = service.viewer_context()

    assert context["logged_in"] is True
    assert context["avatar_name"] == "ninja.nova"
    assert context["region_name"] == "Synthetic Region"
    assert context["session_fingerprint"] == service.session_fingerprint
    assert "token" not in context


def test_inspect_and_revalidate_selected_self_owned_target(service):
    result = service.inspect_selected_target()

    assert result["eligible_for_future_mutation"] is True
    assert result["blocked_reason"] is None
    assert len(result["target_handle"]) == 32
    assert result["target"]["owner_relation"] == "self"
    assert result["target"]["object_name"] == "Disposable Selected Device"
    assert result["script_inventory"]["count"] == 1
    assert result["script_inventory"]["source_returned"] is False
    serialized = json.dumps(result, sort_keys=True)
    assert "33333333-3333-3333-3333-333333333333" not in serialized
    assert "44444444-4444-4444-4444-444444444444" not in serialized

    revalidated = service.revalidate_selected_target(result["target_handle"])
    assert revalidated["valid"] is True
    assert revalidated["target"]["identity_sha256"] == result["target"]["identity_sha256"]


def test_selected_other_owner_is_reported_but_not_issued_a_handle(service):
    service.leap.selected_owner_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"

    result = service.inspect_selected_target()

    assert result["eligible_for_future_mutation"] is False
    assert result["target_handle"] is None
    assert result["target"]["owner_relation"] == "other"
    assert "not owned" in result["blocked_reason"]
    assert result["script_inventory"]["count"] == 0
    assert service.leap.task_inventory_requests == 0


def test_selected_group_owned_target_is_blocked_by_default(service):
    service.leap.selected_owner_id = "00000000-0000-0000-0000-000000000000"
    service.leap.selected_group_owned = True
    service.leap.selected_group_id = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"

    result = service.inspect_selected_target()

    assert result["eligible_for_future_mutation"] is False
    assert result["target_handle"] is None
    assert result["target"]["owner_relation"] == "group"
    assert "Group-owned" in result["blocked_reason"]


def test_target_handle_is_invalidated_when_selection_changes(service):
    result = service.inspect_selected_target()
    service.leap.selected_root_id = "55555555-5555-5555-5555-555555555555"
    service.leap.selected_object_id = service.leap.selected_root_id

    with pytest.raises(LeapError, match="selected target changed"):
        service.revalidate_selected_target(result["target_handle"])
    with pytest.raises(LeapError, match="unknown to this viewer session"):
        service.revalidate_selected_target(result["target_handle"])


def test_target_handle_is_invalidated_when_modify_permission_changes(service):
    result = service.inspect_selected_target()
    service.leap.selected_can_modify = False

    with pytest.raises(LeapError, match="no longer eligible"):
        service.revalidate_selected_target(result["target_handle"])
    with pytest.raises(LeapError, match="unknown to this viewer session"):
        service.revalidate_selected_target(result["target_handle"])


def test_target_handle_is_invalidated_when_avatar_changes(service):
    result = service.inspect_selected_target()
    service.leap.avatar_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    service.leap.selected_owner_id = service.leap.avatar_id

    with pytest.raises(LeapError, match="selected target changed"):
        service.revalidate_selected_target(result["target_handle"])


def test_target_handle_is_invalidated_when_region_changes(service):
    result = service.inspect_selected_target()
    service.leap.region_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"

    with pytest.raises(LeapError, match="selected target changed"):
        service.revalidate_selected_target(result["target_handle"])


def test_target_handle_is_invalidated_when_script_inventory_changes(service):
    result = service.inspect_selected_target()
    service.leap.script_name = "Renamed Controller"

    with pytest.raises(LeapError, match="selected target changed"):
        service.revalidate_selected_target(result["target_handle"])


def test_failed_live_reinspection_invalidates_target_handle(service):
    result = service.inspect_selected_target()
    service.leap.inspect_selection_error = "Select exactly one linkset"

    with pytest.raises(LeapError, match="Select exactly one linkset"):
        service.revalidate_selected_target(result["target_handle"])

    service.leap.inspect_selection_error = None
    with pytest.raises(LeapError, match="unknown to this viewer session"):
        service.revalidate_selected_target(result["target_handle"])


def test_inconsistent_ownership_response_is_rejected(service):
    original_request = service.leap.request

    def inconsistent_request(pump, data, *, timeout=15.0):
        response = original_request(pump, data, timeout=timeout)
        if pump == "LLScriptAutomation" and data["op"] == "inspectSelection":
            response["owner_is_logged_in_avatar"] = False
        return response

    service.leap.request = inconsistent_request

    with pytest.raises(LeapError, match="inconsistent selected-object ownership"):
        service.inspect_selected_target()


def test_multiple_individually_selected_prims_are_rejected_at_service_boundary(service):
    service.leap.selection_object_count = 2
    service.leap.selection_root_count = 0
    service.leap.additional_link_ids = [
        "55555555-5555-5555-5555-555555555555"
    ]

    with pytest.raises(LeapError, match="Select exactly one"):
        service.inspect_selected_target()


def test_one_whole_linkset_with_multiple_nodes_is_accepted(service):
    service.leap.selection_object_count = 3
    service.leap.selection_root_count = 1
    service.leap.additional_link_ids = [
        "55555555-5555-5555-5555-555555555555",
        "66666666-6666-6666-6666-666666666666",
    ]

    result = service.inspect_selected_target()

    assert result["eligible_for_future_mutation"] is True
    assert result["target"]["selection_object_count"] == 3
    assert result["target"]["selection_root_count"] == 1


def test_target_handle_cannot_cross_viewer_sessions(tmp_path):
    first = Stage0Service(
        FakeLeap(),
        tmp_path / "first-captures",
        ("MCP POC ROOT",),
        touch_cooldown=0,
    )
    second = Stage0Service(
        FakeLeap(),
        tmp_path / "second-captures",
        ("MCP POC ROOT",),
        touch_cooldown=0,
    )
    handle = first.inspect_selected_target()["target_handle"]

    with pytest.raises(LeapError, match="unknown to this viewer session"):
        second.revalidate_selected_target(handle)


def test_target_handle_expires_without_extending_its_lifetime(tmp_path):
    now = [100.0]
    service = Stage0Service(
        FakeLeap(),
        tmp_path / "captures",
        ("MCP POC ROOT",),
        touch_cooldown=0,
        target_handle_ttl=10.0,
        monotonic_clock=lambda: now[0],
    )
    handle = service.inspect_selected_target()["target_handle"]
    now[0] = 110.0

    with pytest.raises(LeapError, match="target handle has expired"):
        service.revalidate_selected_target(handle)


def test_workspace_status_reports_unchanged_without_returning_source_or_ids(tmp_path):
    service, _ = make_workspace_service(tmp_path)
    handle = service.inspect_selected_target()["target_handle"]

    result = service.workspace_status(
        "fixture-workspace", "fixture", "controller", handle
    )

    assert result["status"] == "unchanged"
    assert result["baseline_known"] is True
    assert result["source_returned"] is False
    assert result["writes_performed"] is False
    assert result["local"]["sha256"] == result["remote"]["sha256"]
    assert service.viewer_status()["workspace_keys"] == ["fixture-workspace"]
    serialized = json.dumps(result, sort_keys=True)
    assert "llOwnerSay" not in serialized
    assert "33333333-3333-3333-3333-333333333333" not in serialized
    assert "44444444-4444-4444-4444-444444444444" not in serialized
    assert service.leap.script_updates == []


def test_workspace_status_classifies_local_remote_and_both_changed(tmp_path):
    service, source = make_workspace_service(tmp_path)
    handle = service.inspect_selected_target()["target_handle"]
    assert service.workspace_status(
        "fixture-workspace", "fixture", "controller", handle
    )["status"] == "unchanged"

    source.write_text("default { state_entry() { llOwnerSay(\"local\"); } }\n", encoding="utf-8")
    assert service.workspace_status(
        "fixture-workspace", "fixture", "controller", handle
    )["status"] == "local_ahead"

    source.write_text(service.leap.script_source, encoding="utf-8")
    service.leap.script_source = "default { state_entry() { llOwnerSay(\"remote\"); } }\n"
    assert service.workspace_status(
        "fixture-workspace", "fixture", "controller", handle
    )["status"] == "remote_ahead"

    source.write_text("default { state_entry() { llOwnerSay(\"local again\"); } }\n", encoding="utf-8")
    assert service.workspace_status(
        "fixture-workspace", "fixture", "controller", handle
    )["status"] == "conflict"


def test_workspace_status_different_without_baseline_is_conflict(tmp_path):
    service, _ = make_workspace_service(
        tmp_path,
        local_source="default { state_entry() { llOwnerSay(\"local\"); } }\n",
        remote_source="default { state_entry() { llOwnerSay(\"remote\"); } }\n",
    )
    handle = service.inspect_selected_target()["target_handle"]

    result = service.workspace_status(
        "fixture-workspace", "fixture", "controller", handle
    )

    assert result["status"] == "conflict"
    assert result["baseline_known"] is False
    assert result["baseline_sha256"] is None


def test_workspace_status_reports_missing_and_blocks_duplicates_or_permissions(tmp_path):
    service, _ = make_workspace_service(tmp_path)
    service.leap.script_present = False
    handle = service.inspect_selected_target()["target_handle"]
    missing = service.workspace_status(
        "fixture-workspace", "fixture", "controller", handle
    )
    assert missing["status"] == "missing"
    assert service.leap.script_source_requests == 0

    duplicate_service, _ = make_workspace_service(tmp_path / "duplicate")
    duplicate_service.leap.duplicate_script_name = True
    duplicate_handle = duplicate_service.inspect_selected_target()["target_handle"]
    duplicate = duplicate_service.workspace_status(
        "fixture-workspace", "fixture", "controller", duplicate_handle
    )
    assert duplicate["status"] == "blocked"
    assert "More than one" in duplicate["reason"]
    assert duplicate_service.leap.script_source_requests == 0

    denied_service, _ = make_workspace_service(tmp_path / "denied")
    denied_service.leap.script_can_copy = False
    denied_handle = denied_service.inspect_selected_target()["target_handle"]
    denied = denied_service.workspace_status(
        "fixture-workspace", "fixture", "controller", denied_handle
    )
    assert denied["status"] == "blocked"
    assert "copyable and modifiable" in denied["reason"]
    assert denied_service.leap.script_source_requests == 0


def test_workspace_status_blocks_target_mapping_mismatch_before_source_read(tmp_path):
    service, _ = make_workspace_service(tmp_path, target_name="Some Other Device")
    handle = service.inspect_selected_target()["target_handle"]

    result = service.workspace_status(
        "fixture-workspace", "fixture", "controller", handle
    )

    assert result["status"] == "blocked"
    assert "name does not match" in result["reason"]
    assert service.leap.script_source_requests == 0

    kind_service, _ = make_workspace_service(
        tmp_path / "kind", target_kind="worn_attachment"
    )
    kind_handle = kind_service.inspect_selected_target()["target_handle"]
    kind_result = kind_service.workspace_status(
        "fixture-workspace", "fixture", "controller", kind_handle
    )
    assert kind_result["status"] == "blocked"
    assert "kind does not match" in kind_result["reason"]
    assert kind_service.leap.script_source_requests == 0


def test_inspection_rejects_duplicate_script_item_identity(service):
    service.leap.duplicate_script_name = True
    service.leap.duplicate_script_item_id = True

    with pytest.raises(LeapError, match="duplicate selected script item UUIDs"):
        service.inspect_selected_target()


def test_workspace_status_rejects_unknown_workspace_and_stale_handle(tmp_path):
    service, _ = make_workspace_service(tmp_path)
    handle = service.inspect_selected_target()["target_handle"]
    with pytest.raises(LeapError, match="workspace key is not allowlisted"):
        service.workspace_status("unknown", "fixture", "controller", handle)

    service.leap.selected_name = "Changed Selected Device"
    with pytest.raises(LeapError, match="selected target changed"):
        service.workspace_status(
            "fixture-workspace", "fixture", "controller", handle
        )
    assert service.leap.script_source_requests == 0


def test_workspace_status_revalidates_again_after_remote_source_read(tmp_path):
    service, _ = make_workspace_service(tmp_path)
    handle = service.inspect_selected_target()["target_handle"]
    service.leap.change_selection_on_source_read = True

    with pytest.raises(LeapError, match="selected target changed"):
        service.workspace_status(
            "fixture-workspace", "fixture", "controller", handle
        )

    assert service.leap.script_source_requests == 1
    with pytest.raises(LeapError, match="unknown to this viewer session"):
        service.revalidate_selected_target(handle)


def test_workspace_source_reader_rechecks_allowlisted_containment(tmp_path):
    service, _ = make_workspace_service(tmp_path)
    outside = tmp_path / "outside.lsl"
    outside.write_text("default {}\n", encoding="utf-8")

    with pytest.raises(LeapError, match="escaped its allowlisted workspace"):
        service._read_workspace_source(outside, tmp_path / "workspace")


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


def test_preview_and_apply_script_edit(service):
    original = service.leap.script_source
    preview = service.preview_test_hud_script_edit(
        operation="append",
        find_text="",
        replacement_text="// synthetic edit-plan test\n",
    )

    assert preview["planned"] is True
    assert preview["source_returned"] is False
    assert preview["separator_added"] is False
    assert Path(preview["diff_path"]).is_file()
    plan_path = Path(preview["diff_path"]).with_suffix(".json")
    assert plan_path.is_file()

    result = service.apply_test_hud_script_edit(
        plan_id=preview["plan_id"],
        confirmation=EDIT_CONFIRMATION,
    )

    assert result["applied"] is True
    assert result["compiled"] is True
    assert result["source_verified"] is True
    assert result["plan_consumed"] is True
    assert service.leap.script_source.endswith("// synthetic edit-plan test\n")
    assert Path(result["backup_path"]).read_text(encoding="utf-8") == original
    assert not plan_path.exists()
    assert not Path(preview["diff_path"]).exists()


def test_apply_script_edit_rejects_stale_plan(service):
    preview = service.preview_test_hud_script_edit(
        operation="append",
        find_text="",
        replacement_text="// stale plan test\n",
    )
    service.leap.script_source += "// changed elsewhere\n"

    with pytest.raises(LeapError, match="stale plan was not applied"):
        service.apply_test_hud_script_edit(
            plan_id=preview["plan_id"],
            confirmation=EDIT_CONFIRMATION,
        )

    assert service.leap.script_updates == []
    assert not Path(preview["diff_path"]).exists()
    assert not Path(preview["diff_path"]).with_suffix(".json").exists()


def test_append_reports_separator_for_source_without_final_newline(service):
    service.leap.script_source = "default { state_entry() {} }"
    preview = service.preview_test_hud_script_edit(
        operation="append",
        find_text="",
        replacement_text="// appended\n",
    )

    assert preview["separator_added"] is True
    assert preview["candidate_bytes"] == preview["original_bytes"] + len("\n// appended\n")


def test_apply_script_edit_restores_after_compile_failure(service):
    original = service.leap.script_source
    preview = service.preview_test_hud_script_edit(
        operation="replace",
        find_text="ready",
        replacement_text="updated",
    )
    service.leap.fail_next_compile = True

    with pytest.raises(LeapError, match="exact original source was restored"):
        service.apply_test_hud_script_edit(
            plan_id=preview["plan_id"],
            confirmation=EDIT_CONFIRMATION,
        )

    assert service.leap.script_source == original
    assert len(service.leap.script_updates) == 2
    assert service.leap.script_updates[1] == original
