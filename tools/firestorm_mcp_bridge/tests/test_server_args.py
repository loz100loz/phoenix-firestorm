from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from firestorm_mcp_bridge.server import parse_args


def encode_config(value: object) -> str:
    raw = json.dumps(value).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def test_launch_config_preserves_paths_and_attachment_names() -> None:
    config = encode_config(
        {
            "port": 18765,
            "session_file": r"C:\Path With Spaces\session.json",
            "capture_dir": r"C:\Path With Spaces\captures",
            "script_backup_dir": r"C:\Path With Spaces\script-backups",
            "allowed_attachment_names": ["MCP POC ROOT", "Second test HUD"],
            "workspace_roots": {"fake-game": r"C:\Path With Spaces\fake game"},
        }
    )

    args = parse_args(["--launch-config", config])

    assert args.port == 18765
    assert args.session_file == Path(r"C:\Path With Spaces\session.json")
    assert args.capture_dir == Path(r"C:\Path With Spaces\captures")
    assert args.script_backup_dir == Path(r"C:\Path With Spaces\script-backups")
    assert args.allowed_attachment_names == ["MCP POC ROOT", "Second test HUD"]
    assert args.workspace_roots == {
        "fake-game": Path(r"C:\Path With Spaces\fake game")
    }


def test_workspace_root_cli_uses_named_binding() -> None:
    args = parse_args(["--workspace-root", r"fake-game=C:\Fake Game"])

    assert args.workspace_roots == {"fake-game": Path(r"C:\Fake Game")}


def test_workspace_root_cli_rejects_malformed_binding() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--workspace-root", "missing-path"])

    with pytest.raises(SystemExit):
        parse_args(["--workspace-root", r"Bad Key=C:\Fake Game"])


def test_launch_config_rejects_unknown_fields() -> None:
    config = encode_config({"port": 18765, "unexpected": True})

    with pytest.raises(SystemExit):
        parse_args(["--launch-config", config])
