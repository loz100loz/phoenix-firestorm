# Private Tailscale transport

## Goal

Allow a workspace watcher on another tailnet device to reach the authenticated
Firestorm MCP bridge without exposing it to the public internet or binding the
bridge to every network interface.

## Network shape

```text
VS Code + watcher                Firestorm PC
----------------                ------------
local game project              Tailscale Serve HTTPS endpoint
manifest + saved .lsl   ---->   127.0.0.1:<viewer MCP port>
                                Firestorm-owned LEAP bridge
```

This is the direct Tailscale-to-MCP design. Tailscale Serve is the private HTTPS
front door on the Firestorm PC and reverse-proxies to the MCP listener on that
same PC. The watcher is not another server: it is an optional MCP client that
turns a stable VS Code file-save event into a workspace status, preview, or
push request. An interactive MCP client can use the same route for the bridge's
other enabled controls, including explicit workspace pushes when no watcher is
running. See [`CAPABILITY_MATRIX.md`](CAPABILITY_MATRIX.md).

Tailscale Serve terminates HTTPS and applies the tailnet access policy. The MCP
bridge remains bound to `127.0.0.1` and continues to require its bearer token.
Both layers are required.

## Current Tailscale commands

For a fixed example bridge port of `8765`, current Tailscale documentation uses:

```powershell
tailscale serve --bg http://127.0.0.1:8765
tailscale serve status --json
tailscale serve off
```

`tailscale serve` is tailnet-only. Do not substitute `tailscale funnel`, which
publishes a service to the internet. Enabling Serve HTTPS may require a one-time
tailnet consent step. Tailnet policy must explicitly restrict which user or
device identities may reach the Firestorm PC service.

These commands are documentation, not an instruction to run them now. The
project has not changed the user's Tailscale state.

## Required bridge work before live use

1. Add an explicit external MagicDNS hostname/URL setting.
2. Add only that hostname to MCP Host and Origin validation while retaining the
   loopback allowlist.
3. Keep each multi-login viewer on a distinct port and explicit remote mapping.
4. Pair the remote watcher with the selected viewer session without copying the
   bearer token or session descriptor into Git, logs, chat, or the manifest.
5. Test unauthorized, wrong-tailnet-identity, wrong-host, stale-session, and
   viewer-shutdown behavior before enabling automatic writes.
6. Record `tailscale serve status --json` before mutation and verify `tailscale
   serve off` as the rollback.

The current random bearer token changes with each viewer session. A secure
pairing mechanism is therefore still required for unattended remote watching;
tailnet membership alone must not silently bypass MCP authentication.

## Save-to-object behavior

Once transport and mapping are connected, an `on_save` script follows this
sequence:

1. Wait for the local file to remain stable through the debounce interval.
2. Validate the manifest key, relative path, UTF-8 source, and size.
3. Send the local candidate over private tailnet HTTPS.
4. Resolve the current object and task script by the manifest's exact names.
5. Refuse missing, ambiguous, locked, stale, or unpermitted targets.
6. Back up the permitted remote source outside Git.
7. Upload and compile while preserving running state, VM target, and Experience.
8. Read back the exact installed source and return structured diagnostics.
9. Restore the original automatically if compile or verification fails.

Production mappings should default to `manual`; `on_save` is for individually
proven development devices.
