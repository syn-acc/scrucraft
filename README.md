# SCRUCraft — Minecraft agent SDK

Connect your own AI agent to a real survival player in Minecraft. SCRUCraft
provides the Python SDK, authenticated gateway and native body controls; your
agent supplies the model, planning and memory.

## Architecture

```text
Your agent ↔ Python SDK ↔ Authenticated gateway ↔ Java adapter ↔ Minecraft
```

- **Agent + SDK:** plan tasks, send commands and consume observations/results.
- **Gateway:** verify players, enforce body ownership, manage control leases and
  stream commands and observations over WebSockets.
- **Java adapter:** execute survival actions and native navigation, preserve real
  inventory rules, and report outcomes from the game.

Task planning stays with the agent. Human stops take priority. An accepted command
is not evidence that a task succeeded.

## Roadmap to a Minecraft benchmark

1. **Reliable gameplay API.** Complete and validate movement, world interactions,
   crafting, containers, cancellation and recovery, including mod compatibility
   and native multi-body performance.
2. **Survival baseline.** Start from an empty inventory; measure shelter, food,
   tools, progression and deaths through repeatable end-to-end runs.
3. **Industrial pilot.** Build a powered Create mill, verify two production batches
   and deliver 32 newly produced bread. Expand toward logistics, unseen orders
   and recovery from controlled faults.
4. **Reproducible benchmark.** Freeze isolated world snapshots, pack/API versions,
   task rules and model budgets. Repeat across seeds and report completion,
   production, time, cost, interventions and recovery using independent evidence.

**Status:** experimental gameplay is available; full API acceptance and native
multi-body performance remain incomplete. Sustained industrial production and a
validated benchmark score have not yet been demonstrated.

[Player setup](sdk/README.md) ·
[API completion checklist](sdk/docs/api-completion-checklist.md) ·
[Realtime protocol](sdk/docs/realtime.md) ·
[Configuration and contributing](sdk/docs/configuration.md)
