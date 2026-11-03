# Development transport profile

These experiments run ten synthetic Python body connections and ten SDK clients
over local loopback WebSockets, targeting 20 body frames/second and five actions
per second per body. Each body starts with 350 retained, already acknowledged
receipts. The synthetic executor completes look actions without Minecraft.
The process CPU measurement includes the gateway, synthetic bodies, and SDK clients.

Commit `1ca5452d0786cbdc3055c68c27f988a70252d5cf` contains the source before
the development optimization, matching the 194-test frozen handoff runtime. The current development source changes targeted
condition notifications, pending native ACK retention, and bounded public receipt
windows. SDK fallback additionally queries missing receipts once when a snapshot
explicitly marks its history window as truncated. No mutation is replayed.

Saved sequential repeat (`baseline-repeat.json`, `optimized-repeat.json`):

| Metric | Baseline | Development |
| --- | ---: | ---: |
| Duration | 8.172 s | 8.203 s |
| Completed actions | 388 | 383 |
| Errors | 0 | 0 |
| Completion p95 | 125 ms | 94 ms |
| Process CPU | 8.078 s | 4.969 s |
| Grant bytes | 15,098,832 | 430,494 |
| Condition wakeups | 6,210 | 3,136 |

An earlier same-shape pair had baseline p95 375 ms and development p95 78 ms;
short local timing varies. The repeat demonstrates less repeated traffic and CPU,
not a precise or sustained performance guarantee. These numbers are not live
Minecraft latency, do not validate native grants, and do not pass VERIFY-05.
The frozen single-body handoff and production files were not modified.

The development source passes 199 local regression tests, including actual
loopback socket checks for 64 pushed transitions with full older receipt lookup,
old long-running completion recency, deferred result inclusion, ACK confirmation
and replay, 600-second history expiry, epoch-safe SDK reconciliation, policy
revocation/stop, and targeted condition notifications.

Run from the repository with `agent-gateway/requirements.txt` installed:

```sh
git worktree add /tmp/scru-baseline 1ca5452d0786cbdc3055c68c27f988a70252d5cf
python benchmarks/transport/profile_stream.py --source /tmp/scru-baseline/agent-gateway --seconds 8 --history 350
python benchmarks/transport/profile_stream.py --seconds 8 --history 350
```

Use an equivalent fresh path on Windows. The script imports the current SDK for
both runs; it compares gateway transport behavior, not end-to-end release builds.
Saved results came from the local pre-version-bump checkout. No baseline source
copy or production credentials are distributed with this benchmark.
