# Firestorm MCP capability matrix

This page separates controls that are live today from controls that are only
planned or technically possible. The remote network path does not reduce the
available MCP tool set: a permitted client on another tailnet device can call
the same tools as a local client.

## How remote control fits together

```text
Remote development PC                         Main Firestorm PC
---------------------                         -----------------
VS Code save
    |
optional workspace watcher --\
                              +-- private tailnet HTTPS --> Tailscale Serve
interactive MCP client -------/                               |
                                                              v
                                                   127.0.0.1:<viewer port>/mcp
                                                              |
                                                     Firestorm MCP bridge
                                                              |
                                                        LEAP connection
                                                              |
                                                   one Firestorm process
```

The watcher is an optional MCP client. It detects a stable mapped `.lsl` save,
then requests preview/status/push operations. An AI can instead edit the local
LSL and call those MCP tools directly whenever it decides the change is ready;
all workspace functions remain available with no watcher running. An
interactive MCP client can connect to the same server for every other exposed
control. Tailscale Serve is the private HTTPS reverse proxy into the
loopback-only MCP listener; it is
still a direct Tailscale path from the remote PC to the MCP on the Firestorm
PC. Firestorm and the bridge do not need access to the remote project folder.

Keeping MCP on loopback means it is not directly exposed to the LAN, the
tailnet interface, or the public internet. Tailscale Serve supplies the
tailnet-only entry point, TLS, and tailnet policy, while MCP still requires its
own bearer authentication. Funnel is not part of the design.

For multi-login, each Firestorm process has its own bridge, loopback port,
session token, runtime directory, and explicit remote mapping. A client must
select the intended viewer rather than whichever viewer happens to answer.

## Available and proven now

These MCP tools exist in the current bridge. Live mutation remains deliberately
limited to the disposable worn attachment named exactly `MCP POC ROOT`.

| Control | Current tool | Current boundary |
| --- | --- | --- |
| Check bridge/viewer/login readiness | `viewer_status` | Read-only |
| Discover Firestorm LEAP APIs | `discover_viewer_apis` | Read-only |
| List worn attachments and HUD roots | `list_attachments` | Read-only |
| Send a touch to the test HUD | `touch_test_hud` | Exact allowlisted worn HUD; send has no acknowledgement |
| List scripts in the test HUD | `list_test_hud_scripts` | Exactly one permitted HUD target |
| Prove write/compile/read/restore | `prove_test_hud_script_round_trip` | Generated harmless change; exact restoration |
| Add the proven third touch color | `add_third_touch_color` | One fixed source transformation only |
| Preview a bounded script edit | `preview_test_hud_script_edit` | Exact replace or append; no upload |
| Apply a previewed edit | `apply_test_hud_script_edit` | Confirmation, stale check, backup, compile, verify, rollback |
| Preview one mapped workspace push | `preview_workspace_push` | Verified `local_ahead` only; repeated revalidation, 30-minute outside-Git plan/diff, no source response or upload |
| Capture visual evidence | `capture_viewer` | Viewer UI hidden by default; HUD may be shown |

The custom viewer also has permission-preserving LEAP operations for task
inventory, script-source retrieval, and source upload/compile. The MCP policy
currently wraps them only in the guarded test-HUD operations above; their
presence is not permission for general object writes.

## Implemented locally but not connected to live writes

| Capability | Current state |
| --- | --- |
| Validate an explicitly chosen project manifest | Implemented and tested |
| Validate contained UTF-8 `.lsl` paths and reject NULs/duplicates | Implemented and tested |
| Watch mapped files with a debounce interval | Implemented and tested |
| Emit hash-only stable-save events | Implemented and tested |
| Synthetic three-device/four-script workspace | Implemented and tested |
| Per-viewer avatar/grid/region context | Implemented, automated-tested, and live-tested |
| Selected-linkset inspection and script summary | Implemented, automated-tested, and live-tested |
| Strict self-owner gate and expiring target handles | Implemented, automated-tested, and live-tested |
| Changed-selection rejection | Implemented, automated-tested, and live-tested |
| Expired and cross-viewer handle rejection | Implemented and automated-tested; controlled multi-viewer live proof remains future work |
| Hash-only `workspace_status` comparison | Implemented and automated-tested; fake example names intentionally have no live target |
| Outside-Git `preview_workspace_push` plan/diff | Implemented, automated-tested, and live-tested against the disposable test HUD; one script, verified `local_ahead`, no upload |
| Push a saved file into Firestorm | Not wired yet |
| Remote Tailscale endpoint and pairing | Designed, not configured |

## Next development controls

These form the practical VS Code-to-Firestorm loop. They will be callable
directly by an AI or developer; the optional watcher merely invokes the same
tools after selected save events:

| Planned tool/control | Purpose |
| --- | --- |
| `apply_workspace_push` | Recheck hashes, back up, upload, compile, return diagnostics, exact-read-verify, and restore on failure |
| `preview_workspace_pull` / `apply_workspace_pull` | Bring permitted in-world changes back without silently overwriting local work |
| Multi-viewer identity proof | Verify cross-viewer handle rejection between two user-controlled concurrent viewer sessions |
| Device-set transactions | Update several mapped scripts in deterministic order with stop/rollback policy |
| Runtime test helpers | Touch mapped controls, capture results, and correlate structured test messages |

Automatic `on_save` should initially be allowed only for individually proven
development mappings. Production objects and multi-script devices should stay
manual preview/confirm until their transaction and rollback behavior is
proven.

## Broader controls Firestorm can support

Firestorm already exposes some of these through LEAP; others need narrow viewer
APIs or safer MCP wrappers. They are feasible roadmap items, not current tool
permissions.

| Area | Possible controls | Work/boundary |
| --- | --- | --- |
| World discovery | List nearby rendered objects; inspect current selection | Existing discovery plus safe target policy |
| Linksets | List root/children, link numbers, names, faces, transforms, ownership, and effective permissions | New structured inspection API/wrapper |
| Object contents | List permitted task inventory in a selected prim | Viewer API exists for the proof; general target policy needed |
| LSL development | Read permitted source; write/compile; return line/column errors; preserve VM, running state, and Experience | Core proof exists; general object workflow and live proof needed |
| Script runtime | Query/start/stop/reset scripts | New viewer operations and explicit approval needed |
| Interaction | Touch exact root or linked prim/face/UV; operate mapped test controls | Touch exists; link-safe resolution and acknowledgements need work |
| Observation | Receive correlated nearby chat, owner messages, dialogs, notifications, and script errors | Event subscriptions, filtering, privacy controls, and tests needed |
| Camera and evidence | Move/frame camera and capture screenshots with HUD/UI options | Firestorm APIs exist; MCP safety wrapper needed |
| Viewer UI automation | Inspect UI paths/values and inject bounded mouse/keyboard input | Firestorm APIs exist; high-risk fallback, not enabled now |
| Avatar inventory | Query normal avatar inventory and metadata | Firestorm API exists; no general MCP inventory tool now |
| Session context | Login status, region, selected viewer, disconnect/logout handling | Partial status exists; hardening remains |

“Full controls” should mean a broad, explicit, permission-checked tool set—not
an unrestricted remote-control endpoint. Firestorm and Second Life permissions
remain authoritative. The bridge must not bypass ownership, modify/copy rights,
RLVa locks, region capabilities, or normal script-source visibility. Login
credentials, public internet exposure, arbitrary destructive inventory writes,
and silent production updates remain outside the design. The concrete
viewer/avatar binding, duplicate-name and selected-object rules are defined in
[`TARGET_IDENTITY_SECURITY.md`](TARGET_IDENTITY_SECURITY.md).
