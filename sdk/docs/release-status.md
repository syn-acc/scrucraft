# Release status and compatibility

Reviewed **2026-11-03**. SDK, gateway, adapter and client-pack versions describe
different components; their numbers do not need to match.

| Component or feature | Status |
| --- | --- |
| Minecraft client pack 0.1.3 | Published; SCRU branding, 22 mods, no LSO |
| Python SDK / gateway 0.1.2 | Published baseline: self-service login, bodies, leases, observations, goals, outgoing chat |
| Java adapter 0.3.2 | Last recorded live adapter |
| Python SDK / gateway 0.2.0.dev1 | Development source; direct-action additions are not a live-release claim |
| Prefix-free agent names | Pending an explicitly approved Minecraft maintenance release; query `/v1/access` |
| `move_to`, `look_at`, primitive `stop` | Development milestone; require body-advertised `raw_capabilities` |
| Native navigation | Development Java implementation; live terrain performance and reliability require integration validation |
| Bidirectional WebSocket control and per-tick telemetry | Implemented in staged development; [contract and measurements](realtime.md); not deployed |
| Direct digging, placement, crafting, inventory transfers and containers | Planned; not exposed by the documented client API |

For new integrations use `scru_minecraft`, `SCRU_AGENT_*`, and `X-SCRU-*`.
Legacy `syn_minecraft`, `SYN_AGENT_*`, and `X-Syn-*` aliases remain for existing
clients. Conflicting current and legacy HTTP headers are rejected. Current
environment variables take precedence over legacy values in the Python SDK.

Check `GET /v1/access` before choosing a name and `GET /v1/me` after login.
For development direct actions, inspect a fresh body's `raw_capabilities` and
`body_epoch`; missing capabilities mean unsupported, regardless of SDK version.

The `/v1` HTTP path is a protocol namespace, not a package version. Readers should
tolerate additional response fields. Do not depend on undocumented fields,
internal endpoints, a particular body-result retention duration, or staged URLs.

Release checks must cover the SDK, gateway and actual loaded adapter together.
A successful unit test or accepted request does not establish successful movement
in the live world. Java changes require a separately approved maintenance window.
