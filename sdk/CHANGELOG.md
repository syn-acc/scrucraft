# Changelog



Package versions are separate from Minecraft client-pack and adapter versions.

See [release status](docs/release-status.md) before using development features.



## 0.3.0.dev1 — controlled experimental checkpoint



- Protocol 2 bounded command queue, retained outcomes, native result acknowledgements

  and compact snapshots. Compatible look/navigation controls are independent.

- Direct inventory/hand/toggle, world/entity, container/crafting and public chat

  operations, plus explicit block and recipe queries, gated by executor capabilities.

- Sync and async action handles, finite readiness, typed subscriptions, diagnostics,

  and bounded reconnect/resync that reconciles results without mutation replay.

- Structured native failures, per-call authority/work-area checks and prompt safety

  stop. Full gameplay and performance evidence is tracked by the existing checklist;

  see [verification](docs/verification.md). Production remains on the release below.



## 0.2.0.dev1 — live experimental release, 2026-11-03



- First direct-control milestone: capability-gated movement, looking and stopping,

  with body epochs and executor results. Native navigation is developed alongside

  the Java adapter. Adapter 0.4.0 was deployed in an approved restart window;

  terrain traversal reliability still requires integration verification.

- Reorganized client documentation; explicit live/development contracts, OpenAPI,

  access model, troubleshooting and read-only examples.

- Bidirectional WebSockets and per-tick telemetry deployed and verified with

  actual Java look-action results. Windows-client p95 completion: 62.563 ms.

- Prefix-free names are live. Inventory/container actions remain planned.



## 0.1.2 — published baseline, 2026-11-02



- Self-service login through a private code delivered to a whitelisted Minecraft

  account. Player credentials bind to UUID, with membership rechecks.

- Every player manages their own bodies. Earlier unverified manager credentials

  were revoked; ClosedDoor is an ordinary member.



## 0.1.1 — 2026-11-02



- SCRU branding, `scru_minecraft`, `SCRU_AGENT_*` and `X-SCRU-*`, retaining legacy

  compatibility aliases and rejecting conflicting HTTP identity headers.



## 0.1.0 — historical



- Initial owner-scoped lifecycle, leases, goal control, observations and outgoing

  speech. Its original access handoff model is superseded by 0.1.2.
