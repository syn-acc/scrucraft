# Gameplay API completion checklist

**Area policy (development candidate):** No location or coordinate selection is
required. Omitted/null `area` means unrestricted survival play. Area checks below
apply only to optional owner-selected bounds. Normal survival, account ownership
and human-stop controls remain. This policy change is not yet deployed.

Working backlog, reviewed **2026-11-03**. This is the release checklist for a
player-ready SDK, not an advertisement of currently supported operations.

Live baseline: adapter **0.4.0**, SDK/gateway **0.2.0.dev1**. Direct control exposes
only `move_to`, `look_at` and `stop`. Authentication, body ownership, leases and
bidirectional WebSockets are implemented. Live latency measurements exercised
`look_at`; they do not establish navigation or general gameplay reliability.

Signatures below are proposed SDK interfaces. Final wire fields, slot conventions
and interaction targets must be documented before implementation is marked done.
The gateway forwards individual operations; task planning and skill composition
belong in the player's agent. Native navigation belongs in the body adapter.

## How we work through this

Keep an item unchecked until its Java/gateway implementation, Python SDK method,
observations/results, meaningful tests and documentation are ready. Add its PR or
commit and test evidence beside the item when checking it. Implementation complete
does not mean deployed: record deployment separately in [release status](release-status.md).

Suggested order: **execution contract → observations and basic controls → world
interactions → containers/crafting → recovery and complete gameplay validation**.
Navigation validation can proceed alongside these stages.

The current implementation effort uses these existing 40 items as its scope.
There is no separate, narrower milestone replacing them. Candidate code and
partial test coverage are tracked in [verification evidence](verification.md);
passing one gameplay fixture does not complete a whole checklist section.

## 1. Execution contract — fix before adding more actions

- [ ] **EXEC-01 — Independent compatible controls.** Looking must not silently
  cancel navigation. Define which movement, hand and inventory operations can run
  together; incompatible operations must explicitly queue, replace or reject.
  Test moving while looking and changing a held item during a hand action.
- [ ] **EXEC-02 — An outcome for every accepted command.** Correlate action ID and
  body epoch through `accepted`, optional `started`, and `done`/`failed`/`cancelled`.
  A command replaced before Java receives it must also get an outcome. Never
  equate acceptance with success; test rapid replacement and cancellation races.
- [ ] **EXEC-03 — Cancellation and held controls.** Define `cancel(action_id)`,
  `stop()` and held-input release semantics. Stop must promptly abort digging,
  navigation and item use, release toggles and close container interaction state.
  Test human stop, disconnect, expired grants, death and body removal.
- [ ] **EXEC-04 — Retry and result reconciliation.** Document bounded result
  retention and a way to inspect an uncertain action after reconnect. Deduplicate
  exact retries, reject changed payloads using the same ID, and report an explicit
  unknown outcome when evidence expired. Never blindly replay item mutations.
- [ ] **EXEC-05 — Consistent errors and truthful capabilities.** Publish argument,
  capability, reach, permission, resource and concurrency failures as structured
  errors. Unsupported legacy goal/chat calls must fail clearly, not appear queued
  successfully. Capability discovery must match the actual active executor.
- [ ] **EXEC-06 — Authoritative checks per call.** Preserve whitelist/UUID,
  ownership, lease, body-epoch and human-stop checks. Enforce work areas for every
  dig, placement and container operation, including transactions after movement.
  Revalidate long-running actions when their world or authorization changes.

## 2. Missing action primitives

These are missing from the direct gateway/SDK, even where an older internal Java
controller already has related functionality. Reuse real survival mechanics;
do not synthesize items, teleport or silently select tools on the server.

### Inventory and movement inputs

- [ ] **ACT-01 — `select_slot(n)`**: select the documented hotbar slot and observe
  the held stack. Test every valid slot, empty slots and invalid indices.
- [ ] **ACT-02 — `swap_hands()`**: exchange main/offhand stacks through vanilla
  mechanics. Test empty and populated hands; verify counts and item components.
- [ ] **ACT-03 — `drop(slot, count)`**: drop an exact legal quantity from an
  explicit slot. Test partial/full stacks, invalid counts and ambiguous retries;
  verify inventory decrement and spawned item entity without duplication.
- [ ] **ACT-04 — `jump(enabled)`**: define one-shot versus held jumping and its
  interaction with navigation. Test grounded/airborne behaviour and release on stop.
- [ ] **ACT-05 — `sneak(enabled)`**: expose and observe sneaking. Test collisions,
  edge behaviour and forced release when control ends.
- [ ] **ACT-06 — `sprint(enabled)`**: expose requested and actual sprint state.
  Respect vanilla hunger and movement constraints; test stop and lease expiry.

### World and entity interaction

- [ ] **ACT-07 — `dig(x, y, z)`**: mine the specified block using the selected
  tool, real break progress, durability and drops. Check reach, line of sight,
  dimension and work area. Test unbreakable blocks, changed targets, cancellation,
  tool breakage and out-of-area rejection. Completion means the intended block
  was broken, not merely that mining began; do not implicitly walk to it.
- [ ] **ACT-08 — `place(x, y, z, face)`**: interact with an explicitly documented
  support block/face using the held item. Define whether coordinates name the
  support or destination; check the actual destination and all affected cells
  against the work area. Test empty hands, collision, orientation, replaceable
  blocks and multi-block placements; verify exact inventory consumption.
- [ ] **ACT-09 — `use_item()`**: activate the held item, including duration-based
  use such as eating or drawing a bow. Specify hand, start/release behaviour and
  what counts as completion. Test instant use, held use, interruption, consumption
  and unusable items. Add an explicit release operation if stop alone is insufficient.
- [ ] **ACT-10 — `use_on(target)`**: interact with a block face or entity through
  typed target references. Define hand and hit location; enforce vanilla reach,
  line of sight and applicable world-modification permissions. Test doors,
  workstations, invalid entities and targets that disappear.
- [ ] **ACT-11 — `attack(entity_id)`**: attack the current entity with the held
  item and vanilla cooldown/reach rules. Document the player/PvP permission policy
  rather than silently imposing an enemy-only filter. Test missing targets,
  obstruction, cooldown and permission rejection. An executed attack is not a kill.
- [ ] **ACT-12 — `chat(text)`**: send validated public player chat without command
  execution. Preserve reasonable spam limits, route through the realtime executor,
  return delivery outcome and observe the message in the public chat stream.

### Containers and crafting

- [ ] **ACT-13 — `open_container(x, y, z)`**: open an accessible permitted
  container and return a session ID, revision and complete slot layout. Test
  blocked/removed containers, distance changes, double chests and human stop.
- [ ] **ACT-14 — `move_item(from_slot, to_slot, count)`**: transfer between explicit
  player/container slot references within the active session. Validate its
  revision, reach, work area, stack limits and slot rules on every call. Test
  competing viewers, stale revisions, partial stacks and disconnect/retry cases;
  verify conservation of counts and item components across both inventories.
- [ ] **ACT-15 — `craft(recipe_id, count)`**: craft a discoverable supported recipe
  using real ingredients and the appropriate grid/workstation. Define count as
  recipe executions or output quantity. Test missing ingredients, full inventory,
  remainder items, alternative ingredients and unsupported mod recipes. Verify
  outputs and remainders; never claim arbitrary machine processing is supported.
- [ ] **ACT-16 — `close_container()` — supporting addition**: close the active
  session, invalidate its handles and release any cursor stack safely. Test
  explicit close, disconnect, death and stop without item loss or duplication.

## 3. Observations and read queries required by those actions

- [ ] **OBS-01 — Complete inventory**: stable slot identifiers for hotbar, main
  inventory, armor, offhand and cursor; explicit empty slots, counts, durability,
  relevant item components and inventory revision. Current output omits empty
  slots and does not provide the complete equipment/container contract.
- [ ] **OBS-02 — Entity observations**: bounded nearby entity queries with IDs,
  types, positions and interaction-relevant state. Define range, limits, target
  lifetime and privacy boundaries. Current output is filtered to selected hostiles
  and dropped items rather than a general interaction view.
- [ ] **OBS-03 — Block states**: bounded radius and explicit-position queries
  returning block IDs, state properties, dimension and freshness. Distinguish
  unloaded/unknown cells from air. Current resource/walkable samples are insufficient
  for arbitrary placement and interaction. Queries must not force chunk generation.
- [ ] **OBS-04 — Public chat**: incoming messages with IDs, sender and timestamp,
  delivered as events with deduplication. Exclude private login codes and private
  messages. The existing internal human-stop processing is not a public chat API.
- [ ] **OBS-05 — Containers**: session ID/revision, slot roles, contents, capacity
  and close/invalidation events. Other players' unrelated storage must not appear
  in ambient observations; require an authorized open session.
- [ ] **OBS-06 — Recipes**: discover supported recipe IDs, ingredients, outputs,
  remainders and workstation requirements; distinguish unsupported recipe types
  from insufficient ingredients. Agents must not guess IDs from display names.
- [ ] **OBS-07 — Execution and body state**: expose active actions, break/use
  progress, selected slot, hands, requested/actual movement toggles and terminal
  outcomes. Keep fast updates separate from costly terrain queries and document
  snapshot age, gaps, resync and backpressure behaviour.

## 4. SDK ergonomics — no player-written transport workarounds

- [ ] **SDK-01 — Complete onboarding helper**: guide login, create/select an owned
  body, await readiness with a finite timeout, and acquire control. Preserve
  private credentials and show actionable errors. Validate actual in-game code
  delivery with a participating whitelisted player; administrative test tokens
  do not prove this flow.
- [ ] **SDK-02 — Reconnect and resync**: reconnect the transport with bounded
  backoff, clear stale body/container state and reconcile outstanding actions.
  Never automatically override a human stop or replay uncertain mutations.
- [ ] **SDK-03 — Async actions and subscriptions**: provide an asynchronous API
  alongside the synchronous client, action handles with completion/cancellation,
  and typed observation/event subscriptions. Looking while moving must not require
  application authors to manage sockets or lease renewal.
- [ ] **SDK-04 — Pacing and diagnostics**: expose action limits and retry timing;
  safely pace submissions without hiding errors or delaying stop behind work.
  Surface connection state, observation freshness and request timing. Check
  packaged installation and examples from a clean environment.
- [ ] **SDK-05 — One coherent contract**: keep capability discovery, method names,
  HTTP/WSS schemas, examples and the short player guide consistent. Document
  supported mod interactions and precise unsupported cases. Remove misleading
  legacy paths from the recommended player flow.

## 5. Comprehensive release acceptance

- [ ] **VERIFY-01 — Navigation**: live isolated fixtures for flat ground, slabs,
  stairs, low ceilings, ascent/drop limits, obstructions, moving entities, terrain
  changes and loaded-chunk boundaries. Test arrival, cancellation, unreachable
  targets, timeout, death and respawn. Declare limitations for fluids, ladders,
  doors and unsupported modded terrain explicitly.
- [ ] **VERIFY-02 — Full gameplay journey**: a player logs in, creates a named
  agent, navigates to an approved area, selects tools, gathers materials, crafts,
  places blocks, transfers items through a chest and communicates. The agent
  writes task logic; it does not patch the SDK or implement transport recovery.
- [ ] **VERIFY-03 — Failure journey**: repeat with missing materials, changed
  terrain, concurrent chest access, disconnects, duplicate requests, revoked
  membership and death. Verify exact item accounting and clear outcomes.
- [ ] **VERIFY-04 — Human control**: human stop cancels active work and persists
  across reconnects; only deliberate owner resume permits new work. Work-area
  rejection must leave blocks and inventories unchanged.
- [ ] **VERIFY-05 — Multi-body performance**: measure ten-body fairness, game tick
  cost, observation cadence and p50/p95/p99 acknowledgement and execution latency.
  Include sustained load, slow consumers and startup; retain outliers. Set and
  record release targets before testing rather than selecting convenient results.
- [ ] **VERIFY-06 — Release evidence**: all required items above have linked tests
  and documentation; publish supported capabilities and remaining limitations,
  preserve backup/rollback, and deploy Java changes only in a newly approved
  maintenance window. Record the deployed versions and smoke-test results.

Existing evidence: [live WebSocket measurements](realtime.md),
[current direct-action contract](direct-actions.md), and [migration history](../MIGRATION.md).
