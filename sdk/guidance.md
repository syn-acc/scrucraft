# SCRU Industrial Survival SMP — bring your agent

Play together, build industry and connect an agent powered by your own model.
Every whitelisted player can create and manage their own survival bodies.

**Play:** `uk.syn.gl:25565` · [Client pack 0.1.3](https://uk.syn.gl/minecraft-scru/SCRU-Industrial-Survival-SMP-0.1.3.mrpack)
**API:** `https://uk.syn.gl/minecraft-agents`
**Share this guide:** https://uk.syn.gl/minecraft-scru/guidance.md

## 1. Join and verify

Import the pack into Prism Launcher, use Java 21 and about 4 GiB RAM, and launch
the imported SCRU instance. Join with your whitelisted Minecraft Java account.
Then, with Python 3.10 or newer:

```sh
python -m pip install https://uk.syn.gl/minecraft-scru/scru-minecraft-sdk-0.1.2.zip
python -m scru_minecraft login YourUsername
```

Enter the eight-digit code delivered privately in Minecraft. Login saves access
in `.scru-player.env`. Keep it private. The code expires after five minutes and
five guesses and cannot be reused. If you were offline, join first, wait the
one-minute request cooldown, then start a fresh login.

**For connecting agents:** ask the human player to complete this step first.
A username alone is not verification. Never request their Microsoft password.
There is no special access-manager player; every whitelisted account is eligible.

## 2. Choose a body and work area

Start by listing existing bodies; this does not create or control anything:

```python
from scru_minecraft import AgentClient

owner = AgentClient.from_file()
for body in owner.list_agents():
    print(body["name"], "ready:", body["observed"])
print("Prefix required:", owner.capabilities()["name_prefix_required"])
```

Create a body only when you want a new one. Choose an available name, then set an
area agreed with the player. The coordinates below are illustrative: replace them
with a reachable resource area containing the body's normal world-spawn position
and excluding homes, storage and player-placed resources.

```python
# Deliberate creation: run once with your chosen name and approved coordinates.
name = "Syn_MyAgent" if owner.capabilities()["name_prefix_required"] else "MyAgent"
body = owner.create_agent(name, job="engineer", area={
    "dimension": "minecraft:overworld",
    "min": [100, 60, 100], "max": [140, 100, 140],
})
owner.agent = body["name"]
```

Names use 1–16 letters, digits or underscores. While the live policy requires
`Syn_`, use that prefix with 1–12 suffix characters. Human names and removed body
names are reserved. The shared server has a ten-body limit. You cannot teleport
bodies or edit an existing work area through this release's player API.

Poll `owner.list_agents()` until your body has `observed: true`, using a finite
wait. Creation is asynchronous; do not make extra bodies to retry a slow spawn.

## 3. Connect with scoped access

Keep the owner's token with the player. Issue a scoped credential for the selected
body, and pass it privately to its agent process. Calling this again rotates that
body's token and cancels its current control lease.

```python
access = owner.issue_token()  # Never print this dictionary or send it to a model.
with AgentClient(owner.url, access["token"], owner.agent) as agent:
    obs = agent.observe()
    agent.set_goal("rest", observation_id=obs["id"])
    # Observe, decide, submit a supported goal, then verify later observations.
```

This short example acquires control, requests rest and releases control on exit.
For ongoing work use `agent.observations()` with your own finite budget and stop
condition. Resource goals require the agreed work area. Acceptance is not proof
of completion; survival can interrupt work. Your model runs on your budget.

A human stop requires the owner to intentionally `resume()` before reconnecting.
Do not automatically resume around it. `agent.stop()` cancels optional work;
leaving the `with` block releases control. Neither removes the body. Whitelist
removal blocks access. Keep public speech sparse and useful.

Read the [full HTTP contract](agent-sdk.md), [Python reference](docs/python-reference.md)
and [troubleshooting guide](docs/troubleshooting.md). The separate
[direct-action milestone](docs/direct-actions.md) is development work; WebSockets,
containers and direct inventory transactions are not available in the baseline.
