# VS Code project-folder synchronization

## User workflow

The user keeps a game in a project folder. Each device has its own subfolder
and set of LSL files. Today every change must be copied from VS Code into a
Firestorm script editor, saved, checked for compilation, and then tested. The
target workflow makes the local `.lsl` files the source of truth and uses
Firestorm only as the permission-aware compile, install, and runtime-test
target.

The project folder can live on another tailnet device. In that layout, the
watcher runs beside VS Code and sends only the mapped saved script over private
HTTPS to the Firestorm PC; the Firestorm PC does not mount or scan the project.

## Two operating modes

The MCP workspace tools are the primary interface and do not depend on a
watcher:

1. An AI or developer edits and saves a local `.lsl` file.
2. The AI explicitly calls workspace status or preview for the mapped script.
3. After review/confirmation, the AI calls apply to upload, compile,
   exact-read-verify, and optionally run a mapped test.

This manual/on-demand mode remains fully usable when the watcher is stopped or
disabled. It is the default for production mappings and multi-script changes.

The watcher is an optional convenience client. For a mapping explicitly marked
`on_save`, it detects a stable save after the debounce interval and invokes the
same underlying MCP workflow. It does not provide a separate server or a
different set of Firestorm controls. A project may freely mix `manual` and
`on_save` mappings.

## Intended project shape

```text
game-project/
  firestorm-mcp.json
  devices/
    door-controller/
      controller.lsl
      access-list.lsl
    game-hud/
      main.lsl
      display.lsl
```

The manifest will map stable local device and script keys to exact in-world
object and task-script names. Runtime UUIDs must never be stored in the
manifest. Firestorm resolves current object and inventory IDs immediately
before every operation.

## Target operations

1. `workspace_status` compares local files with permitted Firestorm source and
   reports unchanged, local-ahead, remote-ahead, conflict, missing, or blocked.
2. `preview_workspace_push` builds an outside-Git plan and diff for one script
   without uploading. The implemented first slice requires verified
   `local_ahead` state, re-reads/revalidates before writing a 30-minute plan,
   and returns metadata plus the diff path without source.
3. `apply_workspace_push` is implemented for one mapped script. It accepts only
   a plan ID and exact confirmation, rechecks target/mapping/baseline/source/diff
   integrity, writes an exact outside-Git backup, uploads and compiles, returns
   compiler errors by local file, exact-read-verifies success, and restores the
   original on failure.
4. `preview_workspace_pull` and `apply_workspace_pull` safely bring permitted
   in-world changes back to local files without silently overwriting work.
5. Runtime test helpers can touch an explicitly mapped test control, capture
   HUD output, and later observe structured script messages.

## Safety and mapping rules

- A workspace root is explicitly allowlisted when the bridge launches. Tool
  calls use only manifest keys and relative paths contained by that root.
- Local files may intentionally be version-controlled in the user's game repo.
  Live backups, edit plans, session descriptors, captures, object IDs, and
  inventory IDs remain outside Git under local application data.
- Push never uses a stored object UUID. Each target is resolved by its declared
  kind plus exact name and must be unambiguous at operation time.
- Firestorm's normal ownership, copy/modify permissions, RLVa locks, region
  capabilities, compile results, VM target, running state, and Experience
  association remain authoritative.
- Full source is not returned in MCP responses. Reviewable diffs are written to
  a local path, and responses contain only paths, hashes, sizes, and status.
- Workspace roots are named and allowlisted when the bridge starts. Status
  calls accept only those names, manifest keys, and a selected-target handle;
  callers cannot supply a filesystem path or runtime object/item UUID.
- Status hashes canonicalize UTF-8 line endings to LF so an otherwise identical
  Windows CRLF file does not appear changed. Actual byte sizes remain visible.
- A session-only comparison baseline is learned only from a verified equal
  local/remote pair. Without that baseline, unequal sources are conservatively
  `conflict`; after it exists, one-sided changes are `local_ahead` or
  `remote_ahead` and two-sided changes remain `conflict`.
- Every write is previewed, explicitly confirmed, backed up, compiled, and
  exact-read-verified. Stale plans abort without upload.

## Staged implementation

1. **Transaction core:** bounded preview/apply edits for the exact worn
   `MCP POC ROOT`. Implemented, automated-tested, and live-proven.
2. **Workspace root and manifest:** manifest schema, local containment, UTF-8
   validation, duplicate mapping checks, and debounced save detection are
   implemented and tested against a synthetic three-device/four-script
   workspace. Hash-only `workspace_status` is implemented with named launch
   allowlists, selected-target revalidation, exact script matching, permission
   checks and source-withholding. Single-script preview and apply are implemented
   and automated-tested. Apply adds exact confirmation, post-backup revalidation,
   an outside-Git recovery backup, compile diagnostics, exact read-back, baseline
   advancement after success, and automatic restoration after failure. Its live
   disposable-HUD proof remains pending; device-set writes remain a later stage.
3. **Owned selected object:** explicit current-selection resolution for one
   rezzed disposable device, with the same permission and ambiguity gates.
4. **Device sets:** multiple mapped scripts per device, deterministic compile
   ordering, per-file results, and configurable stop/rollback behavior.
5. **Development loop:** direct AI/MCP calls are the primary path; optional
   file watching or an explicit VS Code task can invoke the same preview, push,
   compile-diagnostic, and runtime-check tools.

Stages 3 and later require a separate live safety proof before production game
objects are allowed.

## Live read-only push-preview proof

On 2026-09-19, `preview_workspace_push` passed its first live proof against the
disposable worn `MCP POC ROOT`; no production workspace or object was used.

1. An isolated workspace under `%LOCALAPPDATA%\FirestormMCP` was populated from
   an existing verified runtime backup whose canonical hash exactly matched the
   sole live script.
2. The bridge launched with that workspace as a named allowlisted root and
   issued a handle only after the exact selected attachment passed self-owner,
   modify, script-count, copy and modify checks.
3. `workspace_status` reported `unchanged` and established the session baseline.
4. A harmless comment was appended only to the isolated local `.lsl` file;
   `workspace_status` then reported `local_ahead`.
5. `preview_workspace_push` created its 30-minute JSON plan and unified diff
   outside Git. The diff hash verified and the diff contained the local-only
   marker.
6. A final status call remained `local_ahead`; the live remote hash still
   matched the baseline, `source_returned` was false, and `writes_performed` was
   false.
7. The MCP tool inventory confirmed that `apply_workspace_push` was not exposed.

This proves selection binding, baseline classification, revalidation and plan
generation on a live permitted target. It is not an upload/compile proof and is
not approval to expose apply or use production objects.

## Synthetic workspace

`tools/firestorm_mcp_bridge/examples/fake_lsl_game` contains three deliberately
fake devices with four scripts. Three mappings use `on_save`; one uses
`manual`. The save watcher waits for file content to remain stable for the
manifest's debounce interval before emitting one hash-only event. It never
returns source. The example object/script names remain deliberately nonexistent,
so allowlisting this folder cannot accidentally match the user's live content.
