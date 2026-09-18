# Firestorm MCP documentation index

This is the canonical starting point for people and AI agents working on the
Firestorm MCP project. Read this page before changing code or running a live
viewer test.

## Current state

Stage 0 is implemented and has passed a live proof using an unmodified
Firestorm 7.2.5 beta. The bridge can discover viewer APIs, list worn
attachments, touch the exact allowlisted scripted test HUD, and return a
HUD-visible screenshot. Stage 0 does not read or write LSL source and does not
modify Firestorm C++.

Later-stage features in the roadmap are ideas and design targets only. They
must not be implemented until the user explicitly approves a new stage.

## Documentation map

| Document | Purpose | When to read or update |
| --- | --- | --- |
| [`AGENTS.md`](../../AGENTS.md) | Mandatory scope, safety, testing, and documentation-maintenance rules | Read first with this index; update when agent operating rules change |
| [`PROOF_OF_CONCEPT.md`](PROOF_OF_CONCEPT.md) | Original architecture, proposed capabilities, staged roadmap, risks, and full long-term acceptance concept | Read for design intent; update only when the approved roadmap changes |
| [`STAGE_0_LIVE_PROOF.md`](STAGE_0_LIVE_PROOF.md) | What was actually tested, evidence, compatibility findings, and remaining limits | Update after a meaningful repeat or expansion of the live proof |
| [`SCRIPT_WRITE_FEASIBILITY.md`](SCRIPT_WRITE_FEASIBILITY.md) | Source-backed answer on whether MCP can write and compile an existing HUD script, what is missing, and the safest first live write test | Read before designing or implementing script access |
| [`tools/firestorm_mcp_bridge/README.md`](../../tools/firestorm_mcp_bridge/README.md) | Bridge setup, launch instructions, tools, runtime files, and safety boundary | Read before setup/launch; update with operational or tool changes |
| [`doc/building_windows.md`](../building_windows.md) | Upstream Firestorm Windows build instructions | Read only if an approved later stage requires building the viewer |
| [`CONTRIBUTING.md`](../../CONTRIBUTING.md) | Upstream repository contribution rules | Read before broader viewer changes or upstream contribution work |

## Code map

| Path | Responsibility |
| --- | --- |
| `tools/firestorm_mcp_bridge/src/firestorm_mcp_bridge/leap.py` | Length-prefixed LLSD LEAP transport, request correlation, and API discovery |
| `tools/firestorm_mcp_bridge/src/firestorm_mcp_bridge/service.py` | Stage 0 safety policy and viewer operations |
| `tools/firestorm_mcp_bridge/src/firestorm_mcp_bridge/server.py` | Authenticated localhost MCP server, tools, launch config, and session descriptor |
| `tools/firestorm_mcp_bridge/launch_installed_firestorm.ps1` | Safe installed-viewer launch, side-by-side channel selection, multi-login isolation, and Firestorm-version argument compatibility |
| `tools/firestorm_mcp_bridge/tests/` | LEAP, service, server, MCP, and process smoke tests |

## Architectural decisions

- Firestorm launches a small external Python bridge through LEAP.
- MCP uses authenticated Streamable HTTP bound only to `127.0.0.1`.
- LEAP standard input/output stays reserved for framed LLSD messages.
- Stage 0 uses existing viewer APIs and makes no viewer C++ changes.
- A touch target is resolved from the avatar's current attachments immediately
  before the operation. The tool accepts an exact allowlisted name, not an
  arbitrary object UUID.
- Runtime session descriptors and screenshots stay under
  `%LOCALAPPDATA%\FirestormMCP` and must not be committed.
- Multi-login viewers receive separate ports, session descriptors, and capture
  directories.
- Firestorm 7.2.5+ needs LLSD notation for `LeapCommand`; the Windows launcher
  supplies a delimiter-safe LLSD URI value.

## Stage boundary

| Stage | Status | Scope |
| --- | --- | --- |
| Stage 0 | Implemented and live-tested | LEAP connection, discovery, attachment listing, exact allowlisted HUD touch, screenshot |
| Stage 1 | Not approved or implemented | Linkset/task-inventory inspection and permission metadata |
| Stage 2 | Feasibility confirmed; not implemented | Permitted LSL source retrieval, update, compilation, and runtime control |
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
no acknowledgement.

## Documentation maintenance

Keep this page useful as a true index rather than a history dump:

1. Add every new Firestorm MCP document to the documentation map.
2. Update the code map when responsibilities or entry points change.
3. Update the stage table only when scope is explicitly approved or verified.
4. Record repeatable proof evidence in the applicable status document.
5. Link to canonical material instead of duplicating instructions.
6. Never record credentials, bearer tokens, private chat, unrelated attachment
   names, avatar UUIDs, object UUIDs, inventory UUIDs, or other session secrets.
