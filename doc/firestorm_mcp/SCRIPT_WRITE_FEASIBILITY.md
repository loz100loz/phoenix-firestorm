# HUD script-write feasibility

**Finding:** Feasible, but not exposed by the current LEAP/MCP surface  
**Source reviewed:** `Firestorm_Beta_7.2.5.81669` (`8741b19ca554c0c6da70b470b2480cae3ee7998d`)  
**Live HUD mutation performed:** No

## Answer

Firestorm can write new LSL source into an existing script inside an attached
HUD, send it through Second Life's normal compiler, and receive compilation
success or errors. Firestorm's standard live script editor already does this.

The installed beta does not expose that workflow through LEAP. The current MCP
therefore cannot yet enumerate the HUD's task inventory, read its script
source, or upload replacement source. Generic UI clicking would test the wrong
boundary and would not provide reliable permission or compiler results.

## Existing code that proves the write path

- `indra/newview/llviewerobject.cpp` fetches object task inventory through the
  region's `RequestTaskInventory` capability and notifies asynchronous
  inventory listeners.
- `indra/newview/llpreviewscript.cpp` implements `LLLiveLSLEditor`. It resolves
  the task inventory item, enforces normal copy and modify permission checks,
  fetches permitted source through the normal asset system, and saves through
  the region's `UpdateScriptTask` capability.
- `indra/newview/llviewerassetupload.cpp` implements `LLScriptAssetUpload` for
  a task ID, item ID, Mono/LSL2 target, running state, experience ID, and source
  buffer.
- The existing upload callback returns `compiled` and `errors`; Firestorm's
  live editor already routes these to compile-success and compile-failure
  handlers.
- `indra/newview/llcompilequeue.cpp` demonstrates asynchronous task-inventory
  retrieval, asset retrieval, upload, timeout handling, and compiler-result
  processing without depending on editor text controls.
- `indra/newview/fslslbridge.cpp` independently demonstrates programmatic LSL
  upload into an attached Firestorm bridge object.

These are reusable viewer paths. A script API should call them rather than
posting raw simulator messages or automating the editor window.

## What the beta exposes through LEAP

`LLInventory` is avatar-inventory only. Its operations are:

- `getItemsInfo`
- `getFolderTypeNames`
- `getAssetTypeNames`
- `getBasicFolderID`
- `getDirectDescendants`
- `collectDescendantsIf`

The matching beta contains no LEAP listener operation named
`getTaskInventory`, `getScriptSource`, `updateScriptSource`, or
`LLScriptAutomation`.

## Smallest useful implementation

A narrow viewer event API should provide three asynchronous operations:

1. `getTaskInventory` — fetch one visible object's task inventory, wait for a
   complete reply, and return script item metadata plus effective permissions.
2. `getScriptSource` — reuse the live editor's permission and asset-fetch path;
   fail normally when source is not viewable.
3. `updateScriptSource` — enforce the same permissions, use
   `LLScriptAssetUpload` with `UpdateScriptTask`, and return structured compile
   and installation results.

The MCP layer should expose a still narrower operation for the first proof. It
must resolve the currently worn exact attachment name `MCP POC ROOT`, require
exactly one exact script-name match, and never accept an arbitrary object or
item UUID from the caller.

## First reversible live write test

Before uploading anything, the proof must:

1. Resolve exactly one worn `MCP POC ROOT` attachment.
2. Fetch its task inventory and identify exactly one explicitly allowlisted
   test script.
3. Confirm the object and script satisfy Firestorm's normal view/modify
   permission checks.
4. Retrieve the current permitted source and save a timestamped local recovery
   copy outside Git.
5. Upload a harmless uniquely marked comment added to that source while
   preserving compilation target, running state, and experience association.
6. Require a structured `compiled: true` and installed result.
7. Fetch the source again to verify the marker is present.
8. Restore the exact original source, require a second successful compilation,
   and verify the restored source.

Abort without upload on ambiguity, missing permissions, retrieval failure,
backup failure, missing region capability, logout, object disappearance,
timeout, or compile failure. Never test against a production HUD.

## Current conclusion

No live script was changed during this feasibility check. The blocker is not
Second Life or Firestorm's ability to write the script; it is the missing
narrow LEAP API. Implementing that API requires a custom Firestorm build and is
a new permission-bearing stage, not a bridge-only Stage 0 change.

