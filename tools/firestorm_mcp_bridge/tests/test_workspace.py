from __future__ import annotations

import json
from pathlib import Path

import pytest

from firestorm_mcp_bridge.workspace import WorkspaceError, WorkspaceWatcher, load_workspace


def write_workspace(root: Path, *, script_path: str = "devices/hud/main.lsl") -> Path:
    source = root / script_path
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("default { state_entry() {} }\n", encoding="utf-8")
    manifest = {
        "version": 1,
        "debounce_ms": 500,
        "devices": {
            "test-hud": {
                "target": {"kind": "worn_attachment", "name": "MCP POC ROOT"},
                "scripts": {
                    "main": {
                        "path": script_path,
                        "task_script_name": "New Script",
                        "sync_mode": "on_save",
                    }
                },
            }
        },
    }
    (root / "firestorm-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
    return source


def test_fake_example_workspace_is_valid():
    root = Path(__file__).parents[1] / "examples" / "fake_lsl_game"
    manifest = load_workspace(root)

    assert len(manifest.devices) == 3
    assert len(manifest.scripts) == 4
    assert sum(script.sync_mode == "on_save" for script in manifest.scripts) == 3
    assert sum(script.sync_mode == "manual" for script in manifest.scripts) == 1

    door_source = (root / "devices" / "training-door" / "controller.lsl").read_text(
        encoding="utf-8"
    )
    assert "is_open ?" not in door_source
    assert "if (is_open)" in door_source
    assert "else" in door_source


def test_watcher_emits_one_debounced_save(tmp_path):
    source = write_workspace(tmp_path)
    watcher = WorkspaceWatcher(load_workspace(tmp_path))

    source.write_text("default { state_entry() { llOwnerSay(\"saved\"); } }\n", encoding="utf-8")
    assert watcher.poll(now=1.0) == []
    assert watcher.poll(now=1.4) == []
    changes = watcher.poll(now=1.5)

    assert len(changes) == 1
    assert changes[0].device_key == "test-hud"
    assert changes[0].script_key == "main"
    assert changes[0].sync_mode == "on_save"
    assert changes[0].relative_path == "devices/hud/main.lsl"
    assert watcher.poll(now=2.0) == []


def test_workspace_rejects_path_escape(tmp_path):
    outside = tmp_path.parent / "outside.lsl"
    outside.write_text("default {}\n", encoding="utf-8")
    write_workspace(tmp_path, script_path="../outside.lsl")

    with pytest.raises(WorkspaceError, match="escapes the workspace root"):
        load_workspace(tmp_path)
