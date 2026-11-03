# SCRU agent control — candidate only

**Area policy (development candidate):** No location or coordinate selection is
required. Omitted/null `area` means unrestricted survival play. Area checks below
apply only to optional owner-selected bounds. Normal survival, account ownership
and human-stop controls remain. This policy change is not yet deployed.

**0.3.0.dev1 / adapter 0.5.0-dev1 is not deployed.** For the shared server use the
[live guide](guidance.md). Against an authorized candidate server, install this
checkout with `python -m pip install "./sdk[stream]"` and use a private player login
file for that endpoint. Every whitelisted player controls their own named bodies.

```python
from scru_minecraft import AgentClient

client = AgentClient.from_file(agent="MyAgent")
client.prepare(required=["move_to", "look_at", "dig"])
with client.realtime() as body:
    x, y, z = body.observe()["position"]
    body.look_at(x + 2, y + 1, z).result()
```

To create a body, call `prepare(create=True)`. No location or area selection is required. Read `raw_capabilities`, inventory slots and recipe queries. Build task
logic from direct primitives; await action results, not acceptance. Use
`async_realtime()` for async control. `reconnect()` reconciles uncertain outcomes
without replay; never retry uncertain item mutations blindly. Respect human stop;
only deliberate owner `resume()` permits new control. Keep credentials outside
prompts and Git. The [API contract](docs/direct-actions.md) defines limits and
unsupported interactions; the [completion checklist](docs/api-completion-checklist.md)
defines release readiness.
