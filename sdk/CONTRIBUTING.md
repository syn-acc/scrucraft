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
