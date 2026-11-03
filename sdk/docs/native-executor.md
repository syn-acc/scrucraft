# Native executor contract (candidate)


**Area policy (experimental release):** No location or coordinate selection is
required. Omitted/null `area` means unrestricted survival play. Area checks below
apply only to optional owner-selected bounds. Normal survival, account ownership
and human-stop controls remain. This policy is live in the controlled experimental release.


This document describes the staged protocol-2 executor. Deployment and checklist

acceptance are recorded separately; source availability does not establish that

all gameplay and failure fixtures have passed.



The body is a survival `ServerPlayer`. Inventory, health, damage, break timing,

drops, item use and placement run through Minecraft methods on the server thread.

The socket reader only replaces the latest authorization grant; it never touches

the world. The gateway sends `kind: controls`, `body_epoch`, `lease_id`, `area`,

`commands`, and `valid_for_ticks: 4`. A grant older than 200 ms cannot execute.

Changing or removing the lease cancels active work and closes inventory sessions.

Realtime bodies do not perform hidden automatic eating, including while stopped;

clients must select and use real food. Vanilla survival still ticks normally.

The legacy goal-controller mode retains its existing survival food policy.



## Action channels and outcomes



`move_to` replaces only navigation. `look_at` keeps navigation running and rotates

local movement inputs into the selected gaze direction so looking does not steer

the route. `dig` and duration-based `use_item` occupy the hand channel. Selection,

swapping, dropping, placing, attacking and inventory transactions reject with

`hand_busy` during either action. Movement can continue alongside a hand action;

reach and authorization are checked every tick and may fail that action.



Each result includes `id`, `body_epoch`, `state`, `reason` and game `tick`.

`started` describes ongoing work; `done`, `failed` and `cancelled` are terminal.

The native executor keeps a rolling 512-entry history, evicting only outcomes
already acknowledged by the gateway. Snapshots offer every unacknowledged outcome
plus the recent 64 entries and active actions. Gateway admission bounds unfinished
commands, including results still waiting for full payload delivery. Every result
update moves the ID to the most recent position. The gateway acknowledges fully retained terminal payloads, allowing the

body to keep a compact native result. Each frame has a 512 KB result budget with

rotating priority; deferred details are explicitly marked. A single read-query

result exceeding 400 KB fails with `query_result_too_large`; request a smaller

page or radius. Exact retransmissions (ignoring the decreasing delivery `timeout_ticks` budget)
resurface the existing result without executing

again. The gateway enforces payload identity and manages reconnect reconciliation;

clients must not retry mutations under new IDs to resolve uncertain outcomes.



`cancel(action_id)` cancels the named running action. Cancelling an already

terminal action succeeds with `already_terminal`; an absent ID reports

`unknown_action`. `stop` cancels navigation/dig/use, clears gaze and movement

inputs, releases jump/sneak/sprint and closes the container session. Stopping item

use aborts it; only explicit `release_use` invokes release behaviour such as firing

a drawn bow. A completed `attack` means an attack was executed, not that it killed

or necessarily damaged the target.



## Coordinates, inventory and interactions



Block coordinates are integer `[x,y,z]` triples. Area bounds are minimum inclusive,

maximum exclusive and carry an exact dimension ID. Checks reject unloaded chunks

and world-border/build-height violations without loading terrain.



`place` names the **destination**, while `face` is the clicked face of its adjacent

support (`destination - face`). Both support and destination must lie inside the

area. The held block is used without automatic tool selection. Vanilla doors,

beds and double plants additionally validate their second cell before placement.

Unknown modded footprints and scaffolding reject with

`unsupported_placement_footprint`. Replaceable support is rejected because vanilla

would redirect placement to that support cell. Native collision and survival

placement rules still apply. A rejected native hook can return `placement_rejected`;

read world/inventory observations to resolve mod-specific effects. Unexpected

native/mod exceptions report `outcome_unknown_executor_error` with

`reconciliation_required: true` and `side_effects: unknown`. Only preflight

validation failures promise that no operation was attempted; an exception does

not prove atomic rollback. Do not replay uncertain mutations automatically.



`dig` uses the currently selected tool and real vanilla start/stop destruction.

It reports `broken` only after observing the body's break event and removal of

the target. Unbreakable blocks, insufficient harvesting tools, changed targets,

out-of-reach targets and tool changes fail explicitly. It never walks or selects

a tool implicitly.



Hotbar slots are 0–8; main inventory 9–35; armor 36–39 (feet to head); offhand 40.

The observed cursor has slot -1 and cannot be passed to `drop`. `drop(slot,count)`

first checks the native inventory slot pickup rule (including Binding Curse),

then spawns an exact copied quantity and decrements the real source stack; retries

reuse the existing result. `swap_hands` preserves whole item components.



`jump(enabled)` is held jumping: while enabled it jumps whenever grounded, in

addition to navigator step jumps. `sneak(enabled)` applies native sneaking and

reduces movement input. `sprint(enabled)` records intent; actual sprinting also

requires forward input, sufficient food, no sneak/use and no horizontal collision.

Stop or lost control clears every request.



`use_item(hand)` accepts `main` (default) or `off`; instant interactions complete

immediately, duration-based use starts and completes when native use ends.

`release_use` explicitly releases a held use. Buckets and block items are rejected

by the generic air-use call because their world-write footprint needs a targeted

operation.



`use_on` accepts either `entity_id` or a block `target` plus `face`, and an optional

hand. It validates line of sight, reach and work area. Block-entity and workstation menus require

`open_container` (unsupported workstation types fail explicitly); block/bucket/bone-meal use on blocks is rejected because the

executor does not promise bounded arbitrary growth or fluid writes. Vanilla door

interaction checks both halves. Entity interaction uses vanilla `interactOn`. Interactions that open an

untracked entity menu, such as trading, are immediately closed and fail with

`unsupported_entity_menu`; trading and workstation processing are not promised.

`attack(entity_id)` requires a live target, clear sight, range within three metres

from eye to target centre and a fully replenished cooldown. Players are valid

only when server PvP is enabled; native damage/team rules remain applicable.



`chat(text)` broadcasts a public, attributed system message (not signed client

chat), adds it to the public-chat observation and returns `delivered`. Text is

1–220 characters with no slash-command prefix/control/formatting characters;

there is one message per body per 40 game ticks. Private login codes and whispers

never enter this public-message collector.



## Observations and queries



Fast frames include every inventory slot and cursor, explicit empty stacks,

structured persistent item components, durability, inventory revision, selected

slot, hands and requested/actual movement state. Components over 2,048 encoded

bytes are omitted with `components_truncated`, `components_sha256` and

`component_bytes`; native stack comparisons/transfers still preserve their full

values. Use `query_inventory` to retrieve full components in bounded byte pages with a

pinned stack revision; a changed stack rejects further pages rather than mixing

versions. SDK helpers decode and assemble the component JSON. Entity snapshots include up to

64 nearest live entities within a 16-block bounding-box expansion, including

players, ordinary mobs and dropped stacks. IDs are ephemeral and valid only for

the current world/body context. Entity inventory/private chat is never disclosed.



`query_blocks` accepts a centre `target` and radius 0–4, or up to 64 explicit

`positions`. Each requested cell must be within 32 blocks of the body. Rows carry

position, dimension, world game tick and `loaded`; loaded rows include block ID,

properties, replaceability and hardness. An unloaded row omits block state rather

than pretending it is air. Query/action ticks use world game time, matching snapshot `world_tick`; outer

snapshot `tick` is the adapter sequence. Use the body epoch and capture timestamps

for stream freshness across restarts. The result contains `blocks`; the last query is also

included in slow `queried_blocks` snapshots.



Container snapshots expose only an authorized active session. `query_recipes` is

an explicit paged discovery helper; `query_recipe` reads a full individual recipe

descriptor in revision-pinned byte pages through SDK `recipe()`. The entire recipe book is not broadcast

every tick.

`average_tick_ms` is the Minecraft server's rolling mean of up to 100 tick costs

(in milliseconds), not network round-trip time. `execution` includes active IDs,

use ticks and break progress. Progress is an

estimate from native hardness and elapsed ticks; terminal action outcomes are the

authority for completion. Public chat retains the last 24 identified messages;

consumers deduplicate by message ID, and reconnect may have gaps.
