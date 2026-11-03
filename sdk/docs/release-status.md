# Release status and compatibility

Reviewed **2026-11-03**. SDK, gateway, adapter and client-pack versions describe
different components; their numbers do not need to match.

| Component or feature | Status |
| --- | --- |
| Minecraft client pack 0.1.3 | Published; SCRU branding, 22 mods, no LSO |
| Python SDK / gateway 0.1.2 | Historical download; migrate body control to WebSockets |
| Java adapter 0.4.0 | Historical direct-control baseline |
| Python SDK / gateway 0.2.0.dev1 | Historical direct-control baseline |
| Prefix-free agent names | Live; available valid names may be used by any whitelisted player |
| `move_to`, `look_at`, primitive `stop` | Live; require body-advertised `raw_capabilities` |
| Native navigation | Development Java implementation; live terrain performance and reliability require integration validation |
| Bidirectional WebSocket control and per-tick telemetry | Live; [actual Java latency measurements](realtime.md) |
| SDK / gateway 0.3.0.dev1 and adapter 0.5.0-dev1 | Live controlled single-body experiment; 44 native cases passed, ten-body load failed; [evidence](verification.md) |
| Direct digging, placement, crafting, inventory transfers and containers | Live experimental primitives; complete acceptance remains governed by the [checklist](api-completion-checklist.md) |
| Queued outcomes, complete primitive SDK, async handles and bounded reconnect | Live experimental protocol 2; [player guide](../guidance.md) and [contract](direct-actions.md) |

For new integrations use `scru_minecraft`, `SCRU_AGENT_*`, and `X-SCRU-*`.
Legacy `syn_minecraft`, `SYN_AGENT_*`, and `X-Syn-*` aliases remain for existing
clients. Conflicting current and legacy HTTP headers are rejected. Current
environment variables take precedence over legacy values in the Python SDK.

Check `GET /v1/access` before choosing a name and `GET /v1/me` after login.
For development direct actions, inspect a fresh body's `raw_capabilities` and
`body_epoch`; missing capabilities mean unsupported, regardless of SDK version.

The `/v1` HTTP path is a protocol namespace, not a package version. Readers should
tolerate additional response fields. Do not depend on undocumented fields,
internal endpoints or staged URLs. Candidate result retention is explicitly bounded
in the direct-action contract and is not durable across gateway restarts.

Release checks must cover the SDK, gateway and actual loaded adapter together.
A successful unit test or accepted request does not establish successful movement
in the live world. Java changes require a separately approved maintenance window.

Deployment on 2026-11-03 preserved offline world/gateway backups and the running
controller. Architect completed native navigation through the public SDK. This
does not establish full gameplay, industrial production or multi-body latency.
The approved restart window is consumed; further Java deployments require a new one.
