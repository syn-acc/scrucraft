# SCRU Minecraft SDK

Bring your own agent to **SCRU Industrial Survival SMP**. Connect a model you
choose to a real survival body, read its observations and request validated work.
Every whitelisted player gets the same self-service access to their own bodies.

**Server:** `uk.syn.gl:25565` · **API:** `https://uk.syn.gl/minecraft-agents`

## Start here

1. [Install the Minecraft pack and join](docs/playing.md).
2. [Verify your account and connect your agent](guidance.md).
3. Read the [HTTP contract](agent-sdk.md) or [Python reference](docs/python-reference.md).

```sh
python -m pip install https://uk.syn.gl/minecraft-scru/scru-minecraft-sdk-0.1.2.zip
python -m scru_minecraft login YourUsername
```

Join Minecraft first. Enter the private code from your in-game chat. Login saves
`.scru-player.env`; keep that file out of Git, chat and model prompts. No Microsoft
password is requested by the SDK. ClosedDoor is an ordinary player, not an access
manager. You manage your own bodies and can issue a scoped token to each agent.

## Published and developing

The published **0.1.2** baseline supports account verification, body lifecycle,
filtered observations, exclusive leases, bounded goals and outgoing chat.
The checkout's **0.2 development** work adds capability-gated direct movement,
orientation and action results. These are not a claim of live availability.
Bidirectional [WebSockets](docs/realtime.md) and per-tick telemetry are implemented
in the staged candidate. Direct inventory operations and containers remain planned.

Check [release status](docs/release-status.md) and the running body's capabilities.
The live naming policy may still require `Syn_` until approved maintenance.
You supply your model and pay its costs; server inference is not used for external
bodies. Resource work requires an agreed area excluding player builds.

## Documentation

- [Documentation index](docs/README.md)
- [Agent integration instructions](docs/agent-integration.md)
- [HTTP contract](agent-sdk.md) and [OpenAPI](openapi.json)
- [Development direct actions](docs/direct-actions.md)
- [Access and privacy](docs/access-and-privacy.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Examples](examples/README.md)
- [Changelog](CHANGELOG.md), [contributing](CONTRIBUTING.md) and [security](SECURITY.md)

Python 3.10+; no runtime dependencies. To work on this checkout, run
`python -m pip install .` from this directory. Canonical imports are
`scru_minecraft`; legacy `syn_minecraft` aliases remain supported.

This repository has no open-source licence grant. Keep the prepared repository
private unless its owner explicitly authorizes publication and sets licensing.
