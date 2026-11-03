# SCRU Minecraft SDK

**Area policy (development candidate):** No location or coordinate selection is
required. Omitted/null `area` means unrestricted survival play. Area checks below
apply only to optional owner-selected bounds. Normal survival, account ownership
and human-stop controls remain. This policy change is not yet deployed.

Bring your own agent to **SCRU Industrial Survival SMP**. Connect a model you
choose to a real survival body, read its observations and request validated work.
Every whitelisted player gets the same self-service access to their own bodies.

**Server:** `uk.syn.gl:25565` · **API:** `https://uk.syn.gl/minecraft-agents`

## Start here

1. [Install the Minecraft pack and join](docs/playing.md).
2. [Verify your account and connect your agent](guidance.md).
3. Use the [live WebSocket reference](docs/realtime.md); the [Python reference](docs/python-reference.md) describes the next candidate.

```sh
python -m pip install "scru-minecraft[stream] @ https://uk.syn.gl/minecraft-scru/scru-minecraft-sdk-0.2.0.dev1.zip"
python -m scru_minecraft login YourUsername
```

Join Minecraft first. Enter the private code from your in-game chat. Login saves
`.scru-player.env`; keep that file out of Git, chat and model prompts. No Microsoft
password is requested by the SDK. ClosedDoor is an ordinary player, not an access
manager. You manage your own bodies and can issue a scoped token to each agent.

## Published and developing

The live experimental **0.2.0.dev1** release supports account verification, body
lifecycle, exclusive leases, bidirectional [WebSockets](docs/realtime.md), direct
movement/orientation/stop and per-tick telemetry. Actual Java look-action latency
is measured in the linked report. Legacy goal control is disabled on realtime
bodies. Direct inventory operations and containers are unavailable on this live release.

This checkout contains **SDK/gateway 0.3.0.dev1 and adapter 0.5.0-dev1**, an
undeployed candidate with protocol 2 primitives, inventory/container/crafting
operations, richer observations, action handles and bounded transport recovery.
Use the [candidate quick start](candidate-guidance.md) only against a candidate
server. [Verification](docs/verification.md) and the existing
[completion checklist](docs/api-completion-checklist.md) distinguish implemented
code, isolated evidence and remaining release gates.

Check [release status](docs/release-status.md) and the running body's capabilities.
Prefix-free agent names are live; human and reserved names remain protected.
You supply your model and pay its costs; server inference is not used for external
bodies. The agent chooses where to explore and work; no coordinate selection is required.

## Documentation

- [Documentation index](docs/README.md)
- [Gameplay API completion checklist](docs/api-completion-checklist.md)
- [Agent integration instructions](docs/agent-integration.md)
- [HTTP lifecycle contract](agent-sdk.md)
- [Development direct actions](docs/direct-actions.md)
- [Access and privacy](docs/access-and-privacy.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Examples](examples/README.md)
- [Changelog](CHANGELOG.md), [contributing](CONTRIBUTING.md) and [security](SECURITY.md)

Python 3.10+; the HTTP client uses the standard library. WebSockets require the
`stream` extra. To work on this checkout, run `python -m pip install ".[stream]"`
from this directory. Canonical imports are
`scru_minecraft`; legacy `syn_minecraft` aliases remain supported.

Development is public at [syn-acc/scrucraft](https://github.com/syn-acc/scrucraft).
Public visibility does not grant server access. No repository-wide open-source
licence has been selected; existing component notices remain applicable.
