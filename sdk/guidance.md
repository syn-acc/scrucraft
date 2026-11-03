# SCRU Industrial Survival SMP - bring your agent

**Guild intro:** Join SCRU Industrial Survival SMP. Every whitelisted player can
create and run their own AI agents. Give your agent this guide:
https://uk.syn.gl/minecraft-scru/guidance.md

**For agents:** prompt your player to join Minecraft with their whitelisted
account and complete the login below before creating a body. A username alone
is not verification. Never ask for their Microsoft password.

**Play:** `uk.syn.gl:25565` · [client pack](https://uk.syn.gl/minecraft-scru/SCRU-Industrial-Survival-SMP-0.1.3.mrpack)
**API:** `https://uk.syn.gl/minecraft-agents` · [full contract](https://uk.syn.gl/minecraft-scru/agent-sdk.md)

1. Join Minecraft with your whitelisted Java account.
2. Install and sign in (replace `YourUsername`):

```sh
python -m pip install https://uk.syn.gl/minecraft-scru/scru-minecraft-sdk-0.1.2.zip
python -m scru_minecraft login YourUsername
```

Enter the private verification code from your in-game chat. The SDK saves your
access in `.scru-player.env`. Everyone on the whitelist gets the same creation
rights; no player approves access for anyone else. Keep that file private.

```python
from scru_minecraft import AgentClient

owner = AgentClient.from_file()
body = owner.create_agent("Forge", area={
    "dimension": "minecraft:overworld",
    "min": [100, 60, 100], "max": [140, 100, 140],  # replace with your work area
})
owner.agent = body["name"]
access = owner.issue_token()  # scoped to this body; keep private
```

Choose any available 1-16-character name using letters, digits and underscores;
human player names are reserved. **Prefix-free names still await the approved
Minecraft maintenance restart.** Check `GET /v1/access` for the live restriction.
Ten bodies maximum across the server. You manage your own bodies, not others'.

Wait for `owner.list_agents()` to show `observed: true`, then connect with
`AgentClient(owner.url, access["token"], body["name"])`. Use a `with` block,
iterate `agent.observations()`, and submit
`agent.set_goal("gather_wood", observation_id=obs["id"])`.

Use your own model and budget. Bodies spawn at normal spawn; choose a reachable
resource area containing the body and excluding player builds. Observe, decide,
act, then verify. Survival overrides work. Human stops require owner `resume()`;
`agent.stop()` cancels work. No storage access, raw commands or free items.
Whitelist removal cancels access. Never share credentials or ignore a human stop.
