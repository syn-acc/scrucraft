# Access and privacy

Every whitelisted Minecraft account has the same enrollment rights. ClosedDoor,
like every other member, manages only their own bodies. There is no designated
player who hands out everyone else's access.

## Verify your Minecraft account

Join the online-mode server, then run `python -m scru_minecraft login YourUsername`.
Enter the eight-digit code privately delivered to that account in Minecraft.
This proves access through the authenticated game session. It is not a Microsoft
OAuth webpage, and the SDK does not ask for a Microsoft password or access token.
Ignore codes you did not request.

Codes expire after five minutes, allow five guesses, are single-use, and disappear
if the gateway restarts. Login starts are limited to one per account per minute
and globally one per half-second. Codes are not queued for offline delivery.
The server rechecks whitelist membership and UUID when completing enrollment,
on authenticated requests, and while forwarding control. Reassigning a username
does not transfer another UUID's bodies.

## Two kinds of token

| Token | Scope | Keep it |
| --- | --- | --- |
| Player token (`role: player`) | Create bodies and manage/control that player's bodies | In the human owner's private login file |
| Body token (`role: agent`) | Observe and control one named body | In that agent process's private environment or secret storage |

Login writes `.scru-player.env` without displaying the token. Use
`AgentClient.from_file()` to read it; do not execute it as shell code. The login
command refuses to overwrite an existing file. Protect it with your operating
system's file permissions, especially on shared Windows accounts or synced folders.

Issuing a new body token revokes previous body tokens and cancels the current
lease. The token is returned once. Do not print it, paste it into chat or model
prompts, commit it, attach it to a bug report, or embed it in a URL. These tokens
do not grant OP, shell access, arbitrary console commands or other players' bodies.

For an exposed body token, the owner can rotate it. For an exposed player token,
contact the server host to revoke that owner's tokens; logging in again does not
itself revoke every older player token. Removing someone from the whitelist blocks
their requests and active optional work. Re-enrollment requires whitelist access.

## What an agent can see

The current gateway exports a filtered snapshot of its own body: survival state,
inventory, nearby terrain/entities and progression fields when available. It
omits player lists, other players' inventories, private/admin state and chat.
Chat support is outgoing only. Do not infer that the current observation API is
a full world snapshot or public-chat subscription.

Your agent decides what observations to send to your model provider. You choose
that provider and pay its costs. Server inference is not enabled for these
external bodies. The gateway stores ownership, token hashes and human-stop state;
leases and login challenges are temporary. No retention guarantee is made for
your own process logs or your provider's records.

## Human control

An addressed human stop is persistent. The owner must deliberately call
`resume()` before control can be reacquired; agents must not automatically resume
to get around a stop. `stop()` cancels optional work while retaining the lease;
`close()` releases control. Neither removes the body. Survival responses and
ordinary game physics can continue after optional work ends.
