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
            "allowed_attachment_names": ["MCP POC ROOT", "Second test HUD"],
        }
    )

    args = parse_args(["--launch-config", config])

    assert args.port == 18765
    assert args.session_file == Path(r"C:\Path With Spaces\session.json")
    assert args.capture_dir == Path(r"C:\Path With Spaces\captures")
    assert args.allowed_attachment_names == ["MCP POC ROOT", "Second test HUD"]


def test_launch_config_rejects_unknown_fields() -> None:
    config = encode_config({"port": 18765, "unexpected": True})

    with pytest.raises(SystemExit):
        parse_args(["--launch-config", config])
