# API completion verification

The [API completion checklist](api-completion-checklist.md) is the release scope.
This page records evidence against it, including gaps. It does not redefine the
milestone or turn an implemented method into a verified capability.

SDK/gateway **0.3.0.dev1**, adapter **0.5.0-dev1** are deployed for a controlled
single-body experimental session. Full checklist acceptance remains incomplete.

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

Additional real concurrent-viewer, container-disconnect and slow-consumer fixtures
are implemented locally but have not yet run against Minecraft. Their presence
in the repository is not passing evidence.

The controlled checkpoint has a separate [artifact manifest](evidence/controlled-candidate-20261103.json).

Deployment was verified on 2026-11-03 with offline world/gateway backups,
Minecraft PID 2205174, gateway PID 2205169 and unchanged controller PID 3192194.
Audit: `uk:/data/minecraft-syn-smp/ops/architect-release-20261103T213025Z`.
Architect joined as Jamie_Syn's survival body and completed an SDK navigation
request. This first smoke result is not a live latency measurement. The published
SDK ZIP has documentation-only adjustments (SHA-256
`3d760a411eab7837960a93cfd1ff4d95bdd4f8cd5d9b26ef6b20c0947cf0f95c`);
Its runtime was verified against the frozen build.

## Subsequent development work: 0.3.0.dev2 (not deployed)

199 local checks cover targeted stream conditions, acknowledged-result pruning,
64 recent transitions plus unfinished work, and authoritative SDK fallback.
The [synthetic benchmark](../../benchmarks/transport/README.md) records a short
repeat with less traffic and CPU. It does not run Minecraft, and short-run latency
varies. No native or live ten-body success is claimed for these changes.

## Live observation defect: phantom hostility

Live telemetry reported `minecraft:phantom` with `hostile:false` at 21:38:11 on 2026-11-03.
Architect's health decreased from 20 to about 16.17 during nearby movement/idle.
This is evidence of incorrect classification, not proof that all movement drift
or damage came from that entity. Source uses `ent instanceof Monster`; broader
hostile-class coverage and native regression cases remain required under OBS-02.
No Java replacement or additional restart was performed for this report.

## Live dig outcome discrepancy

[Minimal evidence](evidence/live-dig-reconciliation-20261103.json) records a dig
that failed with `held_item_changed` as an empty selected slot picked up dirt.
The later authoritative query returned air at the original target; inventory
contained two dirt instead of one. No dig retry was sent. This requires ACT-07
and EXEC-02/03/04 follow-up, including whether native delayed breaking continues
after abort. The evidence does not by itself prove the precise mutation order
or exclude another world change. Until resolved, failed digs require world and
inventory reconciliation before any retry. No live Java change was made.

Source follow-up confirmed the cancellation hazard in the exact NeoForge 1.21.1
`ServerPlayerGameMode`: an early STOP packet activates delayed destruction, while
ABORT does not clear that delayed state. Our adapter sends STOP on the next tick.
A later native break can therefore occur after the adapter reports failure or
cancellation. This mechanism is confirmed from source; a deterministic native
regression and a verified fix are still required. The controlled first session
ended safely sheltered; isolated testing is permitted again, but no further live
maintenance window has been approved.

ACT-07/SDK-05 documentation mitigation was published at 21:44 UTC on 2026-11-03.
The live guide warns that failed/cancelled digs may finish later. HTTPS contents
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
does **not** prove an actual player's chat-delivered stop. The live adapter has
not received these corrections.

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

Later local source includes additional body, menu, authorization and SDK changes
that these frozen runs did not execute. The original checklist remains **8/40**.

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
backpack/pot/corpse menus and dimension guards. Their new full-pack fixtures and
clean-install example runner have **not yet passed native acceptance**. The latest
native load result remains the failed run 07 above. Source publication does not
deploy or close those checklist items. The gateway and adapter form a paired
bridge release; see [compatibility](release-status.md).
