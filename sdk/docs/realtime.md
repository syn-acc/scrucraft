# Realtime controls — live experimental 0.2

Deployed on 2026-11-03 with adapter 0.4.0 and SDK/gateway 0.2.0.dev1.
Use this WebSocket flow for bodies on the server. The old goal controller is
bypassed; account verification and lifecycle HTTP endpoints remain available.
Navigation is experimental; terrain traversal reliability still needs validation.

Install the checkout with `python -m pip install './sdk[stream]'`, then use:

```python
from scru_minecraft import AgentClient

client = AgentClient.from_file(agent="YourAgent")
with client.realtime() as body:
    print(body.observe())
    receipt = body.move_to(110.5, 64, 104.5)
    result = body.wait_action(receipt["id"], timeout=30)
    print(result, body.last_timing)
```

Commands and responses share one persistent WSS connection. The SDK reads pushed
state in a background thread, renews its lease, and keeps the latest observation.
`move_to`, `look_at`, `action`, `stop`, `observe`, and `wait_action` need no HTTP
polling. Submission is capped at 20 primitives/sec per body; the SDK does not
silently retry a rejected or ambiguous mutation. `stop()` releases pending work,
while `action("stop")` produces an executor receipt. Closing the context releases
the lease. Reconnection requires a new stream and never replays previous commands.

Connect to `wss://uk.syn.gl/minecraft-agents/v1/events`.
First send `{"token":"PRIVATE_TOKEN","agent":"YourAgent"}`. Tokens must stay out
of URLs, prompts and logs. A command envelope is:

```json
{"request_id":"correlation_1","method":"POST","path":"/v1/actions","lease_id":"LEASE","body":{"id":"unique_action_0001","op":"look_at","target":[1,64,1],"body_epoch":"EPOCH","ttl_seconds":30}}
```

Responses contain `type: "response"`, matching `request_id`, `status`, and either
`result` or `error`, plus `gateway_processing_us`. Acquire with POST `/v1/lease`,
renew with PUT, release with DELETE. DELETE `/v1/goal` stops pending work; GET
`/v1/action-results` reads results. Other routes remain HTTP-only.

Pushed `snapshot` envelopes contain `sequence`, `resync` and `observation`.
The first is a full resync; subsequent snapshots may omit unchanged terrain
(`blocks`, `walkable`). Merge by key, but clear cached state on body epoch or
dimension changes. `terrain_captured_at` identifies the terrain sample's age.
Action receipts are bounded latest-state records, not a durable event log.
Slow consumers may skip intermediate snapshots, including `started` states.

The private Java bridge applies the latest grant on the game thread and sends
lightweight observations each tick. A stalled bridge loses its grant after
200 ms of wall time; cancellation is applied on the next executing game tick.
Heavy terrain scans remain roughly 1 Hz. All movement uses the native survival
body and bounded navigation; no teleportation or model call is in this path.

## Live measurements, 2026-11-03

The approved rollout was verified with a temporary survival body executing
`look_at` in the live Minecraft JVM. Every result was `done: oriented`; health
remained 20. The probe was removed and its scoped credentials revoked afterward.

| Path | Samples | Ack p95 | Java completion p50 | p95 | p99 / max |
| --- | ---: | ---: | ---: | ---: | ---: |
| Windows client → public internet WSS → Java → client | 100 | 6.795 ms | 30.400 ms | 62.563 ms | 67.648 / 67.648 ms |
| UK host → public TLS endpoint → Java → host, warmed up | 200 | 3.014 ms | 27.503 ms | 58.389 ms | 64.977 / 69.975 ms |
| First UK host run after startup | 100 | 3.286 ms | 30.322 ms | 80.700 ms | 400.865 / 400.865 ms |

Observed tick rate was approximately 20 TPS. Completion includes transport,
the game tick applying the action, and the pushed Java result. This is a
one-body look-action measurement, not a guarantee for ten bodies or navigation,
digging or crafting. The first run's 401 ms outlier is retained rather than
discarded; its exact cause was not isolated. [Measurement data](live-latency-2026-11-03.json).

## Earlier simulated transport benchmark

On 2026-11-03, `benchmarks/websocket_latency.py` ran 100 loopback commands with a
simulated 20 Hz body and an in-memory whitelist. No TLS, internet or real Minecraft
world was involved:

| Measurement | p50 | p95 | p99 |
| --- | ---: | ---: | ---: |
| Gateway acknowledgement | 0.786 ms | 1.435 ms | 2.319 ms |
| Command arrives at simulated body | 1.216 ms | 2.147 ms | 2.852 ms |
| Simulated next-tick result reaches SDK | 33.477 ms | 49.447 ms | 62.522 ms |

The execution target is the next game tick after arrival, nominally within 50 ms
at 20 TPS, plus network and queue time. Tick stalls, terrain scans, whitelist
broker I/O and path search can affect tails. Navigation
completion is separate from command acknowledgement and can take many ticks.
