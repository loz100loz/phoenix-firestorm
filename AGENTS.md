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

The intended next product workflow is project-folder synchronization: local
`.lsl` files organized by game device in VS Code should be the source of truth,
with explicit manifest mappings to Firestorm task scripts. Implement this in
stages, beginning with the exact test HUD. Do not infer authorization to write
other devices until owned/selected-object resolution and its safety policy are
explicitly approved and live-proven.

Use `tools/firestorm_mcp_bridge/examples/fake_lsl_game` for workspace manifest
and save-watcher development until the user explicitly supplies a real project
root. Never scan for or guess the user's game workspace. Fake workspace targets
must remain deliberately nonexistent and must not trigger live viewer writes.

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
