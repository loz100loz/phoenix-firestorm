# Stage 0 live proof

**Status:** Passed  
**Date:** 18 September 2026  
**Scope:** Existing Firestorm LEAP APIs only; no viewer C++ changes

## Result

The Stage 0 bridge completed the intended live loop:

1. Firestorm launched the bridge through `--leap`.
2. The authenticated MCP endpoint listened on loopback only.
3. `viewer_status` reported a connected LEAP session and a logged-in avatar.
4. Fresh discovery returned 21 viewer APIs, including `LLAgent` and
   `LLViewerWindow`.
5. Attachment enumeration returned the worn objects and exactly one exact
   match for `MCP POC ROOT`.
6. The bridge enumerated attachments again inside `touch_test_hud`, resolved
   that exact allowlisted match, and sent `requestTouch` for face 0.
7. Firestorm saved a 1600 x 900 PNG with viewer UI hidden and HUDs shown.
8. The actual PNG was visually inspected and showed the bright red scripted
   test panel.

Firestorm's existing `requestTouch` operation sends no acknowledgement, so the
bridge correctly reports the operation as sent rather than confirmed. The
scripted HUD's visible state is the proof-side observation.

## Compatibility findings

- Firestorm 7.2.4.80712 exposed the LEAP bridge and screenshot API but did not
  expose `LLAgent/getAttachedObjectsList`, so it could not safely complete the
  attachment-selection gate.
- Firestorm beta 7.2.5.81669 exposed the required attachment operation and
  completed the proof.
- Firestorm 7.2.5 changed `LeapCommand` to an LLSD setting. Plain command text
  failed LLSD parsing, and nested quoted notation was split by Firestorm's
  command-line tokenizer. The launcher now uses delimiter-safe LLSD URI
  notation, which preserved the full bridge command and launched successfully.
- `-Multiple` successfully launched an isolated bridged beta while another
  beta viewer process was already running. The bridged instance received its
  own port, session descriptor, and capture directory.
- The user's stable Firestorm installation was preserved side by side and was
  not replaced.

## Automated verification

The bridge test suite passed on Windows with Python 3.13.3:

```text
9 passed
```

The tests cover LEAP framing/correlation, service safety behavior, MCP tool
exposure, launch-config parsing, and a subprocess smoke path.

## Safety evidence

- No credentials were requested, read, stored, or entered by the bridge.
- No arbitrary or production HUD was touched.
- The default allowlist contained only `MCP POC ROOT`.
- The touch tool accepted no arbitrary object UUID.
- No script source, inventory contents, chat, teleport, arbitrary input, or
  viewer-internal generic event operation was exposed.
- Bearer authentication and runtime identifiers stayed outside Git.
- Screenshot capture hid normal viewer UI by default.

## Remaining limits

Stage 0 does not inspect child links or task inventory, read or update LSL,
return compiler results, control script runtime, or subscribe to runtime
messages. Those capabilities remain later-stage proposals in
`PROOF_OF_CONCEPT.md` and require explicit approval plus new safety design.

