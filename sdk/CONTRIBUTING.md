# Contributing

Development is public at https://github.com/syn-acc/scrucraft. Repository access
does not grant access to the Minecraft host or permission to use other players'
bodies. No open-source licence is granted by this documentation.

Use Python 3.10+ and install with `python -m pip install '.[stream]'`. The
WebSocket client uses the pinned stream dependency. Keep examples finite, make world-changing steps
explicit, and leave owner credentials out of model context.

For a protocol change, update the prose contract, OpenAPI, Python reference and
release status together. Label features as development until verified with the
actual gateway and loaded Java adapter. Preserve older clients deliberately;
do not infer feature availability from package versions alone.

Before review, check Markdown links, compile examples without executing live
operations, and run relevant SDK/gateway tests in the integration workspace.
Network examples must not enroll real users, create bodies, alter world state or
send chat as a side effect of a documentation check. Gateway tests use isolated
temporary state and fake provisioning; they belong in the integration workspace.

Pull requests should describe the user-visible behavior, compatibility changes,
validation and remaining limitations. Never include credentials, `.env` files,
game accounts, player data, worlds, operational backups or provider secrets.

Java changes and live deployment are handled in the integration workspace under
its maintenance rules. Publishing this repository does not deploy its code.

## Reproduce the source build

From the repository root, use Python 3.10+, JDK 21 and Gradle 9.2.1:

```sh
python -m pip install -r agent-gateway/requirements.txt
python -m unittest discover -s tests -q
python agent-mod/prepare_dependencies.py
gradle -p agent-mod build
```

The dependency preparation downloads the public LuckPerms version pinned in
`pack.lock.json`, verifies its SHA-512 and writes only into ignored
`agent-mod/build/dependencies/`. For an offline build, use
`python agent-mod/prepare_dependencies.py --source /path/to/LuckPerms-NeoForge-5.4.150.jar`
and supply the usual prepopulated Gradle/NeoForge cache. No production host paths
or credentials are needed. Running `gradle clean` removes the staged dependency;
prepare it again before building. Native acceptance additionally needs the
locked public server mods and a disposable isolated world; see
[verification](docs/verification.md).
