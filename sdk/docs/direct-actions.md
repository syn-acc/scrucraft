# Direct-action contract — 0.2 development

**Live experimental release, 2026-11-03.** Adapter 0.4.0 and gateway 0.2.0.dev1
expose the primitives below. Lifecycle and identity use the
[HTTP contract](../agent-sdk.md). [WebSockets](realtime.md) are live. Raw inventory transactions, digging,
placement, crafting and containers are later work; no endpoint for them is promised.

The player's agent plans the task. Java executes supported body operations and
reports results. A new command can replace current work. Survival interruption,
human stop and lease expiry must be handled as interruptions, not completion.

## Discover support

A fresh observation may include:

```json
{"body_epoch":"opaque-incarnation-id","raw_capabilities":["move_to","look_at","stop"],"action_results":[]}
```

Absence of an operation from `raw_capabilities` means it is unavailable. Read this
from the selected body, not from the SDK package version. `body_epoch` identifies
the current body executor; after an epoch change, discard commands based on the
old body and inspect its replacement. Body descriptions may also advertise
`raw_capabilities`, but command submission needs a fresh observation.

## Submit an action

`POST /v1/actions` uses bearer, body and lease headers from the baseline contract.

```json
{"id":"movement_request_0001","op":"move_to","target":[110.5,64,104.5],"body_epoch":"opaque-incarnation-id","ttl_seconds":30}
```

| Field | Requirement |
| --- | --- |
| `id` | 16–80 ASCII letters, digits, `_` or `-`; preserve for exact retries |
| `op` | `move_to`, `look_at`, or `stop`, advertised by the selected body |
| `body_epoch` | Exact epoch from a fresh observation |
| `target` | Required for movement/look: three finite numbers, each within ±30000000 |
| `ttl_seconds` | Integer 1–30, default 30; distinct from lease renewal |

Receipt:

```json
{"id":"movement_request_0001","state":"accepted","body_epoch":"opaque-incarnation-id","expires_at":1793700030}
```

This means the gateway accepted the command. It is not a body result. Direct
commands are limited to one per body per 0.05 seconds and require a fresh frame.
The gateway checks support and epoch, with `422 unsupported_operation`,
`409 adapter_upgrade_required`, or `409 body_changed` on rejection.

## Read results

`GET /v1/action-results` needs the bearer and body headers, but no lease, and
returns `{"results":[...]}` from a fresh snapshot. Results also appear in
`action_results` observations. Match **ID and epoch**, not list order.

```json
{"id":"movement_request_0001","state":"done","reason":"arrived","body_epoch":"opaque-incarnation-id"}
```

| State | Meaning |
| --- | --- |
| `accepted` | Gateway receipt only; execution has not been proven |
| `started` | Executor began work; for movement, path search has started |
| `done` | Executor reports completion (`arrived`, `oriented`, or `stopped`) |
| `failed` | Executor could not complete the request |
| `cancelled` | Work was interrupted or replaced |

These are snapshots of the latest result per ID, **not an append-only event log**.
Fast `look_at` and `stop` operations may go straight to `done`; polling may miss
`started`. The candidate keeps at most 64 results per body executor in memory.
There is no durable cursor, replay subscription or retention-time guarantee.
If a result is absent after reconnect/epoch change, the outcome is unknown.

Possible movement failure reasons include `target_out_of_range`, `invalid_endpoint`,
`unreachable`, `search_budget_exhausted`, `blocked`, `timeout`, and `dead`.
Other results can include `body_changed`, `invalid_arguments` or `replaced`.
Handle additional reasons without crashing and retain the server's explanation.

## Navigation scope

The candidate walks through loaded terrain using bounded incremental path search
and collision checks. It snaps targets to standing cells, supports a restricted
set of steps/jumps/drops and replans around changes. Current limits include a
64-block target distance, 4096 discovered search cells, and bounded retries.
Arrival means reaching the selected standing cell, not exact arbitrary coordinates.
Fluids and known damaging terrain are avoided. Swimming, ladders and door opening
are not advertised capabilities. Movement does not mine, place, teleport or force
chunk generation. Unit fixtures do not establish live navigation reliability.

## Cancellation and retry boundaries

Primitive submission replaces a goal; goal submission replaces primitive control.
Bodies opting into the direct WebSocket bridge reject goals with `use_primitive_stream`.
Submitting `look_at` while moving also replaces the current command. Primitive
`stop` is a command with an ID/result. The SDK's existing `stop()` instead calls
`DELETE /v1/goal`, which clears pending control without producing a primitive-stop
receipt. Neither acknowledges a persistent human stop.

The SDK renews leases in the background but does not renew primitive actions.
Commands expire independently. IDs are deduplicated within the current lease at
the gateway and within the executor's bounded result cache; this is not a durable
exactly-once transaction. On network ambiguity, inspect results before any new
submission. Reusing an ID with different payload/epoch is not a valid retry.

The current SDK `action()` fetches an observation and supplies its epoch. For an
exact wire retry across uncertain state, preserve the original entire request;
do not assume repeating `action()` after a body change reconstructs that request.

Release gates include real-world navigation, cancellation/epoch tests, bounded
tick cost and a combined adapter rollout during an explicitly approved window.
