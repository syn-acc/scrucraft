# Instructions for a connecting agent

First ask your player to join Minecraft and complete the
[login](../guidance.md). Do not impersonate a player by supplying only a username.
Keep player credentials out of model context; use a scoped body token in the
agent process whenever possible.

1. Read live capabilities. Confirm that the player wants a new body or select one
   they already own. Listing and observing do not require a control lease.
2. Before creating a resource-working body, have the player choose a reachable
   work area containing its spawn position and resources, excluding builds and
   storage. There is no teleport API or player API to edit an existing area.
3. Create once, preserving the chosen name, job and area for any retry. Bodies
   appear asynchronously. Poll until `observed` is true with a finite timeout.
   A returned creation record is not proof that the body exists in the world.
4. Acquire one lease for one agent process. Observe, decide, submit, then verify
   what happened in subsequent observations or authoritative action results.
5. Use finite primitive TTLs. `client.realtime()` renews the control lease but
   never renews or replays primitive actions; it does not bound model spending.
   Set your own model budget, iteration limit and stop condition.
6. Treat human stops, lost control and revoked access as reasons to stop the
   process and inform the owner. Do not continuously reacquire or automatically
   call owner `resume()`.
7. Release control in cleanup. If the connection is unavailable, lease/grant expiry
   bounds optional work. Report uncertain outcomes as uncertain.

Use read-only observation or `look_at` when first connecting. Resource work can
alter the shared world. Gathering does not establish a productive factory,
self-sufficient farm or completed building. Job labels such as `engineer` are
not a list of verified abilities.

The live WebSocket API puts task planning in your agent and executes supported
primitives in Java. Goal control is disabled on realtime bodies. Subscribe to
observations and match result ID and body epoch to verify execution.

Incoming/outgoing chat primitives are not exposed on realtime bodies yet.

See the [Python reference](python-reference.md), [HTTP contract](../agent-sdk.md)
and [read-only example](../examples/observe.py).
