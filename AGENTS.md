# Firestorm MCP project guidance

## Read the project index first

Before changing or testing Firestorm MCP, read
`doc/firestorm_mcp/README.md`. Follow its links to the current status, original
roadmap, bridge operations, and relevant code/tests. The roadmap describes
possible later stages; it is not authorization to implement them.

Keep the index accurate. When adding, removing, renaming, or materially
changing a Firestorm MCP document, component, tool, safety boundary, workflow,
compatibility finding, or verified stage result, update the index and the
applicable status document in the same change.

## Project scope

This fork contains a deliberately narrow Stage 0 proof of concept under
`tools/firestorm_mcp_bridge`. Keep Stage 0 changes in that directory (plus
small repository-level documentation or ignore rules) unless the user
explicitly approves viewer changes.

Do not modify Firestorm C++ to complete Stage 0. Use the viewer's existing
LEAP event APIs. The user subsequently approved the narrow Stage 2 test-HUD
script proof below; that does not authorize other later-stage features.

## Stage 0 contract

The supported MCP surface is limited to:

- reporting viewer and login status;
- discovering exposed viewer APIs;
- listing the logged-in avatar's worn attachments;
- touching one explicitly allowlisted, currently worn test HUD; and
- capturing a HUD-visible screenshot with viewer UI hidden by default.

Do not add script editing, inventory writes, chat sending, teleporting,
arbitrary viewer input, or arbitrary-object operations without a new,
explicitly approved stage.

## Approved Stage 2 test-HUD script operations

The first approved script mutation is an atomic reversible proof against the
currently worn exact attachment name `MCP POC ROOT`. The MCP tool must:

- accept no caller-supplied object UUID, item UUID, or replacement source;
- require exactly one attachment-name match and exactly one LSL script;
- enforce Firestorm's normal object/script permissions and RLVa attachment lock;
- save and verify an exact timestamped source backup outside Git before upload;
- append only a generated harmless comment;
- preserve running state, Mono/LSO target, and Experience association;
- require structured compile success and exact source read-back;
- restore, recompile, and read back the exact original source; and
- retain the local backup and report a recovery path if restoration fails.

This proof is not authorization for arbitrary objects, production HUDs,
caller-supplied source, script creation/deletion, or general inventory writes.

The user subsequently approved one persistent edit to that same disposable
test HUD: extend its exact red/green `touch_start` toggle with blue as the third
state. The MCP tool must accept no caller-supplied object ID, item ID, source,
or color; require the known one-variable/two-`llSetColor` source shape; back up
the exact original outside Git; compile and read-verify the exact candidate;
and restore/recompile/read-verify the original automatically if the edit fails.
This does not authorize any other persistent script edit.

The user then approved a reusable two-step editor for the sole script in the
exact worn `MCP POC ROOT`. It may accept bounded exact-replace or append
fragments, but never object/item IDs or a full-source read response. Preview
must create a 30-minute plan and reviewable diff outside Git without uploading.
Apply must require the exact confirmation phrase, re-resolve the HUD/script,
reject a stale source, create an exact backup, compile, read-verify, and restore
on failure. Consumed, stale, safely restored, and expired plans must be removed.
If append needs to add a separating newline, preview must report that fact so a
later inverse edit can remove the complete inserted fragment when required.
This approval remains limited to the disposable test HUD; it does not authorize
arbitrary HUDs, rezzed objects, bulk writes, or source deletion.

## Approved read-only target identity foundation

The user approved a read-only selected-object identity layer as the safety
foundation for later world-object work. It may expose viewer/avatar/grid/region
context, inspect exactly one selected linkset or linked prim, list script
inventory only after strict self-owner and modify checks, issue a short-lived
in-memory handle bound to that viewer/avatar session, and revalidate that handle.
It must not mutate, touch, move, create, rez, attach, answer dialogs, or accept a
caller-supplied object UUID. Names are display labels only. Group-owned and
other-avatar-owned targets receive no handle. A changed viewer, avatar, region,
selection, linkset, permission set, object metadata, or script inventory must
invalidate the handle before any later operation can use it.

The intended next product workflow is project-folder synchronization: local
`.lsl` files organized by game device in VS Code should be the source of truth,
with explicit manifest mappings to Firestorm task scripts. Implement this in
stages, beginning with the exact test HUD. Do not infer authorization to write
other devices until owned/selected-object resolution and its safety policy are
explicitly approved and live-proven.

The user approved the first read-only workspace comparison tool. It must use
only workspace roots named and allowlisted when the bridge launches; tool calls
may accept workspace/device/script keys and a short-lived target handle, but no
filesystem path, object UUID, or task-item UUID. It must revalidate the selected
target before reading, require target kind and exact mapped name as assertions,
resolve exactly one copyable/modifiable script by exact name, and revalidate
again after the source read. Return only hashes, byte counts, mapping metadata,
and status; never return source or write to the workspace or viewer. Hashes use
UTF-8 text with line endings normalized to LF so Windows CRLF is not a false
change. A verified in-memory baseline may be established only when local and
remote hashes match; it is session-bound and must not be persisted or guessed.

The user subsequently approved `preview_workspace_push` only. It may accept the
same workspace/device/script keys and short-lived target handle, but must refuse
unless `workspace_status` is exactly `local_ahead` from a verified session
baseline. It must re-resolve the mapping, revalidate target identity and script
permissions, re-read both sources, revalidate again, and reject any changed
hash. The resulting 30-minute plan and unified diff must live outside Git under
runtime state. MCP responses may return plan/diff paths, hashes, sizes, names,
and mapping metadata, but never source or runtime object/item UUIDs. Preview
must not upload, compile, back up, or alter Firestorm or the workspace.

The user subsequently approved the complete single-script
`apply_workspace_push` stage, including a live install-and-exact-restore proof
limited to `MCP POC ROOT` and an isolated runtime workspace. Apply may accept
only a preview plan ID plus the exact `APPLY WORKSPACE PUSH` confirmation; it
must not accept source, paths, object UUIDs, item UUIDs, workspace keys or a
target handle directly. It must reject expired, cross-session, stale, changed,
ambiguous, permission-denied or integrity-failed plans; re-read and revalidate
the allowlisted mapping, selected strict-self-owned target, exact script,
baseline, local source, remote source and diff immediately before upload; save
and verify the exact remote source outside Git; preserve running state, Mono/LSO
target and Experience association; require compile success and exact source
read-back; return per-file compiler diagnostics; and restore/recompile/read-back
the original automatically on failure. Safely consumed, stale and restored
plans are removed. If restoration fails, retain the plan and backup and report
the recovery path. This approval is one mapped script at a time and does not
authorize production objects, device-set transactions, script creation/deletion
or workspace pull.

Use `tools/firestorm_mcp_bridge/examples/fake_lsl_game` for workspace manifest
and save-watcher development until the user explicitly supplies a real project
root. Never scan for or guess the user's game workspace. Fake workspace targets
must remain deliberately nonexistent and must not trigger live viewer writes.

Before adding world-object, dialog, movement, creation, rez, attach, or broader
control tools, read and follow
`doc/firestorm_mcp/TARGET_IDENTITY_SECURITY.md`. Object names are discovery
labels, not unique identity or write authority. Mutations must bind to the
current viewer/avatar session, default to strict self-ownership, use a
short-lived inspected target, revalidate immediately before apply, and fail
closed on duplicates, incomplete properties, owner mismatch, changed selection
or stale state. Group-owned writes require separate explicit approval and an
allowlisted policy.

LSL fixtures and generated LSL must use syntax supported by Second Life. LSL
does not provide the C-style ternary `condition ? a : b`; use `if`/`else`.
Treat any future Second Life Lua language as a separately discovered source
language rather than conflating it with the current Mono/LSO runtime target.

Security-boundary testing is allowed and expected when it is hypothesis-driven,
minimally invasive, and scoped to user-controlled accounts, objects, scripts,
inventory and land or another environment with explicit authorization. Test
expected denials such as wrong owner, restricted permissions, duplicate names,
stale handles, cross-viewer sessions and invalid/replayed credentials. Public
source and protocol review are also allowed. Never use a discovered bypass as a
product feature or broaden testing into third-party objects or data. If an
operation unexpectedly succeeds where normal permissions should deny it, stop
the affected path and follow the responsible-disclosure procedure in
`doc/firestorm_mcp/TARGET_IDENTITY_SECURITY.md`. Do not publicize it or send a
report without the user's review and approval.

Remote access is intended to use tailnet-only Tailscale Serve in front of the
existing loopback listener. Do not bind MCP to all interfaces and do not use
Tailscale Funnel. Do not change Tailscale state until the user approves the
exact hostname, port, access policy, and rollback command. Preserve bearer
authentication in addition to tailnet policy.

## Live-test safety

- Never request, read, store, or enter the user's Firestorm credentials.
- Do not automate the login form. Let the user log in normally when needed.
- Preserve the user's stable Firestorm installation. Test another channel
  side by side with `-ViewerPath`; never replace or uninstall stable.
- When launching this repository's Windows source build, use the compiled
  executable from `build-vc170-64/newview/Release` but set
  `-ViewerWorkingDirectory` to `indra/newview`. The raw executable directory
  intentionally contains only partially copied development assets; using it as
  the working directory causes a missing `app_settings/settings_files.xml`
  shutdown. Run the `copy_w_viewer_manifest` Release target after dependency
  changes, but do not mistake its copy-only output for a packaged install.
- Preserve open viewers and unsaved state. Do not terminate a viewer unless
  the user explicitly asks or the process is verified to be only a failed
  launch/error dialog.
- Use `-Multiple` for multi-login tests. Each bridged viewer must receive a
  unique loopback port, session descriptor, and capture directory.
- Keep MCP bound to `127.0.0.1` with per-session bearer authentication. Never
  print, commit, or include bearer tokens in reports, logs, screenshots, or PRs.
- Treat `%LOCALAPPDATA%\FirestormMCP` as runtime state, not repository content.

Before a live touch, enumerate attachments again and require exactly one exact
name match for `MCP POC ROOT` (or another name explicitly allowlisted for that
session). Abort on zero matches or ambiguous matches. Never accept an arbitrary
object UUID as a touch target.

Firestorm's `requestTouch` notification has no acknowledgement. Report a touch
as sent, not confirmed, and use the scripted test HUD's visible response or
owner-side evidence when confirmation is needed.

The user's Firestorm is configured to limit background rendering to 1 FPS.
When the viewer is tabbed out, allow extra time before HUD-visible screenshot
verification; a delayed rendered frame is not evidence of script or bridge lag.

Before the live script proof, enumerate attachments and task inventory again.
Abort before upload unless there is exactly one worn `MCP POC ROOT` and exactly
one copyable/modifiable LSL script. Never put live-retrieved source, backup
contents, object/item UUIDs, or session tokens in the Firestorm MCP repository,
logs, documentation, or PR text. A user-declared script workspace may
intentionally contain and version its own `.lsl` source; do not confuse that
with runtime backups or source returned from Firestorm.

## Windows launcher compatibility

Use `tools/firestorm_mcp_bridge/launch_installed_firestorm.ps1` for installed
Windows viewers. Keep paths passed through `--leap` safe from Firestorm's
second command-line parse. Firestorm 7.2.5 and newer map `LeapCommand` to LLSD;
the launcher uses delimiter-safe LLSD URI notation for those versions. Verify
launcher changes with `-WhatIf` before a live launch.

## Development and verification

Run bridge commands from `tools/firestorm_mcp_bridge`:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

For a complete live proof, verify in this order:

1. `viewer_status`
2. `discover_viewer_apis(refresh=True)`
3. `list_attachments`
4. confirm exactly one exact allowlisted HUD match
5. `touch_test_hud`
6. `capture_viewer(show_ui=False, show_hud=True)`
7. visually inspect the saved PNG before reporting success

Keep commits focused, stage only task files, and leave unrelated user changes
untouched. Never add session descriptors, captures, credentials, tokens,
virtual environments, build products, or installed viewer binaries to Git.
