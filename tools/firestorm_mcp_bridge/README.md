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
- `viewer_context`
- `inspect_selected_target`
- `revalidate_selected_target`
- `workspace_status`
- `preview_workspace_push`
- `apply_workspace_push`
- `touch_test_hud`
- `capture_viewer`
- `list_test_hud_scripts`
- `prove_test_hud_script_round_trip`
- `add_third_touch_color`
- `preview_test_hud_script_edit`
- `apply_test_hud_script_edit`

The three target-identity tools are read-only. `viewer_context` returns the
non-secret identity of the bridge/avatar/grid/region session plus Firestorm's
startup state and an authoritative `viewer_ready` value. `viewer_ready` becomes
true only at `STATE_STARTED` with a non-null avatar and valid current region;
the bridge does not use a login timer or assume that an early region pointer
means the world is ready. Touch, selection/inventory inspection, and script
writes refuse to run while it is false.
`inspect_selected_target` accepts no object UUID and requires exactly one
selected linkset. It returns object/link/permission metadata and a script
summary, but only issues a ten-minute in-memory handle when the target is
strictly owned by the logged-in avatar and modifiable. Group-owned or
other-avatar-owned targets are reported as blocked. `revalidate_selected_target`
rejects expired, cross-viewer or changed target state. Public target summaries
do not include the runtime object or task-item UUIDs retained inside the handle.

`workspace_status` accepts a named allowlisted workspace, manifest device/script
keys, and a live target handle. It revalidates the selected self-owned target,
checks mapped kind/name and exact script identity/permissions, reads both sources
internally, revalidates again, and returns only canonical hashes, byte counts and
`unchanged`, `local_ahead`, `remote_ahead`, `conflict`, `missing`, or `blocked`.
It never returns source and performs no viewer or workspace write.

`preview_workspace_push` accepts the same keys and refuses every state except
verified `local_ahead`. It then resolves and reads the mapping again,
revalidates the exact self-owned target and copy/modify script permissions,
checks that both hashes are unchanged, and writes a 30-minute JSON plan plus
unified diff under `%LOCALAPPDATA%\FirestormMCP\workspace-push-plans` (or the
corresponding runtime root in tests). Its response contains only metadata and
the diff path—never source or runtime object/item UUIDs. It does not upload,
compile, create a recovery backup, or modify the workspace.

`apply_workspace_push` accepts only a preview plan ID and the exact confirmation
`APPLY WORKSPACE PUSH`. It rejects expired or cross-session plans and rechecks
the manifest mapping, selected self-owned target identity, exact script and
permissions, baseline, local/remote hashes and persisted diff before upload. It
then writes and verifies an exact outside-Git remote-source backup, performs one
final post-backup recheck, uploads while preserving runtime/VM/Experience state,
requires compile success and exact source read-back, and advances the in-memory
baseline. Compiler errors are returned with the relative local path. Any upload,
compile or read-back failure triggers exact restore/recompile/read-back; a safe
rollback consumes the plan, while a failed rollback retains recovery material.
Responses never contain source or runtime object/item UUIDs, and apply never
writes the local workspace.

The complete live single-script push proof passed on 2026-09-19 against the
disposable `MCP POC ROOT` using an isolated runtime workspace. It established
an equal baseline, classified a local-only comment as `local_ahead`, created and
verified the outside-Git diff/plan and backup, compiled and exact-read-verified
the change, then previewed/applied the exact original again. Both plans were
consumed and final local/in-world hashes matched the original with status
`unchanged`. No source or runtime object/item UUID was returned.

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

## Fake workspace and save watcher

The repository includes a synthetic three-device LSL project under
`examples/fake_lsl_game`. It never targets a real object. Validate it with:

```powershell
.\.venv\Scripts\python.exe -m firestorm_mcp_bridge.workspace validate .\examples\fake_lsl_game
```

Watch it for stable local saves with:

```powershell
.\.venv\Scripts\python.exe -m firestorm_mcp_bridge.workspace watch .\examples\fake_lsl_game
```

The watcher validates relative path containment, `.lsl` type, UTF-8 source,
NUL absence, unique mappings, sync mode, and a configurable 100–10000 ms
debounce. It emits metadata and hashes, not source. Live Firestorm push wiring
is intentionally not enabled for these fake object names.

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

For this repository's Windows source build, use the compiled executable but
keep Firestorm's working directory at the source resource tree:

```powershell
.\launch_installed_firestorm.ps1 `
  -ViewerPath '..\..\build-vc170-64\newview\Release\firestorm-bin-next.exe' `
  -ViewerWorkingDirectory '..\..\indra\newview' `
  -Multiple `
  -WorkspaceRoot 'fake-lsl-game=.\examples\fake_lsl_game'
```

The Release executable directory is not a packaged installation and must not be
used as `-ViewerWorkingDirectory`; doing so omits source-tree application
settings such as `app_settings/settings_files.xml`. Build the Release
`copy_w_viewer_manifest` target when staged runtime dependencies need refresh.
`-WorkspaceRoot KEY=PATH` may be repeated. The resolved roots are fixed in the
bridge launch configuration; MCP callers cannot substitute another path.

The Windows launcher packs bridge settings into a base64url JSON launch token and uses forward slashes for the bridge executable path. Firestorm reparses the text supplied to `--leap`, treating backslashes as escapes, so this avoids both nested-quote damage and stripped Windows path separators while preserving attachment names and configuration paths that contain spaces.

Firestorm 7.2.5 and newer also require the `--leap` value to use LLSD notation. The launcher detects the selected executable's product version and supplies a delimiter-safe LLSD URI value automatically, avoiding nested quotes while preserving the command text.

## Safety boundary

- MCP listens only on `127.0.0.1`.
- Every viewer session gets a random bearer token.
- Host and Origin validation protect the HTTP endpoint from DNS rebinding.
- Request size and session counts are limited.
- Touch is restricted to a currently worn, explicitly allowlisted attachment name.
- Selected-object inspection is read-only; names never authorize a target, and
  only a strict self-owned, modifiable object can receive a session-bound handle.
- Workspace status, preview and apply are limited to named launch-allowlisted
  roots, manifest keys, a session-bound selected target and source-withholding
  results. Preview writes its expiring plan/diff outside Git. Apply requires the
  exact confirmation, backup and repeated revalidation; it can update only the
  single script bound into that plan and cannot change the local workspace.
- Screenshots hide viewer UI by default.
- The reversible script mutation is limited to exactly one
  script in the exact allowlisted worn test HUD; caller-supplied source and IDs
  are rejected by design.
- One additional persistent mutation is limited to extending the exact known
  red/green test-HUD touch toggle with fixed blue; it also rejects caller source,
  IDs, colors, or scripts whose structure does not match the guarded template.
- There are no general inventory-write, chat-send, teleport, arbitrary input,
  arbitrary object, or general script-editing tools.
