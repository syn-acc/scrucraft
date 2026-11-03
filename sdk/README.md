# SCRU Minecraft SDK

**Area policy (experimental release):** No location or coordinate selection is
required. Omitted/null `area` means unrestricted survival play. Area checks below
apply only to optional owner-selected bounds. Normal survival, account ownership
and human-stop controls remain. This policy is live in the controlled experimental release.

Bring your own agent to **SCRU Industrial Survival SMP**. Connect a model you
choose to a real survival body, read its observations and request validated work.
Every whitelisted player gets the same self-service access to their own bodies.

**Server:** `uk.syn.gl:25565` · **API:** `https://uk.syn.gl/minecraft-agents`

## Start here

1. [Install the Minecraft pack and join](docs/playing.md).
2. [Verify your account and connect your agent](guidance.md).
3. Use the [live WebSocket reference](docs/realtime.md); the [Python reference](docs/python-reference.md) covers the experimental gameplay API.

```sh
python -m pip install "scru-minecraft[stream] @ https://uk.syn.gl/minecraft-scru/scru-minecraft-sdk-0.3.0.dev2.zip"
python -m scru_minecraft login YourUsername
```

Join Minecraft first. Enter the private code from your in-game chat. Login saves
`.scru-player.env`; keep that file out of Git, chat and model prompts. No Microsoft
password is requested by the SDK. ClosedDoor is an ordinary player, not an access
manager. You manage your own bodies and can issue a scoped token to each agent.

## Published and developing

The experimental **SDK/gateway 0.3.0.dev2 and adapter 0.5.0-dev2** support
identity, body lifecycle, WebSockets, native gameplay primitives and reviewed mod
interactions. This release includes cancellation/recovery fixes and navigation
corrections. Full checklist acceptance, ten-body latency and sustained industrial
production remain incomplete. Start with one controlled body; check the
[mod compatibility limits](docs/mod-compatibility.md) before industrial work.
Use the [player guide](guidance.md) and inspect the active body's capabilities.
[Verification](docs/verification.md) and the existing
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
- [Direct actions](docs/direct-actions.md)
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

Release SDK: **0.3.0.dev2**. Match the published artifact hashes and running
capabilities; a version label alone does not establish tested behavior.
