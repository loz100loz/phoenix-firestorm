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
   or device without uploading.
3. `apply_workspace_push` rechecks source hashes, creates recovery backups,
   uploads in a deterministic order, returns compiler errors by local file, and
   stops or rolls back according to the selected transaction policy.
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
- Every write is previewed, explicitly confirmed, backed up, compiled, and
  exact-read-verified. Stale plans abort without upload.

## Staged implementation

1. **Transaction core:** bounded preview/apply edits for the exact worn
   `MCP POC ROOT`. Implemented, automated-tested, and live-proven.
2. **Workspace root and manifest:** manifest schema, local containment, UTF-8
   validation, duplicate mapping checks, and debounced save detection are
   implemented and tested against a synthetic three-device/four-script
   workspace. Firestorm status and push wiring remain pending.
3. **Owned selected object:** explicit current-selection resolution for one
   rezzed disposable device, with the same permission and ambiguity gates.
4. **Device sets:** multiple mapped scripts per device, deterministic compile
   ordering, per-file results, and configurable stop/rollback behavior.
5. **Development loop:** file watching or an explicit VS Code task for
   preview, push, compile diagnostics, and optional runtime checks.

Stages 3 and later require a separate live safety proof before production game
objects are allowed.

## Synthetic workspace

`tools/firestorm_mcp_bridge/examples/fake_lsl_game` contains three deliberately
fake devices with four scripts. Three mappings use `on_save`; one uses
`manual`. The save watcher waits for file content to remain stable for the
manifest's debounce interval before emitting one hash-only event. It never
returns source and is not connected to a live viewer target yet.
