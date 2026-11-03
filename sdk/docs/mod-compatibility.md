# Industrial pack compatibility — development acceptance

The installed pack is Minecraft **1.21.1 / NeoForge 21.1.265**, with the 25 public
mods pinned by [pack.lock.json](../../pack.lock.json). A read-only server inventory
matched all 25 locked filenames; the adapter is an additional server mod. The
Create 6.0.10 jar inspected has SHA-256
`ef87fe5709f1ba1f5b8bb20a2925b5afb4669e178fd6d8bf10c167759eefe37a`.
The isolated full-pack harness verifies each input jar against its locked SHA-512
and uses a fresh world and default configuration. It never copies player worlds,
authentication data or private configuration.

**Status:** the machine ports, recipe metadata and reviewed mod menus below are
development implementations. Each native fixture needs its own passing evidence
before compatibility is claimed. Existing
vanilla fixture results do not establish mod compatibility. This document adds
concrete industrial acceptance cases to the existing
[40-item checklist](api-completion-checklist.md); it does not replace that list
or mark its items complete.

## Native machine contract

`open_container(x,y,z)` also opens an explicit `kind: "machine_item_port"`
session for the reviewed blocks below. It does not fabricate a graphical menu.
The existing `session_id`, `revision`, `move_item`, `query_inventory` and
`close_container` wire formats apply. The native NeoForge `IItemHandler` decides
insertion, extraction, capacity and item validity; simulation precedes an exact
transfer. Neither `setStackInSlot` nor recipe assembly is used to create machine
output. Current reach, line of sight, optional area bounds, block-entity identity
and capability identity are checked on every access. Native processing or a
competing transfer changes the session revision.

| Block | Native slots and rules | Candidate status |
| --- | --- | --- |
| `create:depot` | 0 held/input; 1–8 output buffer. Only slot0 accepts insertion; native merge restrictions apply. | Implemented, full-pack test pending |
| `create:basin` | 0–8 input; 9–17 output. Native first-empty and duplicate-input rules apply; output insertion is rejected. | Implemented, full-pack test pending |
| `create:millstone` | 0 input; 1–9 outputs. Only valid milling inputs may enter slot0. Native automation cannot extract slot0; the API preserves that rule. | Implemented, full-pack test pending |

Machine sessions expose items, not fluid tanks or kinetic telemetry. A successful
transfer means the items moved; it does not mean a recipe completed. Observe
actual output after native powered ticks. Stop closes access and stops the body;
an independently powered machine can continue running normally in the world.
Unhandled machine ports are explicitly rejected until their native interaction
contract is implemented and tested; this is a per-operation limitation, not a
claim that the entire mod is unsupported.

`query_recipes` and `recipe(recipe_id)` distinguish `craft_supported: true`
grid recipes from `execution: "native_world_ticks"` processing recipes.
The legacy descriptor `supported` means **supported by direct `craft`**; `false`
does not mean that a machine cannot perform the recipe. Machine descriptors
include the native serializer's `native_recipe`, preserving fluid amounts,
probabilistic outputs, heating, durations and sequences instead of reducing
everything to a deterministic item recipe. Oversized catalog entries are marked
`metadata_truncated`; the full single-recipe paging path remains available.
Calling `craft` on a known processing recipe fails `machine_processing_required`.
This prevents instant, power-free output generation.

Metadata covers installed ordinary furnace/smoker/blast-furnace/campfire recipes,
Create pressing, mixing, compacting, milling, crushing, cutting, fan processing,
filling, emptying, deploying, mechanical crafting and sequenced assembly, and
Farmer's Delight cooking/cutting. Discovery alone does not prove that the body
can yet operate every listed workstation.

### Reviewed native menus

The next candidate also adopts menus opened by the mod's actual interaction,
without constructing a replacement provider or accessing its inventory directly:

- Sophisticated Storage chest/barrel/shulker menus use their native storage
  slots, including native capacity, item validation and upgrade slot-change hooks.
  Configuration, upgrade recipe and ghost slots are explicitly marked
  `transfer_supported: false`; they are not ordinary item storage. Linked-storage
  sessions with an explicit work area reject until remote affected bounds can be
  established. Native linked access without an area is not thereby certified.
- A held Sophisticated Backpack opens through `use_item`. The resulting
  `kind: "item_menu"` session uses native backpack context and `stillValid` to
  invalidate item replacement. This is not yet a worn-backpack keybind API.
- Farmer's Delight cooking-pot slots 0–5 are ingredients, 6 is a non-extractable
  meal preview, 7 is the serving-container input and 8 is the native result slot.
  `open_container` requires an empty main hand and no sneaking, so opening cannot
  accidentally serve a meal or change the pot handle. Heat, real ingredients,
  serving containers and native result extraction determine the output.
- Corpse opens through `use_on(entity_id=...)`, after the mod performs its own
  owner/operator/skeleton checks. `kind: "entity_menu"` binds the actual entity
  identity and rechecks range, line of sight, native validity and optional area
  on subsequent reads/transfers. History copies and read-only menus cannot be
  item sources. These are the actual corpse slots, not restored inventory copies.

All three session kinds retain the existing session/revision and transfer wire
format. The new workstation fixtures cover base storage component roundtrips,
portable backpack invalidation, native heated cooking and native cutting with
tool wear. The full-pack lifecycle fixture recovers actual corpse contents and
components instead of assuming death produces loose vanilla item entities.
Nonowner corpse denial, worn backpacks, upgrade configuration and advanced
storage behavior remain separate pending acceptance cases.

## Required industrial acceptance cases

These IDs make the existing checklist's “actual installed mods” requirement
reviewable. They are **pending** until linked native evidence passes. Infrastructure
seeded by a fixture must be recorded separately from agent-crafted infrastructure.

| ID | Exact acceptance | Checklist links |
| --- | --- | --- |
| MOD-01 | Place and retrieve reviewed Create blocks using actual held items; orient shafts/cogs/gearboxes, use a crank, rotate with a wrench, and recover by native sneak-wrench interaction. Check counts, drops and optional-area boundary failures, including custom BlockItem placement helpers. Construct a waterwheel that derives power from real flowing water. | ACT-08, ACT-10, VERIFY-02/03/06 |
| MOD-02 | Load a real depot and press one iron ingot into one iron sheet; load a real basin and mix one andesite + one iron nugget into one alloy. No power means no output. Native power produces output; SDK extracts it. Record input/output counts and revision changes. Motor-seeded tests prove processing only; survival-built power remains a separate MOD-01 requirement. | ACT-13/14/15, OBS-05/06, VERIFY-03/06 |
| MOD-03 | Run two fresh 16-wheat batches through a powered millstone, record actual flour and seed rolls, preserve every byproduct, craft dough with actual water-bucket remainders, refill through native use, cook dough in a fueled furnace and deposit 32 bread. Full journey uses a waterwheel built by the agent. No pre-existing output, injected energy or inferred success in the survival evidence. | ACT-08/10/13/14/15, OBS-05/06, VERIFY-02/03/06 |
| MOD-04 | Depot/basin/millstone ports reject invalid input/output transfers, obey exact counts and native component comparisons, invalidate removed/out-of-range/bounded-area sessions, and reject revisions changed by processing or another body. Reconcile disconnects without replaying mutations. | ACT-13/14/16, OBS-01/05, EXEC-02/04, VERIFY-03 |
| MOD-05 | Sophisticated Storage chest/barrel and worn/held Sophisticated Backpack: discover actual compartments, transfer components and high-capacity stacks, obey filters/locked slots/ownership, close/reconnect safely, and account for upgrade side effects. No raw capability bypass of menu or per-player checks. | ACT-10/13/14/16, OBS-01/05, VERIFY-03/06 |
| MOD-06 | Farmer's Delight pot: real heat + ingredients + serving container yield a meal, preserve containers and slot restrictions. Cutting board: insert ingredient, use appropriate real tool, account for durability, drops and probabilistic output. Recipe metadata must describe both operations. | ACT-10/13/14/15, OBS-05/06, VERIFY-02/03/06 |
| MOD-07 | Lootr: a permitted body opens its own per-player loot inventory without taking another player's loot or bypassing fake-player restrictions; denied interaction is explicit and unchanged. Corpse: recover authorized owner items after native death, preserving components and enforcing ownership/time rules. | ACT-10/13/14/16, OBS-05, VERIFY-03/06 |
| MOD-08 | Steam 'n' Rails: place supported track/control components with correct multi-cell boundaries; native station/controls interaction, schedule handling and riding preserve survival/ownership/stop semantics. Scope and lifecycle of moving contraptions must be explicit before claiming train control. | ACT-08/10/13/14, OBS-05, VERIFY-02/03/06 |
| MOD-09 | Fluid-processing route: observe tank type/amount/capacity; use real buckets or audited fluid handlers without duplication; prove a heated/fluid basin recipe, spout filling and drain emptying with conservation. Fluid-only recipes remain discoverable before this route is implemented. | ACT-10/13/14/15, OBS-05/06, VERIFY-03/06 |
| MOD-10 | Run the complete primitive/native-survival suite with the exact locked server pack, including seasonal farming and difficulty effects, then repeat concurrency/latency checks under the installed performance mods. | VERIFY-02/03/06, OBS-07 |

The local `container_gameplay_cases.py` includes unrun Create depot, powered
press, powered mixer, and two-batch millstone cases guarded by `--full-pack-mods`.
The millstone case records all flour/seed rolls, crafts one dough with its real
empty-bucket remainder, and bakes one bread in a fueled furnace. This is not the
32-bread waterwheel survival journey. The isolated fixture
seeds native motors and machine infrastructure and never seeds their outputs.
Concurrent native-viewer and disconnect/reconciliation cases also remain subject
to their separately recorded run results; two agent menus are not evidence of a
human GUI test.

## Installed mod inventory and outstanding work

| Installed mod/version | Current compatibility boundary and next verification |
| --- | --- |
| Create 6.0.10+mc1.21.1 | Candidate depot/basin/millstone ports and native recipe metadata above; placement/use and full survival power chain pending MOD-01–04/09. Other machine handlers need per-workstation audit. |
| Steam 'n' Rails 0.2.1+neoforge-mc1.21.1 | Planned MOD-08; train/contraption controls are not covered by block inventory operations. |
| Farmer's Delight 1.21.1-1.3.4 | Candidate cooking/cutting metadata and native pot menu; real heat/serving and board/tool fixtures pending MOD-06. |
| Sophisticated Storage 1.6.11.2211 | Candidate reviewed native menus; base roundtrip fixtures pending. Advanced upgrades/linked storage acceptance remains MOD-05. |
| Sophisticated Backpacks 3.26.18.2235 | Candidate native held-item menu; context/components fixture pending. Worn opening and upgrades remain MOD-05. |
| Sophisticated Core 1.5.21.2439 | Shared native slot/upgrade implementation must be audited with both storage mods. |
| Lootr 1.21.1-1.11.38.127 | Planned per-player access MOD-07. Installed config disables fake-player breaking; do not override it or expose shared underlying inventory. |
| Corpse 1.1.22 | Candidate native entity-bound recovery sessions and full-pack death/recovery fixture MOD-07; denial/history cases remain pending. |
| Supplementaries 1.21.1-4.0.2 | Unverified native interactions; identify storage/automation blocks used in the survival journey and audit their menus and affected cells before claiming support. |
| Moonlight 1.21.1-3.7.2 | Library; verify Supplementaries integration in the full pack. |
| Serene Seasons 10.1.0.9 | Native crop/season behavior; record season and actual harvest/regrowth in MOD-10, not a vanilla farming assumption. |
| GlitchCore 2.1.0.2 | Library; full-pack startup and season integration verification. |
| Better Difficulty 1.1.1 | Native combat/survival effects; full-pack survival validation, no immunity or hunger overrides. |
| Terralith 2.6.2 | Native terrain; real generated-terrain navigation remains separate from flat fixtures. |
| Lithostitched 1.8.1-neoforge-21.1 | Worldgen library; same generated-terrain requirement. |
| Lithium 0.15.4 | Full-pack behavior/performance regression checks; vanilla-only timing is insufficient. |
| FerriteCore 7.0.3 | Full-pack startup/memory and functional regression checks. |
| ModernFix 5.27.27 | Full-pack startup/performance and native behavior regression checks. |
| Chunky 1.4.23 | Operational tooling, no player primitive route required; do not start production pregeneration for tests. |
| Spark 1.10.124 | Observability tooling; profiling is separate from gameplay support. |
| LuckPerms 5.4.150 | Native permission denials must remain effective; full-pack access tests. |
| Simple Voice Chat 2.6.22 | No SDK voice support claimed; fixture binds its service to loopback/separate port. |
| JEI 19.64.0.455 | Client recipe UI is not the SDK API; server recipe serializers supply metadata. |
| MezzConfig 0.6.10 | JEI dependency; full-pack startup check. |
| Jade 15.10.6 | Client inspection overlay is not raw server observation evidence. |

## Pinned implementation evidence

Create's exact [6.0.10 release](https://github.com/Creators-of-Create/Create/releases/tag/mc1.21.1-6.0.10)
and installed jar were inspected. The native contracts are defined by its
[depot handler](https://github.com/Creators-of-Create/Create/blob/mc1.21.1-6.0.10/src/main/java/com/simibubi/create/content/logistics/depot/DepotItemHandler.java),
[basin inventory](https://github.com/Creators-of-Create/Create/blob/mc1.21.1-6.0.10/src/main/java/com/simibubi/create/content/processing/basin/BasinInventory.java),
and [millstone](https://github.com/Creators-of-Create/Create/blob/mc1.21.1-6.0.10/src/main/java/com/simibubi/create/content/kinetics/millstone/MillstoneBlockEntity.java).
Native processing, not an SDK recipe shortcut, determines chance outputs and
power/heat requirements. Actual installed settings retain stress, disable bulk
pressing/cutting, and enable mixer/crafter adaptations of applicable vanilla
recipes. Fresh-default fixtures must record their configuration and must not
silently claim to reproduce different production settings.
