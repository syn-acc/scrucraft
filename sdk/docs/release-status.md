# Release status and compatibility

Reviewed **2026-11-03**. SDK, gateway, adapter and client-pack versions describe
different components; their numbers do not need to match.

| Component or feature | Status |
| --- | --- |
| Minecraft client pack 0.1.3 | Published; SCRU branding, 22 mods, no LSO |
| Python SDK / gateway 0.1.2 | Historical download; migrate body control to WebSockets |
| Java adapter 0.4.0 | Live after approved restart on 2026-11-03 |
| Python SDK / gateway 0.2.0.dev1 | Live experimental release: self-service identity, lifecycle and direct WebSocket controls |
| Prefix-free agent names | Live; available valid names may be used by any whitelisted player |
| `move_to`, `look_at`, primitive `stop` | Live; require body-advertised `raw_capabilities` |
| Native navigation | Development Java implementation; live terrain performance and reliability require integration validation |
| Bidirectional WebSocket control and per-tick telemetry | Live; [actual Java latency measurements](realtime.md) |
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
