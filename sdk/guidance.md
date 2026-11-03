# SCRU Industrial Survival SMP — connect your agent

Join `uk.syn.gl:25565` with the server pack. Every whitelisted player can create
available agent names and control their own survival bodies.

For your agent:

```sh
python -m pip install "scru-minecraft[stream] @ https://uk.syn.gl/minecraft-scru/scru-minecraft-sdk-0.3.0.dev2.zip"
python -m scru_minecraft login YourUsername
```

Ask the player for the code delivered privately in Minecraft. Keep
`.scru-player.env` and scoped body tokens out of prompts, chat and Git.

```python
from scru_minecraft import AgentClient

client = AgentClient.from_file(agent="YourAgent")
client.prepare(create=True, required=["move_to", "look_at"])
with client.realtime() as body:
    x, y, z = body.observe()["position"]
    body.look_at(x + 2, y + 1, z).result()
```

Reuse an existing owned body when appropriate. No work-area selection is required;
omitted/null `area` allows unrestricted survival. Explicit bounds are optional
restrictions. Respect builds and human stops; never automatically resume a stop.

**Experimental release: SDK/gateway 0.3.0.dev2, adapter 0.5.0-dev2.** Read each
body's `raw_capabilities`, inventory and recipe metadata. Build tasks from direct
primitives over persistent WebSockets. Await terminal outcomes; acceptance alone
is not success. Reconnect reconciles uncertain actions without replaying them.

Start with one controlled body. Full API acceptance, ten-body latency and sustained
industrial production are not established. Reviewed mod containers and machine
ports have specific support limits; train control and arbitrary mod interfaces are
not promised. Check [mod compatibility](docs/mod-compatibility.md) before use.

[API](docs/direct-actions.md) · [Python](docs/python-reference.md) ·
[Verification](docs/verification.md) · [Release status](docs/release-status.md) ·
[Source](https://github.com/syn-acc/scrucraft)
