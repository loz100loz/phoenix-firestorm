# Stage 2 reversible test-HUD script proof

**Approval:** Explicitly approved by the user

**Status:** Implemented, automated tests passed, and live proof passed

**Live HUD mutation performed:** Yes, on 2026-09-18; exact original restored and verified

## Exact approved boundary

This is not a general object or script editor. The only approved live mutation
is a single atomic round trip against the currently worn exact attachment name
`MCP POC ROOT`. The bridge resolves runtime IDs internally and requires exactly
one LSL script. The MCP caller cannot supply an object ID, item ID, or source.

The viewer API reuses Firestorm's normal task-inventory, asset retrieval, and
`UpdateScriptTask` upload paths. It enforces object modify plus script copy and
modify permission, honors an RLVa attachment lock, and returns structured
compiler results.

## Reversible operation

The proof performs these gates and actions as one locked operation:

1. Re-enumerate worn attachments and require one exact allowlisted HUD match.
2. Fetch task inventory and require exactly one copyable/modifiable LSL script.
3. Retrieve its current source through Firestorm's permission-aware asset path.
   Normalize the single trailing NUL terminator used by task-script assets, and
   reject any embedded or repeated NUL bytes as invalid source.
4. Save and read-verify an exact timestamped backup outside Git.
5. Query and preserve running state, Mono/LSO target, and Experience association.
6. Append only a unique harmless comment and upload it.
7. Require compile success and exact marked-source read-back.
8. Upload the exact original, require compile success, and verify exact read-back.

If the marked upload or verification fails, restoration is still attempted. If
restoration cannot be proven, the operation reports the local recovery path and
retains the backup.

## Current implementation

- `LLScriptAutomation/getTaskInventory`
- `LLScriptAutomation/getScriptSource`
- `LLScriptAutomation/updateScriptSource`
- `list_test_hud_scripts`
- `prove_test_hud_script_round_trip`
- `add_third_touch_color`

The Python bridge tests cover the complete mark/read-back/restore/read-back
sequence with a mock viewer, including restoration after a simulated marked
compile failure. The custom Firestorm build also succeeded.

The first live attempt exposed a normal trailing-NUL task-asset terminator and
was rejected before upload, so it did not change the script. The retrieval path
was corrected to remove exactly that terminator while rejecting embedded or
repeated NUL bytes.

The rebuilt viewer then passed the live proof on 2026-09-18:

- fresh API discovery exposed `LLScriptAutomation`;
- exactly one worn `MCP POC ROOT` and one copyable/modifiable script passed the
  preflight gates;
- an outside-Git exact backup was written and read-verified;
- the generated marker compiled and its exact source was read back;
- the 291-byte original compiled, was restored, and was read back exactly; and
- running state, Mono/LSO target, and Experience association were preserved.

This proves only the narrowly approved disposable test-HUD round trip. It does
not approve or prove a general script editor or arbitrary-object mutation.

## Approved persistent three-color edit

The user subsequently authorized one persistent change to the same disposable
test script: preserve its red and green touch results and add blue as the third
touch result. `add_third_touch_color` implements that request without exposing
a general editor. It accepts no IDs, source, or color input and proceeds only
when the sole script still has the exact expected one-variable red/green toggle
shape. It saves and verifies the original outside Git, compiles and exactly
reads back the generated three-color source, and automatically restores the
original if compilation or verification fails.

Automated success and compile-failure restoration tests pass. The persistent
live operation then passed on 2026-09-19:

- fresh discovery confirmed the guarded tool plus exactly one worn test HUD
  and one copyable/modifiable script;
- the exact 291-byte original was backed up outside Git;
- the fixed blue third state was added, producing a 388-byte candidate;
- Firestorm reported compile success and exact source read-back succeeded;
- running state, Mono/LSO target, and Experience association were preserved;
  and
- HUD-visible captures after live touches visually confirmed red, green, and
  blue states.

An initially delayed capture was caused by the user's configured 1 FPS limit
while Firestorm was tabbed out. It was a background-render timing effect, not
script execution or bridge latency; longer settling produced all three visible
states.

The edit is persistent. The recovery backup remains outside Git.

## Expansion boundary

The architecture can later support other visible objects and HUDs that the
avatar is permitted to inspect and modify. It cannot bypass ownership,
copy/modify permissions, RLVa locks, missing region capabilities, or objects
not available to the viewer. Expanding beyond this one disposable test HUD
requires a separate explicit approval and a new object-selection policy.
