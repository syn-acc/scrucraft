# Python SDK reference

Requires Python 3.10+. The live experimental release is 0.2.0.dev1; install the
`stream` extra for WebSockets. Account and lifecycle methods use HTTP. Use
`client.realtime()` for live body control; the older goal methods below describe
the retained HTTP client surface and are rejected by realtime bodies.

```python
from scru_minecraft import AgentClient, GatewayError
```

| Entry point | Behavior |
| --- | --- |
| `AgentClient(url, token, agent=None, timeout=8)` | Create a client; does not acquire control |
| `AgentClient.from_file(path=".scru-player.env", agent=None)` | Read the owner's private login file |
| `AgentClient.from_env(agent=None)` | Read `SCRU_AGENT_URL`, `SCRU_AGENT_TOKEN`, `SCRU_AGENT_ID` |
| `AgentClient.start_login(username, url=...)` | Start the private in-game challenge |
| `AgentClient.finish_login(request_id, code, url=...)` | Exchange the challenge for a private player token |
| `capabilities()` | GET `/v1/me`; not a body-specific primitive capability query |
| `list_agents()` | Return the visible body list, unwrapped from `agents` |
| `create_agent(name, job="engineer", area=None)` | Owner-only creation request; inspect readiness afterward |
| `issue_token()` | Owner-only rotation of the selected body's scoped token |
| `remove_agent()` | Owner-only removal request |
| `resume()` | Owner-only acknowledgment of a human stop; no lease acquisition |
| `observe()` | Get a filtered frame; may reuse its local cache for 1.05 seconds |
| `observations(interval=1.1)` | Yield changed frame IDs, polling no faster than 1.1 seconds |
| `connect()` | Acquire a lease and start background renewal; returns self |
| `set_goal(goal, observation_id, ttl_seconds=30, request_id=None)` | Submit a goal; suppress recent identical desired goals |
| `say(text, request_id=None)` | Queue sparse outgoing chat under the current lease |
| `stop()` | Clear desired work and DELETE `/v1/goal`; retain lease |
| `close()` | Stop renewal, release lease and clear local desired work |

The default URL is `https://uk.syn.gl/minecraft-agents`. Set `client.agent` to
select a body before control, or pass its name when constructing the client. Use
one client per controlled body; do not switch bodies while holding a lease.
For local test servers only, the constructor supports `allow_local_http=True`
with `localhost` or `127.0.0.1`; real credentials belong only on trusted HTTPS.

A `with AgentClient(...) as agent:` block acquires control on entry and releases
it on exit. Use an ordinary client without a `with` block for read-only observation.
The SDK refreshes the lease every eight seconds and refreshes a desired goal from
recent observations. The default 30-second goal TTL suits that cadence; short
custom TTLs can expire between background refreshes. A lost lease is not
automatically reacquired. Network/renewal errors may end the observation loop;
applications should also impose their own deadlines and completion conditions.

`GatewayError` has `status`, `code`, and `retry_after` (a header string or null).
Transport failures may also raise `OSError`/URL errors. Handle both, preserve
uncertain outcomes, and never log credentials. Failed mutations are not
automatically retried. Goal/chat retry IDs must retain the exact original payload.

## Development-only methods

| Method | Behavior |
| --- | --- |
| `action(op, target=None, ttl_seconds=30, request_id=None)` | Fetch frame/epoch and submit an advertised primitive |
| `move_to(x, y, z, **kwargs)` | Submit movement; return acceptance receipt |
| `look_at(x, y, z, **kwargs)` | Submit orientation; return acceptance receipt |
| `action_results()` | Return the latest bounded body results |

Read the [direct-action contract](direct-actions.md) before using these methods.
There is no synchronous `move_to` completion guarantee, automatic primitive
refresh or general inventory/container interface in this milestone.
Use `with client.realtime() as body` for the live [bidirectional WebSocket API](realtime.md).
