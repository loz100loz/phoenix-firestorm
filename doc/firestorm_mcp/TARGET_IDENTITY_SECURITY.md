# Target identity and control security

## Purpose

Firestorm MCP operates in a shared online world where object names are not
unique, several avatars may use the same computer, and multiple Firestorm
processes may be logged in at once. A visible name is useful for discovery but
must never be sufficient authority for a mutating operation.

The intended experience is still streamlined: the user selects or wears the
object once, MCP presents an unambiguous target summary, and subsequent guarded
operations can reuse a short-lived verified handle while its identity remains
unchanged.

## Implementation status

The read-only foundation is implemented:

- `viewer_context` reports a non-secret bridge fingerprint plus the current
  avatar, grid and region;
- `inspect_selected_target` accepts no object ID, requires one selected
  linkset, and issues a ten-minute in-memory handle only for a strictly
  self-owned, modifiable target with complete properties;
- `revalidate_selected_target` re-resolves the live selection and rejects
  expired, cross-viewer, changed-selection, changed-permission, changed-linkset
  or changed-script-inventory state; and
- public MCP results contain a target identity hash and script summary, not the
  runtime object or task-item UUIDs used internally.

Automated tests, the modified viewer compile, and the first live proof pass.
This layer performs no object or script mutation.

## Live proof result

The read-only identity flow passed live on 2026-09-19 using the side-by-side
custom viewer and the disposable self-owned `MCP POC ROOT` attachment:

1. `viewer_context` reported the already logged-in avatar and current region
   without handling credentials.
2. `inspect_selected_target` resolved the single Edit selection as the root of
   a one-link attachment, confirmed self ownership plus copy/modify permission,
   and reported one script metadata entry without returning source.
3. The bridge issued a short-lived target handle and
   `revalidate_selected_target` immediately accepted the unchanged selection.
4. After the user closed Edit or changed selection, revalidation rejected the
   original handle as stale.

No runtime object UUID, task-item UUID, bearer credential, handle value, or
script source was recorded in the repository or proof notes. Expiry and
cross-viewer rejection remain automated-test results; a controlled concurrent
multi-viewer live proof can be performed later when useful.

## Human-control capability summary

The viewer source contains mechanisms for all of the following, but only the
already documented test-HUD subset is exposed by the current MCP server.

| Requested control | Feasibility | Required MCP work |
| --- | --- | --- |
| Create a new primitive in-world | Feasible | Permission-aware object-create API, land/build checks, result correlation, preview and confirmation |
| Rez an inventory object | Feasible | Exact inventory-item resolution, destination preview, parcel checks, rez result correlation |
| Attach or detach an object | Feasible | Exact self-owned inventory target, attachment-point policy, RLVa checks and post-attach verification |
| Touch world objects or HUD links | Mechanism exists | Selected/linkset target resolution, owner policy, face/UV support and result evidence |
| Read, answer and test script dialogs | Mechanism exists | Filtered `LLNotifications` wrapper, source validation, short-lived dialog handles, assertions and screenshots |
| Create a new script inside an object | Feasible | Selected-prim API, strict permissions/ownership, duplicate-name refusal, compile/read-back and rollback/cleanup policy |
| Read or replace an existing permitted script | Core proof exists | Expand guarded target policy beyond the exact disposable HUD |
| Move the avatar | Mechanisms exist | Scoped wrappers for teleport, sit, stand, autopilot/follow and cancellation; keyboard input only as a fallback |
| Control camera and collect screenshots | Mechanisms exist | Bounded MCP camera wrapper; screenshot is already available |
| Operate arbitrary viewer UI like a human | Technically possible in part | Firestorm exposes keyboard/mouse injection and UI paths, but structured APIs are safer and more reliable |

This can become a broad development and testing control surface, but it cannot
guarantee literally every action a human can perform. Simulator permissions,
parcel and estate rules, server capabilities, RLVa, throttles, lag, collisions,
render range, attachment limits, disappearing dialogs, and viewer UI changes
remain authoritative. Authentication, payments, permission grants, account
security, and other high-consequence actions should not be delegated to a
generic UI-control tool.

## Authorized security validation and responsible disclosure

The project should actively verify that security boundaries hold rather than
merely assume they do. Hypothesis-driven negative testing is allowed and
expected when it uses accounts, objects, scripts, inventory and land controlled
by the user, or another environment for which the user has explicit testing
authorization. Public viewer/source review and protocol analysis are also
appropriate ways to identify a possible weakness without touching another
resident's content.

Useful controlled tests include:

- wrong-owner and deliberately restricted-permission test objects;
- duplicate names, changed selections and stale object/script handles;
- switching between user-controlled avatars and concurrent viewer sessions;
- invalid, expired, replayed or cross-viewer MCP plans and credentials;
- owner, group, region or permission changes between preview and apply;
- dialogs from the wrong object or avatar context; and
- logout, teleport, disconnect, compile failure and rollback interruption.

Tests must be bounded, minimally invasive and designed around a specific
expected denial or security property. Do not broadly scan residents, guess
credentials, access third-party protected source, persist in another account or
object, evade controls, disrupt a region/service, or use a discovered bypass as
a normal product feature. Protecting creators' source and inventory is part of
the product goal, not merely a limitation on the MCP.

An unexpected ability to read protected source, modify an unpermitted object,
impersonate another avatar session, cross viewer-session boundaries, bypass
land controls or evade another security check is a potential vulnerability.
If one is observed:

1. Stop the unexpected operation and disable the affected automation path.
2. Do not broaden impact, access third-party content or attempt persistence.
3. Preserve only the minimum reproducible metadata and locally controlled test
   artifacts needed to understand the issue; never commit secrets, protected
   source, session credentials or another resident's data.
4. Record the affected viewer/build, grid, region capability, expected denial,
   observed result and exact safe reproduction steps.
5. Review the result with the user. If confirmation is necessary, use the
   smallest controlled reproduction against user-owned test fixtures rather
   than testing for greater impact.
6. Determine whether the issue belongs to the viewer, simulator/service, or
   this MCP wrapper.
7. Prepare a private report for the current official Firestorm or Linden Lab
   security-reporting channel as appropriate. Nothing is sent or publicly
   disclosed without the user's review and approval.
8. Keep the related feature disabled until the owner confirms a safe fix or
   mitigation and the denial behavior is regression-tested.

Normal permission-denied results are expected and should be reported plainly;
they are not failures to work around.

## Viewer and avatar binding

Every bridge session must be bound to one Firestorm process and report:

- a non-secret viewer/session fingerprint;
- the logged-in avatar UUID and safe display name;
- grid, region and login state;
- bridge process and per-viewer MCP endpoint identity; and
- the enabled capability scopes.

The remote client must deliberately pair with that viewer session. With
multi-login, each viewer keeps a distinct loopback port, bearer credential,
runtime directory and remote route. A request intended for one avatar must not
fall through to another active viewer.

A project may use a friendly local profile key such as `builder` or `tester`.
The private mapping from that key to the expected avatar belongs outside Git.
Before an apply operation, MCP compares the current logged-in avatar with the
paired profile and aborts on mismatch.

## Selecting the correct object

### Names are not identity

If several objects share a name, MCP must return all candidates and refuse to
choose one automatically. Exact-name matching alone is acceptable only when
there is exactly one candidate inside an already constrained set, as with the
current worn test-HUD proof.

An object description marker such as a project/device key can help discovery,
but it can be copied and therefore cannot replace ownership and runtime
identity checks.

### Preferred world-object workflow

1. The user selects exactly one root or linked prim in Firestorm.
2. `inspect_selected_target` waits for complete simulator object properties.
3. It reports a safe summary: avatar, region, root/child name, link number,
   position, distance, owner relationship, group relationship, modify/copy
   permissions, script inventory summary and a linkset fingerprint.
4. It creates a random short-lived target handle outside Git. The handle binds
   the current viewer session, avatar, region, root and child IDs, owner,
   selection generation, linkset fingerprint and expiry time.
5. Preview uses that handle and names the exact object, prim and script it
   intends to change.
6. Apply re-fetches everything. Any changed selection, region, owner,
   permissions, object identity, linkset shape, script inventory or source hash
   invalidates the plan before mutation.

Runtime object UUIDs are useful inside these short-lived handles but should not
be kept in the version-controlled workspace manifest. Re-rezzing commonly
changes them.

### Attachments and HUDs

An attachment target must additionally prove that it is attached to the
currently logged-in avatar and match the expected attachment point, inventory
item, root object and project mapping. An attachment worn by another avatar is
never a writable target. Duplicate attachment names require explicit selection
or another unambiguous constrained match; MCP must not pick the first result.

## Ownership and permission policy

The safest default for every content mutation is `owner == logged_in_avatar`.
Viewer `permModify()` and script copy/modify checks remain mandatory but are
not, by themselves, a strict self-ownership rule because group powers may grant
access to group-owned objects.

Group-owned mutation should therefore be a separate, disabled-by-default
policy requiring an explicitly allowlisted group, current group powers and a
manual preview/confirmation. Third-party-owned mutation remains denied even if
some interaction is technically possible.

Before a script read, create or update, the bridge must verify all of these:

- target handle belongs to the current viewer and avatar session;
- object properties are complete and current;
- expected owner policy matches;
- object and target prim still exist in the expected region;
- the avatar can modify the object;
- the script can be copied and modified when source access is required;
- attachment RLVa locks do not prohibit the action;
- script name and inventory item resolve exactly once;
- preview source and remote source hashes are still current; and
- the operation has the required capability scope and confirmation level.

Fail closed on missing properties, timeouts, ambiguity or disconnects.

## Creating scripts, objects, rezzing and attaching

These operations need separate tools rather than a universal arbitrary-object
command:

- `preview_create_task_script` / `apply_create_task_script`
- `preview_create_prim` / `apply_create_prim`
- `preview_rez_inventory_object` / `apply_rez_inventory_object`
- `preview_attach_inventory_object` / `apply_attach_inventory_object`

Creating a task script must refuse an existing same-name item unless the user
chose an explicit replace workflow. Apply must verify the new item, compile
result, installed source and runtime state. If compilation or verification
fails, it should remove only the newly created item when that rollback has been
proven safe; otherwise it reports a recovery action instead of guessing.

Object creation and rez previews should show the avatar, region, parcel/build
permission, intended position, inventory item or primitive type and expected
land impact. Attach operations are self-avatar-only and must verify the final
attachment point and inventory item after the simulator replies.

## Dialog observation and testing

Firestorm's existing `LLNotifications` API can list and forward notifications
and respond to a specific notification UUID. A safe MCP wrapper should expose
only script-dialog data needed for testing:

- source object ID/name and owner when available;
- dialog message, textbox state and ordered button labels;
- timestamp, channel and a short-lived dialog handle; and
- a screenshot with unrelated private UI excluded where practical.

`assert_script_dialog` can compare expected source, text and buttons.
`respond_script_dialog` must accept an exact button label from that same live
dialog handle and refuse stale, ambiguous or differently sourced dialogs.
Generic permission, debit, URL, inventory-offer, teleport and account dialogs
must not be answerable through this script-test tool.

## Movement and manual override

Firestorm already exposes teleport, sit, stand, position, autopilot, follow and
camera operations through LEAP. Later MCP wrappers can use them, but each
movement should be bounded, cancellable and tied to the selected viewer/avatar.
Manual movement or cancellation by the user wins immediately. A region change,
logout, unexpected dialog, RLVa restriction or loss of the paired session
aborts the operation.

Autopilot is a request to the viewer, not a guarantee of arrival: collisions,
ban lines, parcel rules, physics and lag can prevent success. The tool should
report observed final position and reason rather than claiming movement merely
because a command was sent.

## Capability scopes and audit

Remote authentication should eventually issue separate scopes such as:

- read-only discovery;
- workspace/script writes;
- touch and dialog testing;
- object create/rez/attach;
- avatar movement and camera; and
- high-risk UI fallback.

The optional file watcher needs only workspace status/preview/push scope. It
does not need avatar movement, dialog response or general UI control.

Every mutating operation should record a metadata-only audit entry outside Git:
timestamp, viewer/avatar fingerprint, tool, plan/target handle, region, target
summary, ownership result, source hashes where relevant, compile/result status
and rollback outcome. Do not log bearer credentials, retrieved source, backup
contents or unrelated chat/dialog text.

## Script language compatibility

LSL does not support the C-style ternary `condition ? a : b` expression; use
ordinary `if`/`else`. Synthetic example scripts must remain valid LSL rather
than merely looking like C-family code.

Future Second Life Lua support should be represented as a script-language
capability discovered from the running viewer and region, not assumed. Keep
source language separate from the current LSL runtime target (`Mono` or `LSO`),
preserve the remote script's language/runtime metadata, and refuse unsupported
language conversions. The transaction, target-identity, backup, diagnostics and
read-back machinery can remain language-neutral.
