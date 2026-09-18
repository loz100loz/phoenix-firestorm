# Firestorm MCP Stage 0 bridge

This directory contains the deliberately narrow proof of concept agreed for Stage 0. It does not patch Firestorm or expose script editing.

The bridge is launched by Firestorm through `--leap`. Its standard input and output are reserved for Firestorm's length-prefixed LLSD protocol. At the same time, it exposes authenticated MCP Streamable HTTP on `127.0.0.1`.

## Exposed MCP tools

- `viewer_status`
- `discover_viewer_apis`
- `list_attachments`
- `touch_test_hud`
- `capture_viewer`

`touch_test_hud` cannot accept an arbitrary object UUID. It resolves an exact allowlisted name against the avatar's currently worn attachments immediately before sending Firestorm's existing `requestTouch` operation. The default allowlist contains only `MCP POC ROOT`.

`capture_viewer` hides the viewer UI and shows HUDs by default. Screenshots stay in the current user's local application-data directory and are returned as MCP image content.

## Development setup

From this directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m pytest
```

## Launch from Firestorm

Firestorm must own the bridge process, so start the viewer with a `--leap` command. The Python executable and module must come from this virtual environment.

Example command shape:

```text
Firestorm.exe --leap "C:\path\to\firestorm-mcp\tools\firestorm_mcp_bridge\.venv\Scripts\python.exe -m firestorm_mcp_bridge"
```

Additional exact attachment names can be allowlisted by repeating:

```text
--allow-attachment-name "Another disposable test HUD"
```

The bridge writes the active endpoint and a random per-viewer bearer token to:

```text
%LOCALAPPDATA%\FirestormMCP\session.json
```

The default MCP endpoint is `http://127.0.0.1:8765/mcp`. The session descriptor is removed when the bridge shuts down normally.

For the standard 64-bit Firestorm installation on Windows, `launch_installed_firestorm.ps1` performs the same launch safely. Its normal mode refuses to continue if Firestorm is already running, so it will not terminate a viewer or risk unsaved state:

```powershell
.\launch_installed_firestorm.ps1
```

Multi-login is an explicit option:

```powershell
.\launch_installed_firestorm.ps1 -Multiple
```

This adds Firestorm's `--multiple` flag and automatically gives the bridged viewer a free loopback MCP port, a unique session descriptor, and a separate capture directory. Use the `SessionFile` returned by the launcher to connect to that specific viewer. `-Port`, `-SessionFile`, and `-CaptureDirectory` can be supplied when fixed values are needed. `-WhatIf` prints the fully constructed launch result without starting Firestorm.

The Windows launcher packs bridge settings into a base64url JSON launch token and uses forward slashes for the bridge executable path. Firestorm reparses the text supplied to `--leap`, treating backslashes as escapes, so this avoids both nested-quote damage and stripped Windows path separators while preserving attachment names and configuration paths that contain spaces.

## Safety boundary

- MCP listens only on `127.0.0.1`.
- Every viewer session gets a random bearer token.
- Host and Origin validation protect the HTTP endpoint from DNS rebinding.
- Request size and session counts are limited.
- Touch is restricted to a currently worn, explicitly allowlisted attachment name.
- Screenshots hide viewer UI by default.
- There are no script, inventory-write, chat-send, teleport, arbitrary input, or arbitrary object tools.
