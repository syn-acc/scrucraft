# Direct-control migration: development milestone 1

The first milestone was deployed on 2026-11-03 in an explicitly approved restart
window: Java adapter 0.4.0 and SDK/gateway 0.2.0.dev1. The direct WebSocket path,
prefix-free names and actual Java look-action latency are verified live. The
remaining migration work below is not complete. [Live results](docs/realtime.md).

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
- Bidirectional authenticated WebSockets on `/v1/events`. First-message auth keeps
  tokens out of URLs. Slow receivers do not hold the gateway/controller mutex.
  Reconnect creates a fresh snapshot sequence; it does not replay commands.

The live adapter now has a direct loopback WebSocket bridge, bypassing the
one-second controller HTTP cycle. Lightweight telemetry and action results are
sampled each game tick (nominally 20 Hz); terrain scans remain about once a second.
Snapshots coalesce under backpressure. Grants expire after 200 ms without renewal;
public stream disconnect releases its acquired lease. No commands replay on
reconnection. Native search scheduling rotates bodies under a shared tick budget.
See [the realtime contract and measurements](docs/realtime.md).

Enable gateway `websocket_enabled` only after installing the pinned dependency and
the nginx upgrade route. The listener binds loopback port 8769. The adapter opts
in using `control_transport: "websocket"` in the existing private
`agent-service/gateway.json`; it reads that file's `token_file`. In this mode it
does not call the goal controller, and goal submissions are explicitly rejected.
Never expose `/internal/body` through nginx. These settings are enabled on the
live adapter following the approved 2026-11-03 maintenance deployment.

## Remaining migration and validation work

1. Isolated in-game navigation fixtures: slabs/stairs, low ceilings, jump arcs,
   falling, moving entities, terrain changes, chunk edges, death/respawn and stop.
   Current fixtures test the search algorithm; compilation does not prove movement.
2. Measure aggregate tick cost and scheduling fairness with ten bodies. The current
   shared deadline is a starting budget, not a measured latency guarantee.
3. Add dig/place/use/attack, hotbar/hands/drop, movement toggles, containers and
   recipe-ID crafting with authoritative completion and real conservation checks.
   Work-area checks must cover destinations and each container transaction.
4. Add raw block queries, complete slot snapshots, nearby entity observations and
   incoming public chat. Private chat remains excluded. Fast telemetry is separated
   from terrain scans, but aggregate cost still needs measurement in Minecraft.
5. Expand receipt retention and cancellation/reconnect tests; integrate navigation
   with an explicit primitive scheduler. Unsupported operations must stay rejected.
6. Prefix-free names and the WebSocket adapter are deployed. Preserve the recorded
   backup/rollback path; further Java releases require a new maintenance window.

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
