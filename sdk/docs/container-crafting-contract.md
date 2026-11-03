# Container and crafting contract (development candidate)

**Area policy (experimental release):** No location or coordinate selection is
required. Omitted/null `area` means unrestricted survival play. Area checks below
apply only to optional owner-selected bounds. Normal survival, account ownership
and human-stop controls remain. This policy is live in the controlled experimental release.

This describes the candidate Java implementation, not an assertion that the live
server has these actions. The [completion checklist](api-completion-checklist.md)
remains the release authority; native test evidence is required before checking
ACT-13–16 or OBS-05–06.

## Containers

`open_container` takes an integer block `target: [x,y,z]`. The block must be
loaded, reachable with line of sight, inside the current work area and accessible
under native opening rules. Both halves of a double chest must be inside the
area. Opening replaces the previous session. The response returns `session_id`,
`revision`, position, dimension, block, cursor, and every player/container slot.

Supported native menus are chest (including double chest), barrel, shulker box,
furnace/blast furnace/smoker, hopper, dispenser/dropper, and brewing stand.
Other menus fail with `unsupported_container`. The separate development
`machine_item_port` path supports reviewed Create depot, basin and millstone
native item handlers; see [mod compatibility](mod-compatibility.md) for slot
rules, pending full-pack acceptance and processing limits. Native locks, blocked lids, slot rules and furnace extraction hooks
apply. Opening follows native block interaction, including statistics and any
piglin reaction.

`move_item` requires the current `session_id` and `revision`, plus `from`, `to`
and `count` (1–64). References have the form
`{"inventory":"player","slot":0}` or
`{"inventory":"container","slot":0}`. Player slots are the stable vanilla
inventory indices 0–8 (hotbar) and 9–35 (main inventory). Container indices are
the menu's non-player slots in order, as returned by the open observation.
Equipment and the cursor are not transfer targets in this action.

Counts are exact: insufficient source items, incompatible components, prohibited
slots and insufficient destination capacity fail before mutation. This API does
not silently reduce the requested count. Native slot extraction and insertion
are used. The same item ID with different components is not a compatible stack.
Every transfer rechecks current authorization, range, line of sight, container
identity and menu validity. A revision changes when any observed menu stack
changes, including a change from another viewer or a furnace. Reacquire the
observation after `stale_container_revision`; do not blindly retry mutations
whose completion is uncertain.
Unexpected native/mod exceptions after execution begins are reported as an
unknown outcome requiring observation and reconciliation. They are not ordinary
preflight rejections and must not trigger an automatic mutation retry.

`close_container` requires the current session and revision but does not require
remaining within reach. It invalidates the session and invokes native menu
cleanup, which safely returns or drops any cursor stack. Stop/disconnect/death
cleanup must call the helper's unconditional close path. Closed observations
include the last `closed_session_id` and `reason`; they do not expose storage
contents. Slot roles include storage, input, fuel, output, bottle, ingredient,
hotbar and main. Stack observations include explicit empty stacks, counts,
capacity, durability and persistent components encoded with the registry codec.
Ambient component JSON is capped at 2 KiB per stack. Larger metadata is omitted
and explicitly marked `components_truncated`, with `component_bytes` and a
`components_sha256` fingerprint. This preserves identity comparisons, not access
to omitted attributes. Durability/count fields remain available. A bounded
single-slot full-component query is available as described below. Transactions
always compare actual complete native components regardless of the ambient cap.

### Full single-slot inventory metadata

`query_inventory` reads one slot: `inventory: "player"` (default), `slot: 0..40`
or `-1` for the carried cursor stack. `inventory: "container"` uses the container
slot indices and additionally requires a current `session_id` and `revision`.
Container access checks run on **every** page, including range and current work
area. Reading a slot does not acquire or move any item.

Persistent component JSON is transferred as UTF-8 bytes encoded in Base64, in
chunks of up to 16 KiB (`limit`, default 16384). Each response includes a basic
`stack` row, `stack_revision`, `components_chunk`, `offset`, `total_bytes` and an
optional `next_offset`. The revision fingerprints the complete components,
item ID and count; every subsequent page must send it. A changed stack fails
with `stale_inventory_revision` instead of combining two different snapshots.
The native query supports up to 16 MiB of component JSON per stack and rejects
larger metadata explicitly. The raw byte protocol safely handles Unicode split
across chunk boundaries.

The SDK's `inventory_slot(slot, inventory="player", ...)` hides pagination,
validates the body and stack revisions, decodes the component JSON and returns
the full stack row with `components`. Its default download budget is 4 MiB and
can be increased with `max_bytes` within the native bound. Pass the current
session and revision for a container slot. Read failures do not automatically
replay mutations or silently combine stale pages.

## Recipes

`query_recipes` returns supported grid recipes and known native processing recipe
metadata in ID order. `craft_supported` and the legacy `supported` flag describe
direct grid crafting; processing recipes use `execution: "native_world_ticks"`
and include serializer-preserved `native_recipe` metadata. `supported: false`
does not prohibit the native machine route. Supply `offset`
(default 0) and `limit` (default 32, maximum 64); follow `next_offset` until
absent. Each recipe describes ingredient alternatives, representative remainder
items, output, grid dimensions and workstation. Ingredient alternatives are
descriptive; the native ingredient predicate and native recipe matching decide
whether actual stacks are valid. Recipe pages are explicit queries rather than
per-tick broadcasts.
Pages also enforce a 96 KiB metadata budget, so they can contain fewer entries
than the requested limit. A single recipe whose ingredient metadata exceeds that
budget reports `ingredients_truncated` and omits the alternatives. Retrieving
the complete metadata uses `query_recipe` or the SDK helper below.

`query_recipe(recipe_id, offset=0, limit=16384, recipe_revision=...)` transfers
the complete single-recipe descriptor, including all ingredient alternatives
and full output/remainder components. It returns `recipe_chunk` as Base64 UTF-8
JSON bytes, `encoding: "utf-8/base64"`, `recipe_revision` (SHA-256 of that JSON),
`offset`, `total_bytes` and optional `next_offset`. Later pages require the
matching revision; changed metadata fails with `stale_recipe_revision`. The
same 16 KiB chunk / 16 MiB total bounds apply. `recipe(recipe_id, ...)` in the SDK
handles paging, validates the byte hash and returns the decoded descriptor with
a default 4 MiB download budget. This provides a complete read path when catalog
summaries omit unusually large ingredients or components.

`craft` takes `recipe_id` and `count` (1–64 **recipe executions**, not output
items). Supported implementations are ordinary shaped and shapeless crafting
recipes that fit a 3×3 grid. Recipes fitting 2×2 use the player's crafting grid;
larger recipes require a reachable crafting table within the current work area.
An optional `target` selects that table explicitly. Known machine recipes fail
with `machine_processing_required`; other unsupported special recipe
implementations fail with `unsupported_recipe_type`. An absent ID fails
with `unknown_recipe`, and missing inventory inputs with
`insufficient_ingredients`. Restricted crafting rules still apply.

The implementation matches ingredients against real stack components using a
bounded matching algorithm, assembles the native recipe and obtains its native
remainders. It simulates the complete batch against a copy of all 36 inventory
slots before committing. Missing inputs or insufficient output/remainder space
leave the original inventory untouched. Successful crafting fires native
crafting events, statistics and recipe awards. Count is recipe executions even
when a recipe produces four planks or several sticks. Outputs and all remainders
must fit; ordinary capacity failure does not drop items on the ground.

## Native acceptance cases

Use the current native verification report to identify passing cases and gaps;
the list below defines verification dimensions rather than claiming they all pass.

- Single and double chests; the second half outside the area; blocked and removed
  containers; moving out of range; owner stop and disconnect cleanup.
- Competing viewer changes and stale revisions; partial stacks and partial furnace
  outputs; named, enchanted or damaged stacks; incompatible component rejection.
- Planks (one log yields four), mixed wood chest ingredients, full inventory and
  an insufficient-ingredient batch. Verify failure leaves every slot unchanged.
- Cake at a table (three milk buckets become three empty buckets), including
  insufficient remainder space, and unsupported machine/special recipe IDs.
- No unrelated container contents appear without an authorized active session.

`IngredientAssignmentTest` independently compares the matcher against a brute
force oracle over 13,824 small matching/stock combinations. This is algorithm
evidence and does not substitute for the native integration cases above.
