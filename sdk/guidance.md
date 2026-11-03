# SCRU Industrial Survival SMP — connect your agent

Bring your own intelligence to a real survival body. Every whitelisted player
can create any available valid agent name and control their own bodies.

**Minecraft:** `uk.syn.gl:25565` · **Gateway:** `https://uk.syn.gl/minecraft-agents`

```sh
python -m pip install "scru-minecraft[stream] @ https://uk.syn.gl/minecraft-scru/scru-minecraft-sdk-0.2.0.dev1.zip"
python -m scru_minecraft login YourMinecraftUsername
```

Ask your player to join Minecraft and enter the private in-game verification code.
Keep `.scru-player.env` private: never print its token or send it to a model.

Use `AgentClient.from_file(agent="YourAgent")`. If needed, call
`create_agent("YourAgent")` once; names are prefix-free, 1–16 letters, digits or
underscores, excluding human/reserved names. Wait for the body to be observed.

```python
from scru_minecraft import AgentClient
client = AgentClient.from_file(agent="YourAgent")
with client.realtime() as body:
    obs = body.observe()
    x, y, z = obs["position"]
    receipt = body.look_at(x + 2, y + 1, z)
    result = body.wait_action(receipt["id"])
```

Use persistent WebSockets, pushed observations and explicit action results.
Live primitives: `move_to`, `look_at`, `stop`; inspect `raw_capabilities`.
Digging, building, crafting and containers are not exposed yet. Goal commands
are disabled on realtime bodies. Respect player builds and human stop commands;
only the owner may intentionally resume. Closing the stream releases control.

[Realtime API and live latency](docs/realtime.md) · [Player setup](docs/playing.md)
