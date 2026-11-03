# API completion verification

The [API completion checklist](api-completion-checklist.md) is the release scope.
This page records evidence against it, including gaps. It does not redefine the
milestone or turn an implemented method into a verified capability.

Candidate: SDK/gateway **0.3.0.dev1**, adapter **0.5.0-dev1**. Not deployed.
Live versions remain SDK/gateway 0.2.0.dev1 and adapter 0.4.0.

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
