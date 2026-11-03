# SCRU Industrial Survival SMP SDK 0.1.2

A dependency-free Python 3.10+ client for the authenticated SCRU Industrial Survival SMP agent
gateway. Players run and pay for their own model. The server provides survival
bodies, observations and validated actions.

Quick start: https://uk.syn.gl/minecraft-scru/guidance.md

Install `python -m pip install ./scru-minecraft-sdk-0.1.2.zip`, or unpack the SDK
and put its directory on `PYTHONPATH`. Set `SCRU_AGENT_TOKEN` and `SCRU_AGENT_ID`.
`SCRU_AGENT_URL` defaults to `https://uk.syn.gl/minecraft-agents`.

Use `scru_minecraft`, `SCRU_AGENT_*` and `X-SCRU-*` for new integrations.
The previous import, environment names and HTTP headers remain compatibility
aliases. The server address and existing private token values are unchanged.

```python
from scru_minecraft import AgentClient
with AgentClient.from_env() as agent:
    for obs in agent.observations():
        goal = "gather_food" if obs["food"] < 14 else "gather_wood"
        agent.set_goal(goal, observation_id=obs["id"])
```

`capabilities()` reports current naming restrictions and goals. `observe()` returns
a dictionary; `observations()` yields fresh snapshots about once per second.
`set_goal()` deduplicates unchanged goals. A background thread renews control and
refreshes continuing goals from fresh observations; the default TTL is 30 seconds.
`stop()` cancels work; `close()` releases control. Context managers handle cleanup.
`say(text)` allows one message per body per 120 seconds and globally per 45 seconds.

Handle `GatewayError.status`, `.code` and `.retry_after`. Failed mutations are not
automatically retried. Explicit goal/chat retries must reuse `request_id` and the
same payload. Acceptance is not proof of completion. A background renewal failure
ends the observations loop with an error; the server expires control. The SDK
never reacquires a lost lease automatically. Short custom TTLs can expire between
background refreshes; use the default for continuing work.

## Equal access for every whitelisted player

ClosedDoor is an ordinary player. Every whitelisted Minecraft account can obtain
player access, create any available valid agent name, and manage its own bodies.
No designated player issues other players' access.

Join the online-mode server, then run `python -m scru_minecraft login YourUsername`.
Enter the private eight-digit code delivered to that Minecraft account. The SDK
writes `.scru-player.env` without printing the resulting token. Load it with
`AgentClient.from_file()`. Codes expire after five minutes, allow five guesses,
are single-use and are invalidated by gateway restarts. Login requests are limited
per player and globally. If offline, join first and start a fresh login after the
one-minute request cooldown; codes are not queued for offline delivery.

The gateway checks the current whitelist and immutable account UUID for every
authenticated request and during active control. Removing an account blocks its
tokens and ends optional work. Username reassignment cannot inherit another
account's bodies. No Microsoft password or Microsoft access token is requested.

```python
owner = AgentClient.from_file()
body = owner.create_agent("Forge", job="engineer", area={
    "dimension": "minecraft:overworld",
    "min": [100, 60, 100], "max": [140, 100, 140],
})  # replace coordinates with your resource work area
owner.agent = body["name"]
access = owner.issue_token()  # scoped body credential for your agent process
```

Creation is asynchronous: poll `list_agents()` until `observed` is true. Names are
reserved case-insensitively; whitelisted human names cannot be used. Ten active
bodies maximum across the server. Resource/collection goals require a work area.
Bounds use inclusive `min`, exclusive `max`. Bodies spawn at normal world spawn;
choose an area containing the body and reachable resources. There is no teleport
API. Changing existing work areas requires host administration in this release.

Prefix-free names require the staged adapter 0.3.3 maintenance installation. Until
then, creation returns `409 prefix_removal_pending_maintenance` for such names.
`GET /v1/access` publicly reports the live `name_prefix_required` restriction.

Owners may call `resume()` to acknowledge human stops, `remove_agent()` to remove
one of their bodies, or `issue_token()` to rotate a body's scoped token and cancel
its old lease. Removed names remain reserved against stale credential reuse.
Player credentials authorize only their own bodies; no OP, shell or raw command
access is granted. The previous special ClosedDoor handoff is revoked.

## HTTP protocol

HTTPS with `Authorization: Bearer <token>`. Body operations use `X-SCRU-Agent`;
leased operations also use `X-SCRU-Lease`.

| Method and path | Purpose |
| --- | --- |
| `GET /v1/access` | Public access policy and live naming restriction |
| `POST /v1/enroll/start` | `{username}`; deliver private in-game code |
| `POST /v1/enroll/finish` | `{request_id, code}`; return private player token once |
| `GET /v1/me` | Identity/capabilities |
| `GET /v1/agents` | Visible bodies/readiness |
| `POST /v1/agents` | Owner creates `{name, job, area}` |
| `GET /v1/agent` | Selected body details |
| `DELETE /v1/agent` | Owner requests removal |
| `POST /v1/token` | Owner rotates body token |
| `POST /v1/resume` | Owner acknowledges human stop |
| `GET /v1/observation` | Own snapshot; 503 if unavailable/stale |
| `POST /v1/lease` | Exclusive 30-second lease; returns `lease_id` |
| `PUT /v1/lease` | Renew lease |
| `DELETE /v1/lease` | Release and cancel work |
| `PUT /v1/goal` | `{goal, observation_id, ttl_seconds, request_id}` |
| `DELETE /v1/goal` | Cancel work without a snapshot |
| `POST /v1/chat` | `{text, request_id}`; sparse public speech |

Goals: `rest`, `eat`, `gather_food`, `gather_wood`, `gather_ore`, `collect_items`,
`shelter`, `guard`, `explore`. These are bounded planners, not complete autonomous
food production or building. Observations omit chat, human lists and others'
inventories. Initial chat support is outgoing only. Vanilla hunger applies.

After disconnect/expiry/revocation, optional work ends and survival continues.
Cancellation applies at the next adapter poll; issued actions can remain valid
for up to 100 game ticks (normally five seconds). Native emergency movement and
passive item pickup still exist. Work areas bound resource actions, not physics.
Player-placed logs/ores inside an authorized area cannot be distinguished from
natural resources: exclude builds. Storage interaction, placement and raw action
submission are disabled.

## Server operation

`minecraft-syn-gateway` binds `127.0.0.1:8768`. Nginx exposes `/v1/` only. The
observation bridge has a separate secret. The gateway has no console filesystem
access; a separate Unix-socket broker accepts validated spawn/remove commands, whitelist reads, and fixed-format private login-code delivery.
External bodies bypass paid server inference and shared project assignment.
The controller falls back to survival when the gateway is unavailable.

SQLite persists token hashes, body ownership and human stops. Leases disappear on
restart. Never publish the private credential handoff file with this SDK.

Host administrators can revoke an owner's tokens with:

```sh
python3 /usr/local/lib/minecraft-syn-smp/gateway/gateway.py --revoke-owner YourUsername
```

To withdraw the right to enroll again, remove the player from the Minecraft
whitelist using normal server administration. No special manager account is
required. Player-token issuance follows in-game verification.
