# Firestorm MCP documentation index

This is the canonical starting point for people and AI agents working on the
Firestorm MCP project. Read this page before changing code or running a live
viewer test.

## Current state

Stage 0 is implemented and has passed a live proof using an unmodified
Firestorm 7.2.5 beta. The bridge can discover viewer APIs, list worn
attachments, touch the exact allowlisted scripted test HUD, and return a
HUD-visible screenshot.

The user approved one narrow Stage 2 extension: a custom side-by-side viewer
plus a single atomic write/compile/read-back/restore proof for the sole script
in the exact worn `MCP POC ROOT` test HUD. The implementation, automated tests,
custom viewer build, and live reversible proof have passed. The exact original
source was restored and read back after recompilation. A subsequent one-purpose
persistent operation extended the known red/green touch toggle with blue. Its
live compile, exact source read-back, and three-color visual touch proof passed.
The next approved implementation step is a reusable two-step editor for that
same test HUD. Its transaction core and automated tests are implemented; live
preview/apply/compile/read-back and exact restoration have passed. The
longer-term target is manifest-driven sync from the user's VS Code game-project
folders. A synthetic three-device workspace plus validated, debounced save
detection is implemented without accessing the real game project or uploading
to live objects. The read-only `workspace_status` MCP tool connects a named,
launch-allowlisted workspace mapping to a revalidated selected target and
reports hash-only sync state. `preview_workspace_push` now creates a 30-minute
outside-Git plan and reviewable local-to-world diff only when that status is
verified `local_ahead`; it re-reads and revalidates without uploading or
altering either side. Both tools are automated-tested, and the preview passed a
live read-only proof on 2026-09-19 against the disposable `MCP POC ROOT` and an
isolated outside-Git runtime workspace. The repository example targets remain
deliberately nonexistent so they cannot accidentally match live content. Apply
remains unavailable. Private Tailscale transport is designed but not configured.

The approved read-only target-identity foundation is also implemented and
automated-tested. It reports per-viewer avatar/grid/region context, inspects one
selected linkset, enforces strict self-ownership before returning an expiring
session-bound target handle, and rejects stale or cross-viewer handles. The
modified viewer target compiles successfully, and the live selected-object
proof passed on 2026-09-19 against the disposable self-owned `MCP POC ROOT`.
No world-object mutation has been added.

Later-stage features in the roadmap are ideas and design targets only. They
must not be implemented until the user explicitly approves a new stage.

## Documentation map

| Document | Purpose | When to read or update |
| --- | --- | --- |
| [`AGENTS.md`](../../AGENTS.md) | Mandatory scope, safety, testing, and documentation-maintenance rules | Read first with this index; update when agent operating rules change |
| [`PROOF_OF_CONCEPT.md`](PROOF_OF_CONCEPT.md) | Original architecture, proposed capabilities, staged roadmap, risks, and full long-term acceptance concept | Read for design intent; update only when the approved roadmap changes |
| [`STAGE_0_LIVE_PROOF.md`](STAGE_0_LIVE_PROOF.md) | What was actually tested, evidence, compatibility findings, and remaining limits | Update after a meaningful repeat or expansion of the live proof |
| [`SCRIPT_WRITE_FEASIBILITY.md`](SCRIPT_WRITE_FEASIBILITY.md) | Source-backed answer on whether MCP can write and compile an existing HUD script, what is missing, and the safest first live write test | Read before designing or implementing script access |
| [`STAGE_2_SCRIPT_WRITE_PROOF.md`](STAGE_2_SCRIPT_WRITE_PROOF.md) | Approved safety contract, implementation status, verification order, and eventual live result for the reversible test-HUD script proof | Read before script API work or any live script write; update with every material result |
| [`WORKSPACE_SYNC.md`](WORKSPACE_SYNC.md) | Target VS Code-to-Firestorm device/script workflow, manifest shape, transaction model, and staged expansion boundary | Read before adding local-file sync or world-object targeting |
| [`TAILSCALE_REMOTE.md`](TAILSCALE_REMOTE.md) | Tailnet-only remote transport design, current gaps, commands, access controls, and rollback | Read before changing bind, proxy, authentication, or remote-client settings |
| [`CAPABILITY_MATRIX.md`](CAPABILITY_MATRIX.md) | Current, pending, and possible Firestorm MCP controls plus the watcher/Tailscale relationship | Read when choosing what to build or explaining local and remote control scope |
| [`TARGET_IDENTITY_SECURITY.md`](TARGET_IDENTITY_SECURITY.md) | Avatar/session binding, duplicate-name handling, selected-object identity, ownership checks and safety policy for expanded controls | Read before any world-object, dialog, movement, creation, rez, attach or general-control work |
| [`tools/firestorm_mcp_bridge/README.md`](../../tools/firestorm_mcp_bridge/README.md) | Bridge setup, launch instructions, tools, runtime files, and safety boundary | Read before setup/launch; update with operational or tool changes |
| [`doc/building_windows.md`](../building_windows.md) | Upstream Firestorm Windows build instructions | Read only if an approved later stage requires building the viewer |
| [`CONTRIBUTING.md`](../../CONTRIBUTING.md) | Upstream repository contribution rules | Read before broader viewer changes or upstream contribution work |

## Code map

| Path | Responsibility |
| --- | --- |
| `tools/firestorm_mcp_bridge/src/firestorm_mcp_bridge/leap.py` | Length-prefixed LLSD LEAP transport, request correlation, and API discovery |
| `tools/firestorm_mcp_bridge/src/firestorm_mcp_bridge/service.py` | Stage 0 policy, guarded test-HUD transactions, session-bound target identity, hash-only workspace comparison, and read-only push planning |
| `tools/firestorm_mcp_bridge/src/firestorm_mcp_bridge/server.py` | Authenticated localhost MCP server, tools, launch config, and session descriptor |
| `tools/firestorm_mcp_bridge/src/firestorm_mcp_bridge/workspace.py` | Manifest validation, path containment, source validation, and debounced local-save detection |
| `tools/firestorm_mcp_bridge/launch_installed_firestorm.ps1` | Safe installed-viewer launch, side-by-side channel selection, multi-login isolation, and Firestorm-version argument compatibility |
| `tools/firestorm_mcp_bridge/tests/` | LEAP, service, server, MCP, and process smoke tests |
| `indra/newview/llscriptautomationlistener.*` | Viewer/avatar context, selected-object inspection, and permission-preserving task-inventory/source operations |

## Architectural decisions

- Firestorm launches a small external Python bridge through LEAP.
- MCP uses authenticated Streamable HTTP bound only to `127.0.0.1`.
- LEAP standard input/output stays reserved for framed LLSD messages.
- Stage 0 uses existing viewer APIs and makes no viewer C++ changes.
- A touch target is resolved from the avatar's current attachments immediately
  before the operation. The tool accepts an exact allowlisted name, not an
  arbitrary object UUID.
- World-object names are display labels only. Read-only selected targets use a
  ten-minute in-memory handle bound to one bridge/avatar session; strict
  self-owner, permission, region, linkset, metadata and inventory state are
  revalidated before that handle can be reused.
- Workspace tools can access only roots named at bridge launch. `workspace_status`
  returns canonical hashes and mapping/status metadata. `preview_workspace_push`
  additionally writes a short-lived plan and unified diff outside Git only for
  verified `local_ahead` state. Neither returns source or changes Firestorm or
  the workspace; apply is not exposed.
- Runtime session descriptors and screenshots stay under
  `%LOCALAPPDATA%\FirestormMCP` and must not be committed.
- Multi-login viewers receive separate ports, session descriptors, and capture
  directories.
- The user's viewer limits background rendering to 1 FPS, so live screenshot
  checks need extra settling time while Firestorm is tabbed out.
- Remote transport will keep MCP on `127.0.0.1` and use tailnet-only Tailscale
  Serve; Funnel and direct all-interface binding are outside the design.
- Firestorm 7.2.5+ needs LLSD notation for `LeapCommand`; the Windows launcher
  supplies a delimiter-safe LLSD URI value.

## Stage boundary

| Stage | Status | Scope |
| --- | --- | --- |
| Stage 0 | Implemented and live-tested | LEAP connection, discovery, attachment listing, exact allowlisted HUD touch, screenshot |
| Stage 1 | Implemented, build-tested, and live-tested | Viewer/avatar context, selected-linkset inspection, strict self-owner gate, permission/script summary, expiring handle and stale/cross-viewer rejection; no world-object writes |
| Stage 2 | Proof, three-color edit, and reusable test-HUD editor live-passed | Exact test-HUD task inventory, permitted retrieval, reversible proof, fixed color edit, and bounded preview/apply transactions; no other objects |
| Workspace status and push preview | Implemented, automated-tested, and live-tested against the disposable test HUD | Named workspace allowlist, manifest mapping, selected-target revalidation, exact script resolution, hash-only comparison, session baseline, and outside-Git diff/plan; no viewer or workspace writes |
| Stage 3 | Not approved or implemented | Structured runtime-message observation and expanded interaction tests |
| Stage 4 | Not approved or implemented | Preferences, audit logs, backups, owner restrictions, cancellation, and recovery hardening |

## Standard verification

From `tools/firestorm_mcp_bridge`:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

A live Stage 0 proof must follow the ordered safety gate in `AGENTS.md` and
must end with visual inspection of the actual saved PNG. Do not report a touch
as confirmed merely because `requestTouch` was sent; that viewer operation has
no acknowledgement. If Firestorm is backgrounded, account for the configured
1 FPS background cap before interpreting a delayed HUD frame.

## Documentation maintenance

Keep this page useful as a true index rather than a history dump:

1. Add every new Firestorm MCP document to the documentation map.
2. Update the code map when responsibilities or entry points change.
3. Update the stage table only when scope is explicitly approved or verified.
4. Record repeatable proof evidence in the applicable status document.
5. Link to canonical material instead of duplicating instructions.
6. Never record credentials, bearer tokens, private chat, unrelated attachment
   names, avatar UUIDs, object UUIDs, inventory UUIDs, or other session secrets.
