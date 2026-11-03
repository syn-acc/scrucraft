# Direct-control migration and experimental release

The experimental release is SDK/gateway **0.3.0.dev2** and Java adapter
**0.5.0-dev2**. It adds bounded transport, cancellation/recovery fixes, reviewed mod
interfaces and navigation corrections for fractional ground and airborne starts.
The preceding single-body checkpoint and its failed load reports remain historical
evidence. Full checklist acceptance and ten-body performance remain incomplete.

Track implementation and release acceptance in the
[Gameplay API completion checklist](docs/api-completion-checklist.md).

## What the body actually is

`AgentPlayer` extends Minecraft `ServerPlayer` in survival mode. Its connection is
local, but vanilla ticking, hunger, collision, inventory and advancement machinery
remain active. The original controller uses `move`, `mine`, `place`, `interact`,
`use`, `eat`, `attack`, grid crafting and furnace insertion/extraction. Previously,
Python selected goals and generated movement waypoints. There was no native
navigator or Baritone integration.

## Historical baseline: 0.2.0.dev1 / adapter 0.4.0

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
  Existing owner/whitelist/lease/human-stop checks apply. Realtime bodies reject
  goal submission. Direct movement bypasses goal planning.
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

## Historical experimental checkpoint: 0.3.0.dev1 / adapter 0.5.0-dev1

The source now implements protocol 2 command queues and independent compatible
controls; direct digging, placement, hand/inventory inputs, entity/block use,
containers and recipe crafting; raw inventory/entity/block/public-chat observations;
and synchronous/async SDK handles, readiness, diagnostics and bounded reconnect.
That checkpoint was deployed for a controlled single-body session and did not mean the
comprehensive checklist has passed. See the [player guide](guidance.md),
[wire contract](docs/direct-actions.md), [native semantics](docs/native-executor.md)
and [verification evidence](docs/verification.md).

Results retain full operation payloads by ID while streamed snapshots are compact.
Native detail acknowledgements and byte/count/time bounds prevent repeated recipe
pages and container inventories from expanding every tick. Reconnection reconciles
uncertain IDs; it never replays a mutation or clears a persistent human stop.

## Remaining release work

The [existing completion checklist](docs/api-completion-checklist.md) remains the
complete scope. Its acceptance criteria are unchanged. Isolated native cases must
cover each specified success/failure edge, including navigation terrain, real
inventory conservation, cancellation/revocation/death, and container contention.
Transport tests and successful compilation do not establish those behaviors.

Jamie_Syn completed a real private in-game code exchange. The full
player gameplay and human-chat stop acceptance cases remain separately tracked.
Ten-body performance needs the predeclared targets and retained raw evidence in
[verification](docs/verification.md); small fixtures do not establish production
capacity. Production mod interactions, final package/example checks and rollback
remain release gates. Further Java deployments require separately approved maintenance windows.

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
