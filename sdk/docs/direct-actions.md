# Direct action contract — experimental protocol 2

**Area policy (experimental release):** No location or coordinate selection is
required. Omitted/null `area` means unrestricted survival play. Area checks below
apply only to optional owner-selected bounds. Normal survival, account ownership
and human-stop controls remain. This policy is live in the controlled experimental release.

This describes experimental SDK/gateway **0.3.0.dev2** and adapter **0.5.0-dev2**.
The release corrects the preceding adapter's delayed-dig cancellation defect.
Partial effects before cancellation still remain; inspect authoritative outcomes.
Consult [release verification](verification.md) for exact build evidence and
remaining acceptance gates.

See the [completion checklist](api-completion-checklist.md) for acceptance evidence
and unresolved release gates. The gateway forwards single operations; task planning
belongs in the player's agent.

## Submission and authority

HTTP `POST /v1/actions` and WSS `POST /v1/actions` use the identical JSON body:

```json
{"id":"movement_request_0001","op":"move_to","target":[1.5,64,2.5],"body_epoch":"observed-epoch","ttl_seconds":30}
```

IDs are 16–80 ASCII letters/digits/underscore/hyphen. TTL is an integer 1–30
seconds, independent of the renewable 30-second lease. Every request checks the
current whitelist UUID, body ownership, lease, human-stop state, observed epoch
and advertised capability. Coordinates must be finite and within ±30000000;
block coordinates are integers. Unknown fields are rejected. Work areas use an
inclusive minimum and exclusive maximum, in the registered dimension. Native
execution rechecks reach, line of sight, loaded chunks and work-area permissions;
long-running work revalidates while executing. Container transfers revalidate
the opened container even when the body has moved.

`accepted` proves gateway acceptance only. A bounded queue retains commands until
the native body acknowledges their IDs. Protocol 2 grants carry at most 16 queued
commands, an epoch, work area, renewable 4-tick grant and lease generation. At most
32 commands may be outstanding per body. Looking and navigation are independent;
hand/inventory conflicts return explicit native `hand_busy` failures instead of
silently replacing unrelated actions. New navigation cancels previous navigation.

## Operations and wire fields

All operations below also carry the common fields above. Optional `hand` is
`main` (default) or `off` where listed. Every operation requires its own entry in
`raw_capabilities`; SDK installation is not capability evidence.

| Operation | Additional fields and semantics |
| --- | --- |
| `move_to`, `look_at` | `target:[x,y,z]`; navigation does not implicitly mine or place |
| `select_slot` | `slot:0..8`, hotbar index |
| `swap_hands` | Exchange selected main hand and offhand stacks |
| `drop` | `slot:0..40`, `count:1..99`; exact amount, explicit inventory slot |
| `jump`, `sneak`, `sprint` | `enabled:boolean`; held request, released by stop/grant loss |
| `dig` | Integer `target`; selected tool, real break progress/durability/drops; no implicit walk |
| `place` | Integer destination `target`, `face:up/down/north/south/east/west`, optional `hand`; support is destination minus face direction |
| `use_item` | Optional `hand`; duration use remains active until finish, release, timeout or cancellation |
| `release_use` | Release held use, including effects such as firing; the original use ends `done/released` and this action has its own receipt. Stop/cancel abort without release effects |
| `use_on` | Block `target` + `face`, or mutually exclusive `entity_id`; optional `hand` |
| `attack` | Integer `entity_id`; vanilla reach/cooldown; success means attack executed, not target killed |
| `chat` | `text`: nonblank, at most220 UTF-16 code units (220 ASCII or110 supplementary Unicode characters); no slash commands, control characters, DEL or formatting control; per-body 2s/global 0.2s limit |
| `open_container` | Integer `target`, optional `face` from the six directions; returns session/revision and slot layout in result details |
| `move_item` | `session_id`, `revision`, `from`, `to`, `count:1..64`; slot refs are `{inventory:"player"|"container",slot:n}` |
| `close_container` | `session_id`, `revision`; release handles safely, including after moving away |
| `craft` | `recipe_id:"namespace:path"`, `count:1..64` recipe executions; optional integer `target` for crafting table |
| `query_blocks` | Integer center `target` + `radius:0..4`, or mutually exclusive `positions` list of 1..64 integer coordinates |
| `query_recipes` | Optional `offset>=0`, `limit:1..64` (default32); result details contain page, total, next offset and supported types |
| `query_inventory` | Explicit `slot`; `inventory:player|container` defaults to player; byte `offset`, `limit:1..16384`, `stack_revision` after first page; container requires session/revision |
| `query_recipe` | `recipe_id`, byte `offset`, `limit:1..16384`, `recipe_revision` after first page; complete descriptor read |
| `cancel` | `action_id`; abort the named active action without cancelling compatible work |
| `stop` | Native receipt-bearing stop for every control channel |

Numeric integer fields reject booleans and fractional values. `entity_id`, recipe
page `offset`, and container `revision` are 0..2147483647. `session_id` is a
nonempty string of at most 80 characters. Recipe IDs have at most 256 characters
and match `[a-z0-9_.-]+:[a-z0-9_./-]+`. Metadata byte offsets are 0..16777216,
default 0; limits default 16384. Nonzero offsets require the corresponding
64-character lowercase hexadecimal revision. Player metadata slots are -1..40;
container metadata slots are 0..255 and must also exist in the current session.

Native placement context resolves the requested destination, including replacing
plants and merging matching slabs. With explicit work bounds, supported vanilla
doors/beds/tall plants check every affected cell; unknown placement/use footprints
fail explicitly. With null area, ordinary native block/mod-item callbacks, bucket
use and bone meal are permitted. Dig uses the held tool and native survival speed
and harvest rules, including slow breaking without harvest drops when the tool
is unsuitable. No automatic tool selection occurs. Player attacks follow the
server PvP setting; disabled PvP returns `pvp_disabled`. A cancelled/failed action
is **not** a rollback of effects that already occurred.

Container player slots are 0–35; container slots come from the opened session,
not menu-global indices. Exact revisions prevent stale transfers. Supported native
menus include storage and vanilla furnace/hopper/dispenser/brewing inventories.
Reviewed block, item and entity menus and machine item/fluid ports have narrower
contracts described in [mod compatibility](mod-compatibility.md); arbitrary menus
are not supported. Slots marked `transfer_supported:false` cannot be transferred.
Optional `open_container.face` selects a native sided item port; omitted preserves
unsided behavior. Create's item drain exposes an item port on horizontal faces,
a fluid-only session when face is omitted, and rejects up/down with
`unsupported_item_port_face`. Selected sides appear as `item_port_face`.
Crafting
supports discoverable vanilla shaped/shapeless crafting recipe implementations,
with real ingredient alternatives, output capacity and remainder handling.

`count` counts recipe executions, not output items. Query metadata before crafting.
Discoverable machine recipes use native world processing and reject direct
`craft` with `machine_processing_required`; discovery does not imply craft support.

## Rejections and native failures

HTTP status codes and WSS response `status` have the same meaning. Gateway
rejections carry `error` (and `retry_after` when rate limited); they do not return
an accepted action handle. These are common recovery categories, not an exhaustive
list of native reasons:

| Status / code | Meaning and recovery |
| --- | --- |
| 400 `invalid_request`, `unknown_action_fields`, `block_coordinates_required` | Correct field types, bounds or shape before submitting |
| 401 `unauthorized` | Obtain valid private credentials; do not retry an invalid token |
| 403 `not_whitelisted`, `outside_work_area` | Identity or scope does not authorize the operation |
| 409 `adapter_upgrade_required`, `body_changed` | Read fresh capabilities/epoch; do not replay an uncertain mutation |
| 409 `request_id_reused`, `action_belongs_to_previous_lease` | An ID cannot describe a different request or cross leases |
| 422 `unsupported_operation` | Operation is not in this gateway's contract |
| 423 `human_stop_requires_resume` | Only deliberate owner resume may clear the stop |
| 429 `rate_limited` | Respect `retry_after`; mutations are not automatically retried |
| 503 `agent_not_observed`, `observation_stale` | Wait for readiness with a bounded timeout |

Once accepted, native `failed` outcomes instead identify execution failures such
as `hand_busy`, reach/visibility checks, stale container revisions or missing
ingredients. Inspect the returned reason and current world state. Executor errors
with `reconciliation_required:true` mean side effects are unknown, not absent.
`capabilities()` reports account policy; a body's `raw_capabilities` reports its
available operations. The HTTP/WSS parity table tests validate all 25 operations,
typed alternatives and rejection shapes, not their in-game correctness.

## Results, cancellation and retry

`GET /v1/action-results` requires ownership but no live lease or fresh body frame.

Optional JSON body `{"action_id":"..."}` returns that result, or explicit
`unknown/result_not_retained`. HTTP and WSS accept the same request. Compact outcomes are also merged into snapshots; full operation payloads are fetched
by ID. Native details are acknowledged once retained, so large pages do not repeat
on every tick. Deferred payloads carry `details_pending` and are not acknowledged
until complete; SDK completion waits for them. Each row has `id`, `body_epoch`, `state`, a native
`reason`, and optional operation-specific fields/tick. Match ID **and** epoch.

| State | Meaning |
| --- | --- |
| `accepted` | Queued, execution not yet proven |
| `started` | Native executor acknowledged beginning work |
| `done` | Native executor completed its defined operation |
| `failed` | Rejected or could not finish; inspect reason |
| `cancelled` | Interrupted; effects before cancellation may remain |
| `unknown` | Result no longer retained; inspect world/inventory before deciding |

Gateway results/idempotency are memory-bound to at most 512 actions per body and
10 minutes from acceptance, also bounded to 8MiB per body (oldest terminal outcomes
may be evicted earlier). Restart loses this history. Exact retries within the
same active lease return the original acceptance; changed payloads or reuse from
another lease fail. Native deduplication prevents resending the queued batch from
executing a mutation twice. Never blindly replay after retention expiry/restart.

Timeout without terminal native evidence reports `failed/outcome_unknown_timeout`;
a subsequent native terminal receipt takes precedence. Disconnect cancellation is
conservative: it is not evidence that no partial side effect occurred.

`DELETE /v1/goal` (SDK `stop()`) cancels queued/active work, rotates the native grant
generation and retains the client lease. `action("stop")` instead supplies a native
receipt. Disconnect, credential/membership revocation, lease expiry, human stop
and body replacement cancel control; grant loss clears held controls and container
state. Human stop persists; only deliberate owner `resume()` clears it. Reconnect
never calls resume. The legacy goal and chat routes fail on realtime bodies with
`use_primitive_stream` / `use_chat_primitive`.

## Observations, bounds and pacing

Fast snapshots include complete inventory slots 0–8 hotbar, 9–35 main, 36–39 armor,
40 offhand and -1 cursor, including explicit empties, counts, durability, components
and inventory revision. `hands`, `selected_slot`, `execution`, container session
state and action results accompany health/position. Entities are the nearest 64
within a 16-block bounding region, with runtime IDs, type, position, velocity,
visibility and relevant state; IDs are short lived. `entity_range` describes the
bounding query distance and `entities_truncated` reports the result cap; an absent
entity is not proof that no such entity exists. No unrelated chest inventory
appears before an authorized open session.

Block queries are within 32 blocks and do not generate chunks. They distinguish
unloaded cells from air and return properties/dimension/tick; query details are
also retained as `queried_blocks`. Recipe summaries are paginated on demand. Oversized ingredient summaries are
explicitly marked; `query_recipe` retrieves the complete descriptor. Both full
reads return UTF-8 JSON in Base64 byte chunks, pin a SHA-256 revision, and cap a
single full result at 16MiB. Inventory revision hashes the UTF-8 item ID, NUL,
count, NUL and component bytes; recipe revision hashes its descriptor bytes.
Continuation with a changed revision fails explicitly. Container reads retain
session, revision, reach and area checks. SDK `inventory_slot()` / `recipe()`
reassemble and verify pages with an overall timeout (default30s) and size ceiling
(default4MiB, configurable through16MiB); they never silently retry changed data. `public_chat`
contains the bounded public message history with IDs/speaker/time; private login
codes and private commands are not this stream. SDK chat subscriptions deduplicate
IDs but cannot recover messages lost beyond the bounded history.

Snapshots use latest-state backpressure, not a durable event log. The SDK reports
sequence gaps/resync and observation age, clears stale state after reconnect/epoch
change, and separates fast frames from slower terrain data. Global authenticated
request minimum is 5ms; SDK WSS sends are paced to 6ms, without automatically
retrying rejected mutations. A stop send does not wait behind another request's
acknowledgement. `429` and retry timing remain visible. In-game acceptance and
performance evidence belong to the checklist, not transport-only tests.

`world_tick` is Minecraft world game time and matches native action/query tick
fields. Outer `tick` is the adapter snapshot sequence, not world time.
`average_tick_ms` is the rolling native average over up to 100 server ticks;
it measures server tick cost, not network or action-completion latency.
Unexpected native executor exceptions report `outcome_unknown_executor_error`
with `reconciliation_required:true` and `side_effects:"unknown"`; inspect the
world and retained outcomes before deciding whether another action is appropriate.

Deferred native result payloads count toward the 32-outstanding-action limit until
fully received. They terminate with `result_details_timeout` if delivery exceeds
the action deadline; stop clears the pending marker immediately. A later complete
native receipt can supersede that conservative outcome. Native results remain
eligible for delivery until acknowledged, even outside the latest-64 window.
Following a gateway restart, complete native outcomes may be recovered with
`recovered:true`; their original request payload and lease are unknown, so replay
is not authorized. Already-compacted or expired outcomes remain explicitly unknown.

## Experimental transport changes (0.3.0.dev2)

The public WebSocket pushes the latest 64 receipt transitions plus every
unfinished or deferred result. `action_results_truncated` reports when retained
history exceeds that push window. A long-running action's new terminal transition
returns to the recent window even after many newer actions. Full results remain
available by ID under the existing 512-row, 8 MiB, ten-minute bounds. SDK handles
reconcile a missing result once when truncation is explicit; they never replay it.
Native ACKs are pruned only after same-epoch compact-receipt confirmation.
Body notifications target that body's waiters; authority still renews/rechecks
within the 100 ms heartbeat. These changes do not establish ten-body readiness; the measured acceptance
targets remain governed by the verification report.
