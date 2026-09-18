# Firestorm MCP proof-of-concept bridge

Start with the [Firestorm MCP documentation index](../../doc/firestorm_mcp/README.md)
for the roadmap, current proof status, safety boundaries, and code map.

This directory contains the live-tested Stage 0 bridge plus the implemented
and live-tested, deliberately narrow Stage 2 reversible test-HUD script proof.
It does not expose a general script editor or arbitrary object mutation.

The bridge is launched by Firestorm through `--leap`. Its standard input and output are reserved for Firestorm's length-prefixed LLSD protocol. At the same time, it exposes authenticated MCP Streamable HTTP on `127.0.0.1`.

## Exposed MCP tools

- `viewer_status`
- `discover_viewer_apis`
- `list_attachments`
- `touch_test_hud`
- `capture_viewer`
- `list_test_hud_scripts`
- `prove_test_hud_script_round_trip`
- `add_third_touch_color`
- `preview_test_hud_script_edit`
- `apply_test_hud_script_edit`

`touch_test_hud` cannot accept an arbitrary object UUID. It resolves an exact allowlisted name against the avatar's currently worn attachments immediately before sending Firestorm's existing `requestTouch` operation. The default allowlist contains only `MCP POC ROOT`.

`capture_viewer` hides the viewer UI and shows HUDs by default. Screenshots stay in the current user's local application-data directory and are returned as MCP image content.

`list_test_hud_scripts` resolves the same exact allowlisted worn HUD and lists
only its LSL scripts. `prove_test_hud_script_round_trip` accepts no object ID,
item ID, or replacement source. It requires exactly one script, saves an exact
backup under `%LOCALAPPDATA%\FirestormMCP\script-backups`, adds and compiles a
generated comment, verifies it by reading the source back, then restores,
recompiles, and verifies the exact original.

`add_third_touch_color` is a separate one-purpose persistent operation. It
accepts no source, IDs, or color input. It only transforms the known red/green
touch toggle in the exact allowlisted test HUD into a red/green/blue cycle,
after saving an exact outside-Git backup. It requires compile success and exact
read-back, and restores the original automatically if either step fails.

`preview_test_hud_script_edit` and `apply_test_hud_script_edit` form a bounded
two-step editor for the same exact test HUD. Preview accepts only exact replace
or append fragments and writes the complete review diff to local application
data without uploading or returning full source. Apply requires its one-use
plan ID and exact confirmation phrase, rejects stale source, backs up, compiles,
read-verifies, and restores on failure. Plans expire after 30 minutes. If an
append needs a newline separator, preview returns `separator_added: true` so an
inverse transaction can remove the complete inserted fragment exactly.

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

Use `-ViewerPath` to launch another installed channel, such as a side-by-side Firestorm beta. The running-process guard follows that executable's filename instead of assuming the release-channel process name.

The Windows launcher packs bridge settings into a base64url JSON launch token and uses forward slashes for the bridge executable path. Firestorm reparses the text supplied to `--leap`, treating backslashes as escapes, so this avoids both nested-quote damage and stripped Windows path separators while preserving attachment names and configuration paths that contain spaces.

Firestorm 7.2.5 and newer also require the `--leap` value to use LLSD notation. The launcher detects the selected executable's product version and supplies a delimiter-safe LLSD URI value automatically, avoiding nested quotes while preserving the command text.

## Safety boundary

- MCP listens only on `127.0.0.1`.
- Every viewer session gets a random bearer token.
- Host and Origin validation protect the HTTP endpoint from DNS rebinding.
- Request size and session counts are limited.
- Touch is restricted to a currently worn, explicitly allowlisted attachment name.
- Screenshots hide viewer UI by default.
- The reversible script mutation is limited to exactly one
  script in the exact allowlisted worn test HUD; caller-supplied source and IDs
  are rejected by design.
- One additional persistent mutation is limited to extending the exact known
  red/green test-HUD touch toggle with fixed blue; it also rejects caller source,
  IDs, colors, or scripts whose structure does not match the guarded template.
- There are no general inventory-write, chat-send, teleport, arbitrary input,
  arbitrary object, or general script-editing tools.
