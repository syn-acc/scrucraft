# Direct-control migration: development milestone 1

This branch is **not deployed**. Production remains SDK/gateway 0.1.2 with the
goal API. The staged Java adapter is 0.4.0; the SDK/gateway development version
is 0.2.0.dev1. Do not publish this candidate over the current downloads.

## What the body actually is

`AgentPlayer` extends Minecraft `ServerPlayer` in survival mode. Its connection is
local, but vanilla ticking, hunger, collision, inventory and advancement machinery
remain active. The original controller uses `move`, `mine`, `place`, `interact`,
`use`, `eat`, `attack`, grid crafting and furnace insertion/extraction. Previously,
Python selected goals and generated movement waypoints. There was no native
navigator or Baritone integration.

## Implemented in this first development milestone

- Incremental native A* with bounded search size, tick slicing and loaded-terrain
  checks. Terrain edges use player collision boxes, half-block height samples,
  one-block ascents and drops up to three blocks. Hazardous ground is excluded.
- Native waypoint following, arrival detection, obstruction/stall replanning,
  timeouts, cancellation, and explicit failed reasons. No teleportation, digging,
  placement or chunk generation is performed by navigation.
- `move_to`, `look_at` and stop controls, gated by observed adapter capabilities.
  Each request carries a body incarnation ID, preventing stale commands from
  being applied after respawn. Accepted, started and terminal results are distinct.
- `POST /v1/actions`, `GET /v1/action-results`, and SDK movement/orientation methods.
  Existing owner/whitelist/lease/human-stop checks apply. Goal submission replaces
  raw control and vice versa. Direct movement bypasses goal planning.
- Authenticated WebSocket snapshots on `/v1/events`. First-message auth keeps
  tokens out of URLs. Slow receivers do not hold the gateway/controller mutex.
  Reconnect creates a fresh snapshot sequence; it does not replay commands.

The stream currently reflects the existing adapter snapshot cadence (about 1 Hz),
not a promised high-frequency game-event stream. Enable `websocket_enabled` only
after installing the pinned dependency and the nginx upgrade route. The WebSocket
listener binds loopback port 8769 and shares the HTTP gateway's authorization state.

## Still required before production release

1. Isolated in-game navigation fixtures: slabs/stairs, low ceilings, jump arcs,
   falling, moving entities, terrain changes, chunk edges, death/respawn and stop.
   Current fixtures test the search algorithm; compilation does not prove movement.
2. Measure aggregate tick cost and scheduling fairness with ten bodies. The current
   shared deadline is a starting budget, not a measured latency guarantee.
3. Add dig/place/use/attack, hotbar/hands/drop, movement toggles, containers and
   recipe-ID crafting with authoritative completion and real conservation checks.
   Work-area checks must cover destinations and each container transaction.
4. Add raw block queries, complete slot snapshots, nearby entity observations and
   incoming public chat. Private chat remains excluded. Separate fast telemetry
   from costly terrain snapshots before increasing the adapter's update frequency.
5. Expand receipt retention and cancellation/reconnect tests; integrate navigation
   with an explicit primitive scheduler. Unsupported operations must stay rejected.
6. Build one maintenance release including prefix-free names. Preserve the world's
   backup/rollback path and request a new agreed maintenance window before applying.

## References, not dependencies

- [Mineflayer API](https://github.com/PrismarineJS/mineflayer/blob/master/docs/api.md):
  primitive names and event-oriented client interface.
- [Carpet action pack](https://github.com/gnembon/fabric-carpet/blob/master/src/main/java/carpet/helpers/EntityPlayerActionPack.java):
  server-side player controls.
- [Malmo](https://github.com/microsoft/malmo): observations and action interface.
- [Baritone](https://github.com/cabaletta/baritone): navigation comparison; our
  navigator is implemented here and does not use Baritone.
- [Voyager](https://voyager.minedojo.org/) and
  [Mindcraft](https://github.com/mindcraft-bots/mindcraft): agent-side skill building.

These references informed the interface discussion. No upstream implementation
was copied into the navigator.
