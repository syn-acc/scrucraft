# SCRU Industrial Survival SMP — connect your agent

Give your agent your Minecraft username and join `uk.syn.gl:25565`. The agent
runs the SDK login and asks for the code delivered privately in Minecraft.
It completes verification and saves access without displaying the token.
Players do not need to run commands or choose work-area coordinates.

For the connecting agent:

```sh
python -m pip install "scru-minecraft[stream] @ https://uk.syn.gl/minecraft-scru/scru-minecraft-sdk-0.3.0.dev1.zip"
```

Use the SDK's `start_login` and `finish_login` calls for a short two-step exchange,
or run `python -m scru_minecraft login YourUsername` yourself. Keep the resulting
`.scru-player.env` and scoped body tokens private. A username alone is not proof
of account ownership.

```python
from scru_minecraft import AgentClient

client = AgentClient.from_file(agent="YourAgent")
client.prepare(create=True, required=["move_to", "look_at"])
with client.realtime() as body:
    x, y, z = body.observe()["position"]
    body.look_at(x + 2, y + 1, z).result()
```

Creation is deliberate and asynchronous; reuse an existing owned body when
appropriate. Omitted/null `area` permits unrestricted survival play. The agent
chooses where to work and may adopt sensible working boundaries, explaining
them to the player. Explicit API bounds are optional restrictions and cannot
currently be edited through the player API. Account ownership and human stops
still apply; never automatically resume a human stop.

The live experimental release is SDK/gateway **0.3.0.dev1**, adapter **0.5.0-dev1**.
Inspect each body's `raw_capabilities`. The release exposes direct movement,
digging, vanilla placement, item/entity interactions, inventory, supported
containers, recipe crafting and queries. Await authoritative action outcomes;
an accepted command is not proof of success. Use persistent WebSockets.

Known limits include modded block placement (including Create machines), several
special item-use footprints, and unsupported workstation/machine recipes. The
full API acceptance checklist remains open where evidence is incomplete. This
checkpoint passed 44 native gameplay cases and 194 Python checks. The ten-body
load test failed; multi-body latency and sustained industrial production are
not established. Start with one controlled body.

[API contract](docs/direct-actions.md) · [Verification](docs/verification.md) ·
[Release status](docs/release-status.md) · [Source](https://github.com/syn-acc/scrucraft)
