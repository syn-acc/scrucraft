# Release status and compatibility

**Experimental release:** Python SDK/gateway **0.3.0.dev2** and Java adapter
**0.5.0-dev2**. Versions identify component families; exact published archive and
adapter hashes identify the deployed build. Use the [player guide](../guidance.md).

This release adds bounded result delivery, expiring native grants, complete
metadata reads, recovery fixes and reviewed native mod interactions. Navigation
resolves fractional ground surfaces and handles airborne starts without silently
teleporting or modifying terrain. Dimension-change completion is acknowledged so
ordinary native damage is restored after transfer. Final release-build native
verification is recorded separately. It also corrects delayed native digging that
could survive cancellation in the preceding experimental adapter.

The full [completion checklist](api-completion-checklist.md) remains the release
acceptance record. Ten-body latency and sustained industrial production are not
established. Unit tests and individual gameplay successes do not establish those
gates. See [verification](verification.md) for measured results and retained
failures; use one controlled body while the broader gates remain open.

| Component or interface | Compatibility |
| --- | --- |
| SDK/gateway 0.3.0.dev2 + adapter 0.5.0-dev2 | Experimental protocol 2 release; deploy and roll back as a matched pair |
| SDK/gateway 0.3.0.dev1 + adapter 0.5.0-dev1 | Historical single-body checkpoint; superseded, including its known dig-cancellation defect |
| SDK/gateway 0.2.0.dev1 + adapter 0.4.0 | Historical movement/look/stop baseline |
| Names and ownership | Any whitelisted player may create available valid names and manage their own bodies |
| Direct actions | Body-advertised capabilities are authoritative; SDK installation does not enable missing operations |
| Mod interactions | Only reviewed native menus/ports and documented operations; see [compatibility](mod-compatibility.md) |
| Train and moving-contraption control | Not included in this release |

The dev2 private bridge requires timestamped grants with absolute expiry and
processed-observation acknowledgements. An older gateway cannot drive this adapter;
it fails closed. Internal bridge endpoints remain loopback-only. Public `/v1`
action fields remain compatible, with optional new fields capability-gated.

Use `scru_minecraft`, `SCRU_AGENT_*` and `X-SCRU-*`. Legacy aliases remain accepted;
conflicting current/legacy HTTP headers are rejected. `GET /v1/access` reports
account policy and `GET /v1/me` verifies the authenticated owner. Read a fresh
body's `raw_capabilities` and `body_epoch` before controlling it.

Results and idempotency history are bounded and not durable across gateway
restarts. Inspect uncertain world/inventory outcomes before deciding on another
mutation. Human stop persists through reconnect and requires deliberate owner
resume. Keep credentials private. Further adapter changes require a separately
approved maintenance window.
