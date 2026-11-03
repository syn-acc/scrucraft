# Python SDK reference — candidate 0.3.0.dev1


**Area policy (experimental release):** No location or coordinate selection is
required. Omitted/null `area` means unrestricted survival play. Area checks below
apply only to optional owner-selected bounds. Normal survival, account ownership
and human-stop controls remain. This policy is live in the controlled experimental release.


This reference describes the experimental gameplay SDK. Install the `stream` extra; Python 3.10+ is required.



First run `python -m scru_minecraft login YourUsername` while joined to Minecraft.

The helper prompts for the private in-game code and saves `.scru-player.env`

without printing the token. This proves the authenticated game account, not a

Microsoft OAuth webpage. Keep the file private. Actual participating-player

onboarding remains a release verification gate.



```python

from scru_minecraft import AgentClient



client = AgentClient.from_file(agent="MyAgent")

client.prepare(create=True, area={"dimension":"minecraft:overworld",

    "min":[0,60,0], "max":[16,80,16]}, required=["move_to", "dig"])

with client.realtime() as body:

    movement = body.move_to(3.5,64,3.5)

    body.look_at(5,65,5).result()  # Looking does not cancel navigation.

    movement.result(timeout=30)

    body.chat("Ready.").result()

```



No area selection is required. Omit `create=True` for an existing owned

body. `prepare(name=None, create=False, area=None, job="engineer", timeout=30,

required=())` selects/creates, then waits for readiness with a finite timeout.

It never resumes a human stop. `await_ready(timeout=30, required=())` is available

separately. Missing capabilities raise an actionable `GatewayError`.



## Primitive methods and handles



HTTP `AgentClient` and WSS `RealtimeClient` share the methods below. Prefer WSS for

control; HTTP observation pacing is deliberately slower. Every action returns an

`ActionHandle`, a dict-compatible acceptance receipt:



- `handle.id` or `handle["id"]` identifies the action.

- `handle.wait(timeout=30)` returns the terminal outcome, including failure.

- `handle.result(timeout=30)` returns done or raises `ActionFailed` with `.outcome`.

- `handle.cancel()` submits a separate cancellation action and returns its handle.



| Method | Arguments |

| --- | --- |

| `move_to`, `look_at`, `dig`, `open_container` | `x,y,z` |

| `place` | `x,y,z,face`, optional `hand="main"|"off"` |

| `use_item`, `release_use`, `swap_hands` | optional `hand` only for use_item |

| `use_on` | block `target=[x,y,z],face="up"` or `entity_id=n`, optional hand |

| `attack`, `select_slot` | `entity_id` / hotbar `slot` |

| `drop` | inventory `slot,count` |

| `jump`, `sneak`, `sprint` | `enabled=True` or False to release |

| `chat` | Nonblank `text`, at most220 UTF-16 code units; no slash commands, control characters, DEL or invalid surrogates |

| `move_item` | `from_slot,to_slot,count`, optional explicit `session_id,revision` |

| `close_container` | optional explicit `session_id,revision` |

| `craft` | `recipe_id,count=1`, optional target table coordinates |

| `query_blocks` | `target,radius=1` or `positions=[...]` |

| `query_recipes` | `offset=0,limit=32`, bounded recipe summaries |
| `query_inventory` | `slot`, optional `inventory`, byte `offset,limit,stack_revision`, container session/revision; returns page handle |
| `inventory_slot` | `slot`, optional `inventory,session_id,revision,timeout=30,max_bytes=4194304`; returns full stack with decoded components |
| `query_recipe` | `recipe_id`, byte `offset,limit,recipe_revision`; returns page handle |
| `recipe` | `recipe_id,timeout=30,max_bytes=4194304`; returns full descriptor with ingredients/components |

| `cancel` | `action_id` |

| `action` | `op`, common `ttl_seconds=30,request_id=None` and documented wire fields |



`move_item` slot references are dictionaries such as

`{"inventory":"player","slot":0}` and `{"inventory":"container","slot":3}`.

Full `inventory_slot` and `recipe` reads hide byte pagination, verify SHA-256,
revision, epoch and offsets, and fail if data changes or bounds are exceeded.
Use them when fast snapshots/summaries flag truncated metadata. They are reads
returning decoded dictionaries, not mutation handles; async clients await them.
Await `open_container().result()` first; omitted session/revision use the current

observation. Stale revisions fail explicitly. See the [wire contract](direct-actions.md)

for limits, supported menus/recipes, placement coordinates and interruption semantics.



`stop()` immediately clears all channels while retaining the lease; it returns a

gateway stop receipt. Use `action("stop").result()` when a native completion

receipt is needed. `observe()` returns latest state. `wait_action(id,timeout=30)`

and `action_results(action_id=None)` allow reconciliation independently of handles.



## Async and subscriptions



```python

async with client.async_realtime() as body:

    movement = await body.move_to(3.5,64,3.5)

    look = await body.look_at(5,65,5)

    await look.result()

    await movement.result()

    async for event in body.observations():

        print(event.sequence, event.gap, event.observation["position"])

        break

```



Async calls run blocking transport operations in worker threads. Both clients use

one background reader and lease renewer; callers do not manage sockets.

`observations()` yields typed `SnapshotEvent(sequence,observation,resync,gap)`;

slow consumers get the latest snapshot and gap marker. `chat_events()` yields

`PublicChatEvent(id,speaker,text,at,gap)` with deduplicated public message IDs.

Neither subscription promises replay of every intermediate tick/chat message.



`reconnect(attempts=3,initial_delay=.1)` is an explicit bounded recovery operation:

it clears stale state, opens a new stream/lease, reconciles submitted IDs into

`.reconciled`, and never replays commands. Authentication/membership/human-stop

failures propagate immediately. Inspect world/inventory for `unknown` or

`outcome_unknown_timeout`; do not turn recovery into an automatic mutation retry.

`diagnostics()` returns connection state, latest observation age, pending requests,

sequence and last request timing. `GatewayError` exposes status/code/retry_after;

`ActionFailed` exposes the native outcome; timeouts and transport errors remain visible.



## Account and lifecycle



`from_env`, `from_file`, `start_login`, `finish_login`, `list_agents`,

`create_agent`, `issue_token`, `remove_agent` and `resume` retain their existing

HTTP behavior. Every whitelisted player may create any available valid name and

manage their own bodies. `capabilities()` is account policy/limits; inspect

`observe()["raw_capabilities"]` or `await_ready(required=...)` for the selected body.

The default endpoint is `https://uk.syn.gl/minecraft-agents`; HTTPS is mandatory

except explicitly enabled localhost test HTTP. Use one client per body and never

change `client.agent` while controlling another body. Context managers release

leases; private access tokens must not be logged or embedded in prompts.



Legacy `set_goal` and `say` remain solely for old non-realtime deployments; the

current direct executor rejects them. Use primitives and `chat` in new code.
