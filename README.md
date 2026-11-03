# SCRUCraft — Minecraft agent SDK

Public development repository: https://github.com/syn-acc/scrucraft. The first native-navigation and direct-control milestone is deployed as an experimental release; remaining primitives and terrain validation are unfinished.

Read [the migration status](sdk/MIGRATION.md) before running this candidate. Existing player setup is documented in [sdk/README.md](sdk/README.md).

Work through the [API completion checklist](sdk/docs/api-completion-checklist.md). See [configuration and secret handling](sdk/docs/configuration.md) before contributing.

Python checks: `python -m pip install -r agent-gateway/requirements.txt` then `python -m unittest discover -s tests -v`.

Java: JDK 21, Gradle 9.2.1, NeoForge 21.1.265. The build expects the pinned LuckPerms compile dependency in `../../artifacts` relative to agent-mod; no mod binaries or credentials are included.
