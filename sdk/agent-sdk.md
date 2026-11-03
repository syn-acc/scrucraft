# SCRU player-agent HTTP contract

**Area policy (development candidate):** No location or coordinate selection is
required. Omitted/null `area` means unrestricted survival play. Area checks below
apply only to optional owner-selected bounds. Normal survival, account ownership
and human-stop controls remain. This policy change is not yet deployed.

**Live:** gateway/SDK 0.2.0.dev1 with [WebSocket body control](docs/realtime.md).
The identity/lifecycle contract below remains valid. Goal and chat execution
describe the historical 0.1.2 flow; realtime bodies reject goals and do not execute
queued goal-controller chat. **Direct actions:**
[candidate protocol 2 direct actions](docs/direct-actions.md), explicitly separate
from the [live WebSocket contract](docs/realtime.md). Reviewed 2026-11-03 against gateway
source and deployment records; this review did not complete a real player login.

Base URL: `https://uk.syn.gl/minecraft-agents`. Paths below are relative to it.
[Release status](docs/release-status.md) distinguishes
published behavior from unfinished work.

## Transport and identity

Use HTTPS and JSON objects. Send `Accept: application/json` and, when sending a
body, `Content-Type: application/json`. Authenticated calls use
`Authorization: Bearer <private-token>`. Do not put credentials in query strings.
The Python SDK refuses redirects and remote plaintext HTTP.

Body operations require `X-SCRU-Agent: <body-name>`. Leased operations also require
`X-SCRU-Lease: <lease-id>`. A lease belongs to the exact credential that acquired
it, not merely to the same owner. Legacy `X-Syn-Agent` and `X-Syn-Lease` are accepted;
conflicting current/legacy values return `400 conflicting_headers`.

Player tokens manage the verified player's own bodies; body tokens operate only
their selected body. Neither grants other players' data or server administration.
Whitelist membership and the account UUID are rechecked on authenticated calls
and while control is active. `GET /v1/agents` is owner-scoped, not a server roster.

Successful handled requests currently return HTTP **200**, including creation and
deletion requests. Failure bodies are `{"error":"machine_readable_code"}`.
Rate errors include `Retry-After` as a whole number of seconds. Intermediaries may
return non-JSON errors; clients must handle them without exposing credentials.
Timestamps named `expires_at` and `captured_at` are Unix seconds. Observation IDs,
lease IDs and login request IDs are opaque strings, not sequence numbers.

## Endpoint map

`Public` requires no token. `Owner` means a player token. `Body` means either the
owner token or that body's token, with `X-SCRU-Agent`. `Lease` adds the lease header.

| Method | Path | Access | Request / result |
| --- | --- | --- | --- |
| GET | `/v1/access` | Public | Registration policy, naming restriction and capacity |
| POST | `/v1/enroll/start` | Public | `{username}` → `{request_id, expires_at, message}` |
| POST | `/v1/enroll/finish` | Public | `{request_id, code}` → `{owner, role, token}` |
| GET | `/v1/me` | Token | Identity, goals, timing and capabilities |
| GET | `/v1/agents` | Token | `{agents: [Body, ...]}` |
| POST | `/v1/agents` | Owner | `{name, job?, area?}` → Body, possibly `status: spawn_requested` |
| GET | `/v1/agent` | Body | Body |
| DELETE | `/v1/agent` | Owner + Body | `{status: removal_requested, agent}` |
| POST | `/v1/token` | Owner + Body | `{}` → `{agent, token}` |
| POST | `/v1/resume` | Owner + Body | `{}` → `{status: resumed, agent}` |
| GET | `/v1/observation` | Body | Fresh filtered observation |
| POST | `/v1/lease` | Body | `{}` → `{lease_id, expires_at}` |
| PUT | `/v1/lease` | Lease | `{}` → `{lease_id, expires_at}` |
| DELETE | `/v1/lease` | Lease | `{status: stopped, agent}` |
| PUT | `/v1/goal` | Lease | `{goal, observation_id, ttl_seconds?, request_id}` → goal receipt |
| DELETE | `/v1/goal` | Lease | `{status: stopped, agent}` |
| POST | `/v1/chat` | Lease | `{text, request_id}` → `{status: queued, request_id}` |

Internal observation ingestion and provisioning interfaces are not part of this
client contract and are not authorized by player/body tokens.

## Enrollment and credentials

`username` matches `[A-Za-z0-9_]{1,16}` and must be whitelisted. Join Minecraft
before starting login; the private eight-digit code is delivered to that game's
authenticated account, not to this HTTP response. Submit `code` as a **string**
to preserve leading zeroes. Challenges expire in 300 seconds, after five guesses,
after successful use, or on gateway restart. Starting a login is limited to once
per account per 60 seconds and globally once per 0.5 seconds.

Finishing login returns a player token once. A successful exchange cannot be
replayed to recover a lost response. Keep the result private; if the response is
lost, start a fresh login after the cooldown. Logging in again does not rotate
all existing player tokens.

`/v1/access` returns `version`, `registration: whitelist_in_game_code`,
`role: player`, `name_prefix_required`, `max_agents: 10`, and
`agent_ownership: creating_player`. `/v1/me` adds `owner`, `role`, `agent` (null for
a player token), `goals`, `lease_seconds: 30`, `observation_max_age_seconds: 5`,
`chat: outgoing_only`, and `model_billing: bring_your_own`.

## Bodies and work areas

Body records have `name`, `owner`, `job`, `area` (object or null), `suspended`,
`removed`, and `observed`. Development records may also have `raw_capabilities`.
`observed` means a frame no older than five seconds was available when described;
it does not guarantee the next request will have a fresh frame.

Names are 1–16 ASCII letters, digits or underscores, reserved case-insensitively.
Whitelisted human names and host-reserved names are unavailable. While
`name_prefix_required` is true the name must match `Syn_[A-Za-z0-9_]{1,12}`.
There are at most ten nonremoved gateway bodies across the server. Creation
requests are limited to once per owner per five seconds for new bodies.

`job` defaults to `engineer`; values are `farmer`, `miner`, `builder`, `guard`,
`medic`, `engineer`. These are labels, not guarantees of specialist automation.
Creation is asynchronous. Poll your body's readiness with a finite deadline.
If the response is lost, inspect `/v1/agents`; retry only the same name, job and
area. Matching same-owner creation is reusable; it does not edit an existing body.
Removed names remain reserved to prevent stale credentials inheriting a new body.

An area is null or exactly:

```json
{"dimension":"minecraft:overworld","min":[100,60,100],"max":[140,100,140]}
```

These are illustrative coordinates, not an authorized location. `min` is inclusive
and `max` exclusive, on all three axes. Bounds must be integer triples, each
coordinate between -30000000 and 30000000, with `min[i] < max[i]`. Dimensions are
`minecraft:overworld`, `minecraft:the_nether`, or `minecraft:the_end`.

The updated candidate permits resource goals without an area.
Bodies spawn at normal world spawn; the API does not teleport them. Area changes require host
administration in this release. Areas constrain resource work, not all movement,
physics or passive item pickup. Player-placed resources are not distinguishable
from natural resources: exclude builds and storage.

Issuing `/v1/token` revokes older scoped tokens for that body and ends its lease.
It is not an idempotent token-recovery operation. `/v1/resume` clears a persistent
human stop but does not acquire control. Removal requests suspend the body,
end control, request removal and revoke scoped credentials; inspect subsequent
state instead of treating the response as proof of completed in-world removal.

## Observations

`/v1/observation` requires no lease. It returns a frame received within five
seconds or `503 agent_not_observed` / `503 observation_stale`. Its `captured_at`
is the gateway's receipt time, not a guarantee of subsecond world freshness.
Requests for the same token/body are limited to one per 0.9 seconds.

Always present in a gateway frame: `id`, `captured_at`, `inventory`. The response
adds `control: {suspended, goal, lease_active}`; `goal` is the active goal object
or null. `lease_active` does not mean the caller owns the lease.

Adapter-supplied fields are included when available: `agent`, `tick`, `dimension`,
`position`, `health`, `food`, `night`, `raining`, `sheltered`, `blocks`, `walkable`,
`entities`, `last_action`, `adapter_version`, `survival_profile`, `advancements`,
`deaths`. Treat nearby lists as bounded observations, not exhaustive world scans.
Inventory entries are adapter-defined and omit the obsolete hydration field;
do not assume a slot-level transaction API. Human lists, chat and other players'
inventories are not exported. Development fields are described separately.

Under `survival_profile: vanilla`, hunger and natural regeneration apply. There
are no actual LSO thirst or temperature measurements. Never infer task completion
from a goal receipt or from `last_action` alone.

## Leases, goals and cancellation

A body can have one **30-second** lease. Acquiring requires a fresh observation
and an unsuspended body. Renew before expiry; renewal resets the deadline to 30
seconds from now. Leases do not survive gateway restart. Body-token rotation,
human stop, revocation or whitelist removal ends optional control. Do not assume
a disconnect immediately stops the body.

For a goal, send a recently observed `observation_id` (no older than five seconds),
`request_id` matching `[A-Za-z0-9_-]{16,80}`, and `ttl_seconds` as an integer 1–30
(default 30). Supported goals are:

`rest`, `eat`, `gather_food`, `gather_wood`, `gather_ore`, `collect_items`, `shelter`,
`guard`, `explore`.

```json
{"goal":"rest","observation_id":"opaque-frame-id","ttl_seconds":30,"request_id":"example_request_0001"}
```

The receipt is `{status: accepted, goal, request_id, expires_at}`. It confirms
acceptance of bounded work, not completion. Goal submissions are limited to once
per body per second. A new accepted goal replaces the previous one.

`DELETE /v1/goal` cancels work and queued speech without a fresh observation and
keeps the lease. `DELETE /v1/lease` also releases control. Both still need valid
body/lease credentials. They do not clear a persistent human stop. Survival
responses continue after optional work expires or is cancelled. In the baseline,
already-issued adapter actions may remain valid for up to 100 game ticks (normally
five seconds); cancellation is not an instantaneous freeze.

## Chat

`text` is 1–256 characters, with no control characters below U+0020 or `§`, and
must not start with `/`. Speech is limited to once per body per 120 seconds and
globally once per 45 seconds. A queued speech command expires after 15 seconds.
`queued` is not proof of delivery. Use the same request-ID rules as goals.
This endpoint provides no incoming chat subscription or arbitrary game commands.

## Retries, errors and limits

Goal/chat receipts are deduplicated by **lease ID + endpoint + request ID** while
the lease is active. Retry with the identical complete payload. A changed payload
returns `409 request_id_reused`. Do not treat IDs as durable, cross-lease or
cross-restart exactly-once guarantees. After an ambiguous network failure, inspect
state before deciding whether to issue new work. Enrollment completion and token
rotation are not safely replayable response-recovery calls.

Authenticated requests are spaced at least 0.05 seconds per credential, in
addition to operation-specific limits. Failed requests may consume rate limits.
There are bounded enrollment/receipt capacities; saturation returns 503. The
Python SDK spaces calls and does not automatically retry failed mutations.

| Status | Typical codes | Client response |
| --- | --- | --- |
| 400 | `invalid_request`, `invalid_name`, `invalid_job`, `invalid_username`, `invalid_enrollment`, `agent_required`, `goal_not_supported`, `commands_not_supported`, `conflicting_headers` | Correct input; do not retry unchanged |
| 401 | `unauthorized`, `invalid_code` | Check private credentials or current challenge |
| 403 | `not_whitelisted`, `forbidden`, `player_access_required`, `work_area_required` | Resolve membership, scope or area with owner/host |
| 404 | `agent_not_found`, `not_found` | Check selection and supported endpoint |
| 409 | `lease_lost`, `lease_already_held`, `request_id_reused`, `observation_stale`, `agent_removed`, `name_reserved`, `agent_cap`, `prefix_removal_pending_maintenance` | Inspect state and resolve conflict |
| 410 | `enrollment_expired` | Start a new login after cooldown |
| 423 | `human_stop_requires_resume` | Stop; owner must intentionally resume |
| 429 | `rate_limited` | Respect `Retry-After` |
| 503 | `agent_not_observed`, `observation_stale`, `service_unavailable`, `enrollment_capacity`, `receipt_capacity`, broker failure codes | Back off; use a finite deadline and report persistent failure |

See [troubleshooting](docs/troubleshooting.md) for player-facing recovery steps.
