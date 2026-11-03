# Changelog

Package versions are separate from Minecraft client-pack and adapter versions.
See [release status](docs/release-status.md) before using development features.

## 0.2 development — unreleased

- First direct-control milestone: capability-gated movement, looking and stopping,
  with body epochs and executor results. Native navigation is developed alongside
  the Java adapter and requires integration verification and approved deployment.
- Reorganized client documentation; explicit live/development contracts, OpenAPI,
  access model, troubleshooting and read-only examples.
- WebSocket streaming and inventory/container actions remain planned.

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
