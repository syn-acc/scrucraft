# API coverage and remaining acceptance work

Reviewed 2026-11-03. This matrix tracks **all 40 existing items** in the
[authoritative checklist](api-completion-checklist.md); it does not replace or
narrow their requirements. The checklist currently checks eight items. “Implemented”
below means code exists, not that all acceptance criteria passed or that a new
development change is deployed. Unverified means the cited evidence does not
establish the criterion, not necessarily that the implementation fails it.

The controlled live checkpoint is SDK/gateway **0.3.0.dev1**, adapter
**0.5.0-dev1**. [Run 05][r5] passed 44 isolated native cases and **failed** the
ten-body load test. Subsequent **0.3.0.dev2** gateway/SDK optimizations have local
tests and a [synthetic transport experiment][bench], but no successful native
five-minute performance result. PLAYER reports successful Jamie_Syn in-game code
enrollment; Architect's [first real session](verification.md#controlled-single-body-checkpoint)
performed navigation, natural gathering, grid crafting and placement. That advances
SDK-01/VERIFY-02, but does not establish the complete helper/gameplay/failure
journeys. Fixture administrator tokens remain separate synthetic evidence.

**Live correctness finding:** [live dig evidence][dig] and the source audit
in [verification][verify] identify a native delayed-breaking hazard. An early STOP
packet can schedule destruction that ABORT does not clear, allowing a block change
after `failed` or `cancelled`. Candidate [run 07](evidence/api-fixture-run-07.json)
now verifies the native correction for pickup, cancel, owner/administrative stop,
lease release and grant expiry, waiting 90 native ticks for later effects. This
is not deployed, and actual human-chat delivery remains unverified. Complete
ACT-07 and EXEC-02/03/04/06 criteria still apply. Live failed digs must not be blindly
retried. The eight already checked items remain checked in this matrix; this is
not a new declaration that affected release-level requirements are complete.

## Execution contract

| ID / checklist state | Implementation and evidence | Exact unmet or unverified acceptance | Next concrete action |
| --- | --- | --- | --- |
| **EXEC-01 — checked** | Separate navigation/look and hand/inventory channels; conflicts have explicit results. [Run 04][r4] `flat_navigation_while_looking`, `dig_hand_channel_and_explicit_cancel`; [contract][contract]. | No additional gap asserted for this item's checked independence criteria. The separate dig-abort defect remains under EXEC-03/ACT-07. | Retain moving-plus-looking and held-item-conflict regressions when changing the native executor. |
| **EXEC-02 — open** | IDs and epochs connect accepted/started/terminal states; bounded delivery queue, native deduplication, deferred payload handling and TTL fallback. [Queue tests][queue], [backpressure tests][backpressure], [Run 05][r5] long-action recency, reduced-timeout retry and withheld-payload cases. | Dig failure/cancellation may precede an unreported mutation. Run 05 also timed out an accepted action under load; no successful sustained proof exists. Dev2 receipt-window changes have not run against Minecraft. | Fix and exercise the delayed-break race; run native rapid replacement/cancel and lost/late-result cases with dev2; prove every accepted ID reaches a truthful terminal or explicit unknown outcome. |
| **EXEC-03 — open** | `cancel`, native stop, gateway stop, held-input release and container closure exist. [Run 05][r5] bow stop, container stop, toggle release, navigation deadline and death/respawn cases; [stream tests][streams] disconnect and grant revocation. | Confirmed dig-abort hazard invalidates a general “no later break after stop” guarantee. Actual human-chat stop, disconnect/200 ms grant expiry and removal during active digging/use/navigation need complete native state/side-effect checks. Empty-cursor cleanup does not prove nonempty-cursor conservation. | Run delayed dig abort, human stop, expired grant, disconnect and removal against each active channel, waiting beyond its original completion time; assert no later world/inventory mutation and closed interaction state. |
| **EXEC-04 — open** | Exact retry identity, changed-payload rejection, epoch-aware handles, explicit unknown, 512-result/8 MiB/600-second retention and reconnect reconciliation exist. [Queue][queue], [result tests][backpressure], [SDK diagnostics tests][sdkdiag], [Run 05][r5] native retry/conservation cases. | Retry-safe reporting is still undermined by the delayed dig mutation. Dev2 recent-transition window and authoritative fallback have only local socket evidence. Gateway restart recovery has synthetic coverage, not a full native uncertain-mutation journey. | Verify dig reconciliation without retry; run native disconnect/restart during inventory/world mutations, then inspect outcome/world/counts before any deliberate retry. Preserve exact-ID and epoch guarantees with bounded push history. |
| **EXEC-05 — open** | Structured HTTP/WSS errors, argument validation, capability gating, legacy goal/chat rejection and native reason codes exist. [Primitive contract][queue], [socket parity][streams], [Run 05][r5] invalid inventory/dig/cooldown cases. | The complete argument/capability/reach/permission/resource/concurrency taxonomy is not exercised across every advertised operation and supported mod. Native workstation/entity disappearance and PvP permission cases remain incomplete. | Add table-driven contract coverage for every advertised operation, then native permission/reach/concurrency cases; compare reported capabilities to the exact loaded executor and documented mod support. |
| **EXEC-06 — open** | Whitelist UUID, ownership, lease, epoch and sticky human-stop checks; optional bounds are rechecked on mutations, multi-cell placement and container transactions. [Authorization tests][gatewaytests], [Run 05][r5] changed target, multi-cell bounds and unrestricted-area journey. | A delayed dig can mutate after cancellation/revocation. Broad native authorization-change tests while work is active are missing; not all post-movement container/world races are proven. Null area is intentionally unrestricted; it is not an authorization bypass. | Fix delayed dig abort, then revoke whitelist/token/lease or change bounds during native work; test container transactions after movement and verify rejected operations leave all affected cells/stacks unchanged. |

## Action primitives

| ID / checklist state | Implementation and evidence | Exact unmet or unverified acceptance | Next concrete action |
| --- | --- | --- | --- |
| **ACT-01 — checked** | Hotbar slots 0–8, selected slot and held stack; [Run 04][r4] `inventory_and_held_controls`, `inventory_invalid_arguments_and_drop_shortage`. | None newly asserted for checked valid/empty/invalid-slot criteria. | Keep all-nine-slot and invalid-index checks in the native suite. |
| **ACT-02 — checked** | Native main/offhand swap; [Run 04][r4] empty hands and `swap_two_populated_hands_preserves_components`. | None newly asserted for checked empty/populated/count/component criteria. | Preserve named/damaged-component conservation checks. |
| **ACT-03 — checked** | Exact quantity from explicit inventory slot, native drop, deduped retries; [Run 04][r4] partial/full drop, invalid arguments and Binding Curse case. | None newly asserted for checked quantity/decrement/entity/no-duplication criteria. | Retain retry and component/slot-rule regressions. |
| **ACT-04 — open** | Held jump request and stop release are implemented and observed. [Run 05][r5] `inventory_and_held_controls`. | That case verifies requested toggles, not actual grounded/airborne motion, repeated held jumping or navigation interaction. | Add native grounded, airborne and navigator-conflict cases; measure requested versus actual jump behavior and verify release after stop/expiry. |
| **ACT-05 — open** | Requested/actual sneaking exposed, used in long-navigation receipt test; stop releases it. [Run 05][r5] toggle and long-action cases. | Sneaking collision changes, edge behavior and forced release at every control-ending path lack dedicated native acceptance. | Test low clearance and platform edges, then disconnect/expire/stop and assert actual pose/input release. |
| **ACT-06 — open** | Sprint request, actual state and stop release exist. [Run 05][r5] toggle case. | No dedicated native hungry-versus-fed movement test or sprint lease-expiry test establishes vanilla constraints and actual speed/state. | Exercise hunger thresholds, movement constraints, stop and expiry; assert requested and actual sprint states separately. |
| **ACT-07 — open; known defect** | Selected-tool mining, durability, target/reach checks and drops implemented. [Run 05][r5] unbreakable/obstructed, tool durability, changed-target and explicit-cancel cases. | [Live discrepancy][dig] plus confirmed delayed-destruction source mechanism permits a post-failure/cancel break. Tool breakage, target changes, work bounds and line of sight need rechecking against the correction, including pickup into an initially empty hand. | Reproduce delayed breaking deterministically; correct native abort lifecycle and completion reporting; wait past original break time after each failure/stop and compare target, durability, drops and inventory. |
| **ACT-08 — open** | Destination coordinates with explicitly documented adjacent support face; survival placement and vanilla door/bed/double-plant footprint checks. [Run 05][r5] placement, door and secondary-cell bounds. | Empty hand, collision, orientation and replaceable-block variants are not all evidenced. Supported modded placements require explicit production-mod validation; unsupported footprints must remain truthful failures. | Add native orientation/collision/replaceable/empty-hand matrix and exact consumption checks; evaluate every supported mod placement footprint before advertising it. |
| **ACT-09 — open** | Main/offhand item activation, duration use, `release_use` and abort-without-release stop exist. [Run 05][r5] food consumption and held-bow stop. | Instant-use items, explicit release effects, unusable items and interruption by death/disconnect/revocation are not all verified. Production survival/item behavior remains outside vanilla fixture coverage. | Add instant/held/unusable/release cases, then terminate control during use and account for consumed items/projectiles/remainders. |
| **ACT-10 — open** | Typed block or entity targets, hand/face and native interaction; ambiguous modification footprints reject. [Run 05][r5] `use_on_thin_door_shape_open_close`; [contract][contract]. | Workstations, valid entity interactions, disappearance, invalid entity and permission/occlusion cases are incomplete. Production mod interactions are not established by a vanilla door. | Test block/entity target families, disappear/reach/occlusion failures and selected supported mod workstations; document unsupported actions precisely. |
| **ACT-11 — open** | Native attack, reach, cooldown and target lifetime; server PvP setting documented. [Run 05][r5] `attack_target_lifetime_and_cooldown`. | Obstruction and real PvP permission rejection are not comprehensively evidenced; an executed hit must remain distinct from a kill. | Add blocked-line-of-sight, PvP-disabled/enabled and disappearing-target cases with health/cooldown/results observations. |
| **ACT-12 — open** | Realtime native public chat with outcome; nonblank 220 UTF-16-unit validation, command/control rejection and per-body/global limits. [Run 05][r5] public message journey; [boundary tests][queue]. | Native spam-limit behavior across bodies and public-event identity/timestamps/deduplication are not fully exercised. Human/private-chat privacy is a separate open observation criterion. | Run native chat boundary/rate cases, verify one public event per delivered action and no command execution; test private messages remain absent. |
| **ACT-13 — open** | Native permitted menus, session/revision and complete layouts. [Run 05][r5] blocked/removed/range, double-chest and stop cases. | A genuine second viewer and complete human-stop/disconnect/lifecycle interaction coverage remain unverified; a console inventory edit is not a second viewer. Production machine menus require an explicit support matrix. | Execute real concurrent-viewer and disconnect fixtures; test supported production containers, both double-chest halves and every session invalidation path. |
| **ACT-14 — open** | Explicit player/container slots, revisions, native slot rules, stack/component conservation. [Run 05][r5] named/damaged stacks, stale revision, furnace slots and double chest. | Actual simultaneous viewers, ambiguous transfer across disconnect/reconnect and all machine-specific slot rules lack passing native evidence. | Run two-viewer races and transfer/disconnect/retry with exact counts/components on both sides; validate supported mod menu rules rather than treating arbitrary menus as generic storage. |
| **ACT-15 — open** | Real vanilla shaped/shapeless recipe execution, count=executions, ingredient matching, capacity and remainders. [Run 05][r5] cake, mixed tags, missing batch and capacity atomicity; [recipe checks][recipechecks]. | Production/modded recipes and explicit unsupported recipe rejection are not comprehensively demonstrated. Arbitrary machine processing is not implemented by grid crafting. | Validate concrete supported recipes from the production mod set and unsupported special/machine types, preserving ingredient/output/remainder atomicity. Define machine primitives separately if required by the supported gameplay contract. |
| **ACT-16 — open** | Explicit close, session invalidation and native menu cleanup. [Run 05][r5] explicit close/stop and death-respawn journey. | Nonempty cursor conservation and complete disconnect/death/human-stop closure evidence remain missing; closing an empty cursor is insufficient. | Put a real stack on the menu cursor, then close/disconnect/die/stop; prove conservation and stale-handle rejection after each path. |

## Observations and queries

| ID / checklist state | Implementation and evidence | Exact unmet or unverified acceptance | Next concrete action |
| --- | --- | --- | --- |
| **OBS-01 — checked** | 42 stable player/cursor slots, empty slots, components/durability and revision; bounded full-metadata reader. [Run 04][r4] inventory, populated hands and Unicode reconstruction; [metadata tests][metadata]. | No new gap asserted for checked slot/full-component contract. Production mod component semantics still need integration evidence under SDK-05/VERIFY-02. | Preserve exact full-metadata pagination/checksum/revision checks when adding mod cases. |
| **OBS-02 — open; known defect** | Bounded nearby IDs/types/positions and interaction state exist. [Run 05][r5] attack/lifetime case. | Live phantom was reported `hostile:false`; `Monster`-only classification misses other hostile families. Range, limit/privacy boundaries and classification need comprehensive native cases. | Correct classification and test phantom, ghast, slime and passive/player entities, plus disappearing IDs and observation bounds. Never infer harmlessness solely from false/unknown hostility. |
| **OBS-03 — open** | Radius/explicit-position raw queries with properties, dimension/tick and unloaded status, without intentional generation. [Run 05][r5] world queries, thin-door shape and deferred query result. | Native unloaded/chunk-boundary non-generation, freshness across dimension/epoch and arbitrary state-property coverage are incomplete. | Query loaded air, stateful blocks and unloaded cells; compare chunk state before/after, verify bounds and reject stale cross-body/dimension interpretation. |
| **OBS-04 — open** | Public message snapshots and typed deduplicated SDK chat events; [Run 05][r5] outgoing native chat observed; [SDK subscriptions][sdkcode]. | Incoming real human chat, private login-code/private-message exclusion, bounded-loss/gap and cross-reconnect deduplication are not completely evidenced. | Use authorized participating players for public/private messages and login delivery; run subscription gap/reconnect tests and retain only privacy-safe evidence. |
| **OBS-05 — checked** | Authorized open-session layout/revision/roles/contents and invalidation observations; [Run 04][r4] session, native slot and full metadata cases. | No new gap asserted for this checked observation contract. Real-viewer concurrency/nonempty cursor remain ACT-14/16 acceptance work. | Retain ambient-storage exclusion and revision/closure observations in future container tests. |
| **OBS-06 — checked** | Paged supported recipe discovery plus revision-pinned full metadata reader; [Run 04][r4] discovery/machine rejection and full recipe retrieval; [metadata tests][metadata]. | None newly asserted for checked discovery contract. This does not claim arbitrary machines or every mod recipe can execute. | Keep supported/unsupported recipe distinctions and full metadata fidelity as mod coverage expands. |
| **OBS-07 — open** | Execution channels, progress, hands, toggles and outcomes; fast frames separate from terrain. [Run 05][r5] bow, food, held inputs and receipt cases; [stream tests][streams]. | Dig progress/terminal observations are not trustworthy across the known abort hazard. Dev2 receipt-window/backpressure changes need native validation; sustained slow-consumer behavior failed to gain acceptance in the load runs. | Verify corrected dig lifecycle and all execution state transitions, then native bounded-window/gap/resync/slow-consumer cases with recorded snapshot age and cadence. |

## SDK ergonomics

| ID / checklist state | Implementation and evidence | Exact unmet or unverified acceptance | Next concrete action |
| --- | --- | --- | --- |
| **SDK-01 — open** | Private in-game-code login CLI, owned-body create/select, finite readiness helper and automatic lease acquisition. Development fixes reject unbounded timeout/invalid capability inputs before provisioning, clear old-body observations on selection and reject selection while a previous HTTP lease is held; [helper regressions][queue]. PLAYER reports Jamie_Syn completed real code enrollment and Architect connected; [first session](verification.md#controlled-single-body-checkpoint), [enrollment tests][gatewaytests], [SDK source][sdkbase], [CLI][cli]. | Real enrollment is no longer merely hypothetical, but a durable credential-free login/helper acceptance record and complete documented create/select/readiness/error flow remain incomplete. CLI actionable errors and actual deadline behavior against an unavailable body need end-to-end evidence. Synthetic fixture tokens are not substitutes for this real flow. | Retain a minimal code/token-free enrollment record and validate the exact packaged helper from login through named-body control, including stale/unavailable body and human-stop errors. |
| **SDK-02 — open** | Explicit bounded reconnect/backoff, cleared observation/container state, outstanding-ID reconciliation, no automatic resume/replay. [Socket tests][streams], [SDK result tests][sdkdiag], [Run 05][r5] death/respawn resync. | Full native uncertain-item-mutation disconnect, human-stop-across-reconnect and stale-container-handle journey remain incomplete. Dev2 truncated-window reconciliation is only locally verified. | Execute native transfer/dig/use interruption with reconnect, check original action epoch/outcome and new session, and prove human-stop persists until deliberate owner resume. |
| **SDK-03 — checked** | Sync/async methods, action handles, cancellation and typed observations/chat subscriptions; [socket async test][streams] and native independent-controls evidence. | No new gap asserted for checked API/transport-ownership criterion. Async ergonomics do not establish every primitive's gameplay correctness. | Keep async and sync parity while extending supported primitives and recovery. |
| **SDK-04 — open** | WSS pacing, retry metadata, connection/freshness/request diagnostics and stop priority; account `capabilities().limits` exposes request/queue/retention bounds. Development HTTP safety requests now bypass ordinary request lock/pacing; [real HTTP blocked-request regression][gatewaytests] passes in the 200-test local suite. Clean packaged install recorded in [verification][verify]. | Clean-install CLI help is not all documented examples. Dev2 native load/slow-consumer acceptance remains open; the HTTP priority fix is not deployed. | Execute documented examples from a clean install and rerun native performance/slow-consumer acceptance; retain HTTP and WSS blocked-request stop tests. |
| **SDK-05 — open** | Shared primitive wrappers, capability gating, schemas and short experimental guide; [contract][contract], [Python reference][python], [guide](../guidance.md), [release status](release-status.md). | Production mod interaction/survival coverage and precise unsupported cases are incomplete. Dev1 live versus dev2 source must remain explicit; broad error/schema parity and all examples require verification. | Build the concrete mod-support matrix with the native/container owners, exercise supported workflows, audit every example/guide/capability against the frozen version, and remove ambiguous legacy recommendations. |

## Comprehensive acceptance

| ID / checklist state | Implementation and evidence | Exact unmet or unverified acceptance | Next concrete action |
| --- | --- | --- | --- |
| **VERIFY-01 — open** | [Run 05][r5] flat+look, slab/stair destinations, low ceiling, inserted obstruction, solid target, short timeout, death/respawn. | Moving entities, ascent/drop limits and loaded-chunk boundaries lack full traversal evidence. Fluids, ladders, doors and unsupported mod terrain need explicit limitations and production-relevant tests. | Extend physical traversal fixture across every named terrain case, then cancellation/unreachable/death conditions; publish precise unsupported terrain without pretending path-search unit checks prove movement. |
| **VERIFY-02 — open** | Native fixture gathers one supplied log, crafts, places, uses a chest and chats; unrestricted variant passes [Run 05][r5]. Real Architect session after Jamie_Syn enrollment navigated, harvested natural logs and crafted/placed a table/refuge; [session record](verification.md#controlled-single-body-checkpoint). | Real chest-transfer/communication and full documented helper journey are not established by that session. Food/recovery and industrial production remain unfinished. Fixture-supplied infrastructure and vanilla-only tests do not prove production mod/survival gameplay. | Finish a documented real-player complete journey and supported industrial/survival workflows; agent writes task logic only, with no transport/SDK patches. Preserve the dig failure and damage evidence rather than counting the partial session as a pass. |
| **VERIFY-03 — open** | Missing ingredients/capacity, remainder conservation, changed terrain, retry deduplication, simulated competing mutation and death pass in [Run 05][r5]. | True concurrent chest viewer, uncertain disconnect, revocation during native mutations and the dig post-failure mutation remain unresolved. Full item accounting across each failure is not established. | Fix the dig hazard and execute every named failure journey with before/after stacks/components/world evidence and unambiguous results. |
| **VERIFY-04 — open** | Administrative order stop persists to owner resume; placement/double-chest bounds checks pass. [Run 05][r5] administrator stop and secondary-cell area cases. | Administrative injection is not actual human chat. Known delayed dig can violate post-stop safety. Actual stop across reconnect plus unchanged world/inventory on all work-area rejections remains incomplete. | Use a human public stop, reconnect without resume, verify all active channels remain stopped and no late dig occurs; then deliberate owner resume and comprehensive rejection conservation. |
| **VERIFY-05 — open; failed** | Fixed targets in [verification][verify]; retained run failures and raw samples. [Run 05][r5] failed after 44.7 s, ACK p95 149.564 ms, completion p95 2643.372 ms, pending action timeout. Dev2 [synthetic benchmark][bench] reduces CPU/traffic. | No passing five-minute ten-body fairness/tick/cadence/latency/slow-consumer result. Local Python synthetic figures do not meet any native acceptance gate. | Run the predeclared native sustained test only after correctness fixes and source freeze; keep startup/outliers/resources/mod list, and meet all original targets rather than relaxing them. |
| **VERIFY-06 — open** | [Controlled manifest](evidence/controlled-candidate-20261103.json), deployment/backup/rollback audit and versions recorded in [verification][verify]; experimental navigation smoke passed. | 32 checklist items remain open; correctness/load failures and real onboarding/full journey prevent comprehensive release. Experimental deployment is not completion. No additional live restart window is authorized. | Finish and link all required acceptance evidence, publish truthful capabilities/limitations, prepare rollback and obtain a fresh maintenance window before any further Java deployment; smoke-test the exact deployed artifacts. |

## Evidence interpretation and continuing work

The row-level run-05 gaps below are supplemented by
[full-pack run 07](evidence/api-fixture-run-07.json): **52 cases pass**, including
native two-viewer contention, disconnect reconciliation and delayed-dig guards.
Death recovery fails its vanilla loose-item assumption under the actual Corpse
mod; native authorized corpse retrieval remains required. The native ten-body
test still fails its original targets, with completion p95 3106.542 ms and a
pending action timeout. See the [full report](verification.md#full-pack-development-runs-06-and-07).
These additions advance the named criteria without closing the full items.

[Real human-stop evidence](evidence/live-human-stop-20261103.json) now establishes
Jamie_Syn's public Minecraft message reached Architect, suspension persisted and
a fresh connection was refused with `human_stop_requires_resume`. This replaces
the rows' earlier uncertainty about real delivery/persistence only. Architect was
idle; active cancellation and private-message exclusion remain separate criteria.

The current minimum local development suite has 204 passing tests. Tests added
after that baseline must carry their own run evidence; do not reuse the count as
proof they ran. [Run 05][r5] identifies its actual imported source hashes and
native adapter. New source or a written fixture is not a new passing native case.

Additional local EXEC-03/06 and SDK-02 regression: mixed-case body names previously
authenticated successfully but left the canonical body's lease behind on an
unexpected WebSocket disconnect. Stream names now canonicalize immediately after
authorization. The real-socket
`test_mixed_case_body_name_releases_canonical_lease_on_disconnect` in
[stream tests][streams] verifies release without a client-issued DELETE. This
development fix is not a new production deployment or a substitute for native
disconnect/side-effect acceptance.

The new [authorization fixture](../../tests/authorization_gameplay_cases.py) adds
nine combinations of whitelist removal, owner UUID replacement and token revocation
during actual digging/navigation/held bow use, plus wrong-owner rejection and
changing bounds during active digging/container access. It restores exact fixture
policy, reconnects explicitly and reconciles SDK outcomes/world/inventory after at
least 100 native ticks from the original start. These cases are **syntax-checked,
not run against Minecraft**. They do not simulate a real human chat event.

EXEC-04/SDK-02 stale cancellation follow-up: `ActionHandle.cancel()` now pins the
original body epoch, just as completion lookup does. The HTTP and WSS regression
`test_stale_action_handle_cancel_cannot_cancel_reused_id_in_new_epoch` in
[helper tests][queue] proves an old handle cannot cancel a current action with the
same ID after an epoch change. The gateway returns `409/body_changed` and the
new action remains accepted. This is local source/test evidence.

Production mod support and survival requirements are still being audited against
the actual server pack. Record concrete supported menus, recipes, items, entities,
terrain and survival workflows as evidence arrives; do not replace missing support
with an assertion that vanilla examples constitute comprehensive industrial play.
Neither a single-body checkpoint nor a partial implementation is the completion
condition for this work.

The container audit has identified a concrete industrial gap: the live vanilla
menu/grid implementation does not cover Create depot/basin item handlers or native
processing metadata. A local native candidate now reuses `open_container`,
`move_item`, `query_inventory` and `close_container` for reviewed
`kind: machine_item_port` sessions: depot slots 0–8 and basin slots 0–17. Existing
gateway/SDK slot and revision contracts can carry it without new wire operations.
Recipe descriptors can expose `execution: native_world_ticks`,
`craft_supported: false` and full `native_recipe` metadata; machine recipes must
not be sent through grid `craft`. The native candidate is unbuilt/unverified;
powered processing, probabilities, heat/fluid requirements, slot conservation and
full-pack behavior still require meaningful acceptance tests. A proposed contract
is not an advertised verified capability. Two additional
[container fixtures](../../tests/container_gameplay_cases.py),
`container_two_native_viewers_contested_transfer_conservation` and
`container_disconnect_reconcile_without_mutation_replay`, are written but have no
passing native result in Run 05.

## Thirteen additional installed-pack requirements

These are the **13 open additions** in the
[authoritative checklist](api-completion-checklist.md#additional-requirements-identified-by-the-installed-pack-audit).
They are separate from the original 40 IDs and eight checked entries. Detailed
supported blocks, menus and processing contracts belong in
[mod compatibility](mod-compatibility.md). No local implementation below is a
passing full-pack case.

| Additional ID | Current implementation/evidence | Remaining acceptance and next action |
| --- | --- | --- |
| **PACK-01 — open** | Read-only audit matched 25 public JAR filenames; fixture can verify locked SHA-512 and copy exact public JARs into a fresh world. | Build/run full-pack native acceptance, record relevant live-versus-default config differences and effects, and preserve hashes/resources/ports without production data. |
| **MOD-01 — open** | Native placement/use framework exists; bounded reviewed Create placement work is local. | Verify reviewed kinetic blocks, orientation, crank/wrench and native agent-built waterwheel power, with exact consumption and configured bounds. See [compatibility](mod-compatibility.md). |
| **MOD-02 — open** | Local depot/basin item-port sessions and processing recipe metadata reuse existing SDK/gateway contracts. Written press/mixer fixtures are unrun. | Verify depot/press and basin/mixer inputs/outputs, an unpowered baseline, real powered completion and complete accounting. A fixture-supplied motor must be identified. See [compatibility](mod-compatibility.md). |
| **MOD-03 — open** | Local millstone item port and a written two-batch milling/dough/furnace case; no passing full-pack result. | Complete two fresh 16-wheat batches, observe actual probabilistic byproducts, bucket/dough remainders and fuel/smelting; deliver 32 bread with an agent-built waterwheel in the full journey. See [compatibility](mod-compatibility.md). |
| **MOD-04 — open** | Local machine-port session/revision/slot simulation framework; native conservation/concurrency evidence is pending. | Verify native input/output rules, exact components/counts, reach/bounds, processing/concurrent changes, removal and disconnect reconciliation without mutation replay. See [compatibility](mod-compatibility.md). |
| **MOD-05 — open** | Generic permitted native menus exist; no comprehensive Sophisticated Storage/backpack acceptance. | Implement and verify block/item/worn inventory sessions, compartments, high-capacity stacks, filters, upgrades, ownership and close/reconnect conservation. See [compatibility](mod-compatibility.md). |
| **MOD-06 — open** | Direct item/block controls and recipe-query transport exist; no passing Farmer's Delight workstation journey. | Verify heated pot and cutting-board workflows, serving containers, tool durability, output rolls and complete processing metadata. See [compatibility](mod-compatibility.md). |
| **MOD-07 — open** | Generic container/entity interfaces exist; native Lootr/Corpse access is not established. | Implement and verify body-specific Lootr access and authorized corpse recovery without bypassing restrictions, changing inventory identity or losing components. See [compatibility](mod-compatibility.md). |
| **MOD-08 — open** | Direct placement/use/navigation interfaces exist; Steam 'n' Rails ownership and moving-control semantics are unverified. | Define and verify supported track/control placement, station/schedule/riding interaction and moving-contraption lifecycle, ownership and stop behavior. See [compatibility](mod-compatibility.md). |
| **MOD-09 — open** | Candidate recipe metadata can describe fluids/heat; this does not implement tank/transfer/processing control. | Verify tank observations, real buckets/approved fluid interactions, heated/fluid basin recipes, spout filling and drain emptying with conservation. See [compatibility](mod-compatibility.md). |
| **MOD-10 — open** | Exact public pack inputs can be staged into the isolated fixture; existing native baseline uses a smaller mod set. | Run primitive/survival acceptance under the exact pack and assess seasonal farming, difficulty and performance-mod effects, documenting relevant configuration differences. See [compatibility](mod-compatibility.md). |
| **SURV-01 — open** | Real Architect session gathered logs, crafted/placed shelter/table and took damage without death; recovery/food and industrial production were unfinished. | Run a finite documented food preparation/consumption, health recovery, shelter and threat-response journey with exact supplied/gathered/consumed accounting through SDK primitives. |
| **SURV-02 — open** | Isolated death/respawn resync passes; epoch-pinned cancellation and local reconnect protections are implemented. New authorization cases remain unrun. | Test native damage/death/corpse recovery, interruptions and unknown mutations on the full pack, including stale handles, sticky human stop, deliberate resume and preservation of player work. |

[r4]: evidence/api-fixture-run-04.json
[r5]: evidence/api-fixture-run-05.json
[dig]: evidence/live-dig-reconciliation-20261103.json
[verify]: verification.md
[bench]: ../../benchmarks/transport/README.md
[contract]: direct-actions.md
[python]: python-reference.md
[queue]: ../../tests/test_primitive_contract.py
[backpressure]: ../../tests/test_result_backpressure.py
[streams]: ../../tests/test_streaming.py
[sdkdiag]: ../../tests/test_realtime_diagnostics.py
[gatewaytests]: ../../tests/test_controller_gateway.py
[metadata]: ../../tests/test_inventory_query.py
[sdkcode]: ../scru_minecraft/realtime.py
[sdkbase]: ../scru_minecraft/__init__.py
[cli]: ../scru_minecraft/__main__.py
[recipechecks]: ../../agent-mod/src/test/java/gl/syn/minecraft/
