# API completion verification

The [API completion checklist](api-completion-checklist.md) is the release scope.
This page records evidence against it, including gaps. It does not redefine the
milestone or turn an implemented method into a verified capability.

## Experimental dev2 assessment

The release build is SDK/gateway **0.3.0.dev2** with adapter **0.5.0-dev2**.
It includes the frozen protocol/recovery/mod-port work plus native navigation
corrections for fractional ground and airborne starts. `AgentPlayer` now
acknowledges dimension-change completion so Minecraft's dimension-transition
latch no longer prevents ordinary native damage. Named dimension/damage regressions pass in run 10. The final adapter passes
all 15 focused navigation/control checks in run 11. Run 12 verifies the finite
survival journey outside BetterDifficulty's native spawn-protection area.
Post-freeze MOD-08 train/contraption drafts are excluded.

**10/40 original criteria are checked; 30 remain open.** The 13 additional pack,
mod and survival requirements remain separately open. The packaged release suite
passes **190 tests**. Runs 07/08 provide build-scoped native evidence described
below; earlier failures remain recorded. The five-minute run 10 load result failed its original latency/throughput targets.
Exact final artifact hashes and deployment smoke are recorded separately. No comprehensive or ten-body performance pass is claimed.

## Historical evidence and build boundaries

The sections below preserve the exact builds and measured outcomes from earlier
checkpoints. A historical statement that a change was undeployed or unrun applies
to that checkpoint only. It does not override the release 04 assessment above.

## Automated checks

Run `python -m unittest discover -s tests -v` after installing
`agent-gateway/requirements.txt`. The protocol tests exercise command delivery,
retry identity, cancellation, epoch and ownership checks, SDK handles, and actual
loopback WebSockets. They use synthetic body frames; they do not establish
Minecraft mechanics or real-player enrollment.

Run `gradle -p agent-mod build` with JDK 21 and the documented dependencies.
Registered Java checks include inventory conservation, ingredient assignment
(13,824 exhaustive small matching cases against an independent oracle), name
validation, navigation search, and confinement of the private body-stream URL
to loopback. Search tests do not establish physical traversal.

## Isolated Minecraft checks

`tests/isolated_game_fixture.py` launches a new NeoForge 21.1.265 world, candidate
adapter, LuckPerms, gateway, and public SDK connection. It uses its own synthetic
identity and generated private bridge token, and binds to loopback. It requires
a new directory, preserves logs and JSON evidence, and stops only its own JVM.
Never point its output directory at a production server or copy production world
data or credentials into it.

```sh
python tests/isolated_game_fixture.py \
  --directory /path/to/new-fixture-directory \
  --libraries /path/to/neoforge/libraries \
  --adapter /path/to/syn-agents-0.5.0-dev1.jar \
  --luckperms /path/to/LuckPerms-NeoForge-5.4.150.jar
```

Fixture console commands arrange known starting conditions. Measured operations
then use the SDK, gateway and loaded adapter. Each case links its evidence to
checklist IDs. Logs distinguish supplied materials/infrastructure from gathered
or crafted items. Concurrent-container tests using console changes are explicitly
identified; they do not claim a second human participated.

An isolated success does not prove production mod compatibility, real in-game
login delivery, sustained ten-body performance, or every failure criterion.
Those remain release requirements. Deployment additionally needs the maintenance
window and rollback evidence required by VERIFY-06.

## Performance acceptance, fixed before the load run

For VERIFY-05, collect at least five minutes after startup with ten controlled
bodies. Retain startup separately, plus every steady-state sample and outlier.
Record CPU/memory limits, hardware, mod list, round-trip location, observation
age, game tick timing, per-body counts, and slow-consumer behavior.

For simple instant actions on the same host, targets are p95 acknowledgement
under 25 ms, p95 actual Java completion under 150 ms, p99 under 250 ms, and at
least 19 game ticks/second over the steady-state interval. All bodies must make
progress, at least 99% of connected observation gaps must remain below 250 ms,
and accepted commands must not silently disappear. Digging/navigation duration
is reported separately from these instant-action timings. A resource-constrained
fixture run is labeled as such and cannot establish production load capacity.

## Recorded candidate runs

[Draft PR #1](https://github.com/syn-acc/scrucraft/pull/1) contains the implementation
and retained evidence. The current workspace suite passes 194 Python checks; the
exact final public source package passes 153. The 194 include load fan-out, silent revocation, expired-handle/epoch reconciliation and malformed-input parity regressions.

| Run | Native cases passed | Failed checks |
| --- | ---: | --- |
| [01](evidence/api-fixture-run-01.json) | 11 | None in that initial subset |
| [02](evidence/api-fixture-run-02.json) | 31 | Load setup exceeded fixture thread limit |
| [03](evidence/api-fixture-run-03.json) | 35 | Unicode fixture input; load transport failure |
| [04](evidence/api-fixture-run-04.json) | 40 | Optional-area layout; respawn accounting; load backlog |
| [05](evidence/api-fixture-run-05.json) | 44 | Ten-body load backlog persists |

Run 04 verifies the four command-result regressions, including old terminal
receipts, unacknowledged payloads, retransmission identity and remaining deadlines.
It also verifies complete Unicode component reconstruction. Its load failure exposed
cross-body wakeup amplification; no successful five-minute capacity result is claimed.
The respawn failure was caused by natural pickup at the death location, confirmed
by native player statistics. Corrected fixtures and the transport fix require a new run.

Eight individually supported checklist entries are checked as candidate-complete.
The remaining entries retain their original acceptance criteria. In particular,
second-viewer container concurrency, nonempty cursor cleanup, broader terrain,
slow consumers, real-player full gameplay and live release evidence remain open.

The final SDK installs through its declared build dependencies in a clean Python
3.11 environment. Installed module hashes match the candidate source and CLI help
runs successfully. A no-build-isolation attempt first failed because that clean
environment lacked wheel; the standard documented install succeeds.

## Controlled single-body checkpoint

Run 05 passes all 44 native gameplay cases, including unrestricted-area play,
death/respawn with fresh control, full double-chest layout and administrator
stop persistence followed by explicit owner resume. These use synthetic accounts;
they do not claim a real human chat event or complete production acceptance.

The ten-body test still fails after 44.7 seconds: acknowledgement p95 149.564 ms,
completion p95 2643.372 ms, with one pending action timing out. This fails the
predeclared targets. Raw samples and outliers remain under the isolated run-05
`performance.json`; no sustained five-minute success is claimed. The test ran on
a four-vCPU Intel Xeon Sapphire Rapids KVM host with the 150% CPU, 2400 MiB service
memory and 1536 MiB JVM heap limits recorded in the harness, using loopback traffic.

The owner separately authorized a controlled experimental single-body deployment.
That checkpoint does not complete this checklist or establish multi-body capacity.
Two subsequent SDK edge fixes are covered by focused HTTP/WSS tests: expired
handles return explicit unknown outcomes and retain their body epoch; malformed
typed fields return consistent 400 errors. Runtime hashes identify that frozen
candidate separately from run 05's source fingerprints.

At the run 05 checkpoint, additional concurrent-viewer, container-disconnect and
slow-consumer fixtures had only local coverage. Runs 07/08 below provide subsequent
native evidence; neither source presence nor a later pass rewrites run 05.

The controlled checkpoint has a separate [artifact manifest](evidence/controlled-candidate-20261103.json).

Deployment was verified on 2026-11-03 with offline world/gateway backups,
Minecraft PID 2205174, gateway PID 2205169 and unchanged controller PID 3192194.
Audit: `uk:/data/minecraft-syn-smp/ops/architect-release-20261103T213025Z`.
Architect joined as Jamie_Syn's survival body and completed an SDK navigation
request. This first smoke result is not a live latency measurement. The published
SDK ZIP has documentation-only adjustments (SHA-256
`3d760a411eab7837960a93cfd1ff4d95bdd4f8cd5d9b26ef6b20c0947cf0f95c`);
Its runtime was verified against the frozen build.

## Historical initial dev2 development checkpoint

199 local checks cover targeted stream conditions, acknowledged-result pruning,
64 recent transitions plus unfinished work, and authoritative SDK fallback.
The [synthetic benchmark](../../benchmarks/transport/README.md) records a short
repeat with less traffic and CPU. It does not run Minecraft, and short-run latency
varies. No native or live ten-body success is claimed for these changes.

## Historical dev1 observation defect: phantom hostility

Live telemetry reported `minecraft:phantom` with `hostile:false` at 21:38:11 on 2026-11-03.
Architect's health decreased from 20 to about 16.17 during nearby movement/idle.
This is evidence of incorrect classification, not proof that all movement drift
or damage came from that entity. The affected source used `ent instanceof Monster`. Run 07 below verifies broader
native Enemy-marker classification; the remaining OBS-02 criteria stay open.
No Java replacement or additional restart was performed for this report.

## Historical dev1 dig outcome discrepancy

[Minimal evidence](evidence/live-dig-reconciliation-20261103.json) records a dig
that failed with `held_item_changed` as an empty selected slot picked up dirt.
The later authoritative query returned air at the original target; inventory
contained two dirt instead of one. No dig retry was sent. This requires ACT-07
and EXEC-02/03/04 follow-up, including whether native delayed breaking continues
after abort. The evidence does not by itself prove the precise mutation order
or exclude another world change. At that checkpoint the defect remained unresolved. Uncertain failed actions
still require world and inventory reconciliation before any retry. No live Java change was made.

Source follow-up confirmed the cancellation hazard in the exact NeoForge 1.21.1
`ServerPlayerGameMode`: an early STOP packet activates delayed destruction, while
ABORT does not clear that delayed state. The affected adapter sent STOP on the next tick.
A later native break can therefore occur after the adapter reports failure or
cancellation. This mechanism is confirmed from source; the deterministic native correction is subsequently exercised in run 07 below.
The controlled first session ended safely sheltered. Its maintenance history is
separate from the release 04 deployment and smoke checks.

ACT-07/SDK-05 documentation mitigation was published at 21:44 UTC on 2026-11-03.
The dev1 guide warned that failed/cancelled digs could finish later. HTTPS contents
matched SHA-256 `4789594c42a06c4a41d269dc1cc036a924181b63e2fe992ea2800982ace6aca1`;
all three runtime PIDs stayed unchanged. Backup/audit:
`uk:/data/minecraft-syn-smp/ops/guide-dig-limit-20261103T214434Z`.
This completes the warning task, not the native fix or ACT-07 acceptance.

## Full-pack development runs 06 and 07

[Run 06](evidence/api-fixture-run-06.json) and
[run 07](evidence/api-fixture-run-07.json) use all 25 lock-pinned public server
mods, a fresh world/default configuration and the candidate delayed-dig fix.
Each record contains the exact adapter, Python source and mod hashes. Run 06
passed 28 cases, then an incorrect HTTP-to-WebSocket fixture route prevented
owner resume and caused subsequent failures. Its failures remain recorded.

Run 07 corrects that fixture routing and passes **52 native cases**. Pickup-driven
failure, explicit cancel, owner stop, lease release, grant expiry and an injected
administrative stop all preserve the target after 90 native ticks. Redstone's
native start-state change remains mineable. The administrative-stop case is
named `dig_human_stop_cannot_destroy_later` in the machine-readable record; it
does **not** prove an actual player's chat-delivered stop. The dev1 adapter had not received those corrections at the time of run 07.

Two cases fail. Death/respawn correctly changes epoch and closes controls, but
the vanilla loose-diamond assertion fails because the installed Corpse mod stores
inventory in a corpse. Authorized native corpse recovery is now required under
MOD-07/SURV-02. This is an uncovered pack workflow, not evidence of item loss.

The [native performance report](evidence/native-performance-run-07.json) fails
after 42.4 seconds: acknowledgement p95 **132.566 ms**, completion p95
**3106.542 ms**, observation-gap p99 **455.149 ms**, and a pending action timeout.
Per-body measured TPS is below 19. Slow-observer recovery and controlling-lease
preservation also fail. All predeclared thresholds remain unchanged; the short
synthetic improvements do not establish native performance. A separate
instrumented full-pack diagnostic investigates CPU, message sizes and release
causes; instrumented timings cannot count as acceptance evidence.

Subsequent body, menu, authorization and SDK changes were not part of those
frozen runs. The checklist stood at **8/40** then; the later SDK assessment below
brings the current total to **10/40** without changing those earlier results.

## Real human-chat stop verification

On 2026-11-03 Jamie_Syn typed `Architect, stop` in Minecraft. The live SDK observed
that exact public message, then verified persistent suspension and no active
lease. A guarded fresh connection refused control with HTTP-equivalent 423
`human_stop_requires_resume`; suspension and absent lease remained unchanged.
[Minimal evidence](evidence/live-human-stop-20261103.json) excludes credentials
and coordinates. No resume, gameplay action or restart occurred. Architect was
already idle, so this closes the real delivery/persistence portion of OBS-04,
EXEC-03 and VERIFY-04, not their active-action cancellation or privacy criteria.

## Published source checkpoint after full-pack run 07

The subsequent dev2 source passes **216 workspace Python tests**, **175 tests in
the exact source-only public package**, and the Java build/check tasks. Java checks
cover grant clocks/original deadlines, 11 endpoint cases, 13 name assertions,
11 inventory conservation assertions, 9 navigation checks, and 13,824 exhaustive
ingredient-assignment cases. A real Java/Python WebSocket probe passes stale-grant
rejection, processed-observation ACK backpressure, two-second ACK-stall reconnect,
no replay, fresh stop, expiry and close.

This checkpoint also compiles the native industrial item ports, reviewed storage,
backpack/pot/corpse menus and dimension guards. At that source checkpoint, their new full-pack fixtures and clean-install example
runner had **not yet passed native acceptance**, and run 07 was the latest load
result. Run 08 below advances specific cases. Source publication alone does not
deploy or close checklist items. The gateway and adapter form a paired
bridge release; see [compatibility](release-status.md).

## Full-pack run 08 and individual SDK criteria

[Run 08](evidence/api-fixture-run-08.json) passes native depot, pressing, mixing,
barrel/shulker storage, heated cooking-pot and cutting-board cases. Three early
failures identify a millstone probability assertion, a chest revision change and
a portable-backpack ownership check. Later, intentionally withholding native
grants also withholds observation ACKs; the new two-second watchdog reconnects
and releases the lease. The test did not explicitly reacquire it, causing a
cascade of disconnected-case failures. Those records remain failed; fixes and
independent-case recovery require a new run.

The clean installed SDK examples pass, including exact synchronous/asynchronous
reference snippets, observation and stop examples, verified loopback TLS and
matching installed module hashes. Combined with the separate
[real enrollment record](evidence/live-enrollment-20261103.json) and checkpoint
helper/pacing/error tests, the original **SDK-01** and **SDK-04** criteria are
complete for this build. The original checklist is now **10/40**. This is an
individual evidence assessment, not native release or performance acceptance.

The [five-minute load report](evidence/native-performance-run-08.json) records
300.3 seconds without action errors, about 20 TPS for all ten bodies, and isolated
slow-observer disconnection with the controlling lease preserved. It still
**fails**: each body completes about 2.5 actions/second rather than the required
four; ACK p95 is 255.516 ms, completion p95 834.398 ms and observation-gap p99
755.737 ms. Targets remain unchanged.

The fixture ran gateway, ten SDK clients and ten watchers in one Python
interpreter, using 95.2% of one CPU. The aggregate cgroup used about 116.6% of one
CPU under its 150% limit. Native receive lag p95 was 278 ms and post-gateway SDK
age p95 was 193 ms. A subsequent measurement separates client/watchers into a
subprocess, as in actual player deployments, while retaining the same aggregate
CPU limit, workload and targets. This is a measurement-topology correction,
not a runtime optimization or a passing performance claim.

## Full-pack development run 09

[Run 09](evidence/api-fixture-run-09.json) passed 97 of 105 native gameplay
cases. Eight failures led to the release04 navigation/dimension fixes and
native-behavior fixture corrections; their follow-up evidence is retained in runs 10 and 11 below.

The [five-minute native load report](evidence/native-performance-run-09.json)
keeps the same 150% CPU limit and original acceptance targets, with SDK clients
in a separate interpreter from the gateway. All ten bodies completed the window
without action errors, but per-body throughput was approximately 3.3 actions/s,
below the 4/s floor. ACK p95 was 152.920 ms and Java completion p95 was 537.439 ms
(p99 732.029 ms); observation-gap p99 was 471.954 ms. The latency and throughput
gate failed. Earlier failed measurements remain part of the record.

## Full-pack regression run 10

[Run 10](evidence/api-fixture-run-10.json) passed **105 of 107 gameplay cases**
with adapter SHA-256 `5201a6f5a82ff070728b5f6bac5460d86706fe885259f5a0d4c38b8143bfda5e`.
It verifies real fractional-ground traversal, native waterwheel/mill processing,
fluid handling, seasonal greenhouse behavior, damage after dimension travel,
death/respawn and owner corpse recovery. The recorded `respawn_seconds` includes
recovery and a fresh control action; it is not a pure respawn-latency measurement.

The survival crop approach and held-jump route did not pass. Their results are
retained; a targeted final-build regression follows the fixture and navigation
corrections. The adapter's collision and damage fixes passed their named cases.

The [load report](evidence/native-performance-run-10.json) completed 300.268 seconds
with ten bodies, no action errors and roughly 20 TPS per body. Per-body completion
counts were 1,020–1,043 (about 3.4/s), below the 4/s floor. ACK p95 was **143.106 ms**,
Java completion p95 **510.853 ms** and p99 **699.554 ms**; observation-gap p99 was
**459.583 ms**. The predeclared throughput/latency targets remain failed.

## Final adapter regression run 11

[Run 11](evidence/api-fixture-run-11.json) uses the final adapter SHA-256
`6b6f676f6c0f7aa74090b5adf0e82406ec5434d68ca2905156a429891eba05d8`.
Its explicit `release-regressions` suite passes **15 of 16 cases**, including
held-jump navigation, a one-block arrival in five native ticks, fractional ground,
slabs/stairs, changed terrain, safe drops and rejection of unsupported endpoints.
The navigation controller is the only runtime source file changed since run 10;
the gateway, SDK and other Java adapter sources are unchanged. Java build/checks
pass; the packaged Python suite passes 190 tests.

The survival case passed its harvest, food, natural-healing and shelter assertions
before timing out while waiting to observe the spawned hostile. Its threat-response
and complete survival-journey criterion remain **unverified**. No full-suite pass
or ten-body performance pass is inferred from this focused run. All earlier
failures remain linked. The fixtures select their adapter explicitly; the final
lockfile updates that custom adapter hash while retaining the same public-mod hashes.

## Final survival follow-up run 12

[Run 12](evidence/api-fixture-run-12.json) passes the finite survival case on the
same final adapter, without runtime changes. BetterDifficulty had correctly
blocked the run 11 monster inside its 32-block world-spawn protection. The
follow-up moves the fixture's shared spawn away during the threat test and
restores it afterward; it does not disable that mod protection.

The SDK harvested 12 wheat, crafted four bread and ate two, recovered health
from 14 to 20 through native food regeneration, and converted four raw logs into
16 planks. It placed 13 shelter blocks and retained three. An active zombie was
observed; the agent retreated behind its wall and beneath its roof without
losing health. All 36 seed drops were accounted for. Initial crops, raw logs,
crafting table and work scaffold were declared fixture inputs. This finite proof
does not establish sustained self-sufficiency, industrial output, or completion
of every original/additional checklist criterion. Run 11 remains recorded as failed.
