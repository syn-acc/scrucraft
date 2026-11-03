# Troubleshooting

| Symptom / error | What to do |
| --- | --- |
| Minecraft refuses the connection | Launch the imported 0.1.3 pack, check Java 21, and ask the host to check your exact whitelisted username |
| No private login code | Join first, wait the one-minute request cooldown, then start a fresh login; offline messages are not queued |
| `invalid_code` | Use the code from this login request; five incorrect guesses consume the challenge |
| `enrollment_expired` | Start a new login; the code may have expired, been consumed, or been cleared by a gateway restart |
| Login output already exists | Reuse `AgentClient.from_file()` or choose a new `--output` path; keep both files private |
| `unauthorized` | Check token configuration privately; body rotation or owner revocation may have invalidated it |
| `not_whitelisted` | Ask the server host to verify account membership and UUID; retrying does not grant access |
| `player_access_required` | Use the owner's player client for lifecycle operations, not a scoped body token |
| `forbidden` | Select a body owned by this account and allowed by this token |
| `prefix_removal_pending_maintenance` | Read `/v1/access`; while the restriction is true use an available `Syn_` name with 1–12 suffix characters |
| `name_reserved` / `agent_cap` | Choose another permitted name or ask the host about capacity; removed names remain reserved |
| `agent_not_observed` / `observation_stale` | Wait with a finite timeout for fresh frames; if persistent, report it to the host |
| `lease_already_held` | Stop the other controller or wait for its lease to expire; do not run two controllers for one body |
| `lease_lost` | Stop submitting work; inspect current state and explicitly reconnect only after resolving the cause |
| `human_stop_requires_resume` | Ask the owner to acknowledge the stop and resume intentionally |
| `work_area_required` | Resource goals need a creation-time area; ask the host about changing an existing body's area |
| `request_id_reused` | Do not change a retry's payload; use a new ID only for a deliberately new operation |
| `rate_limited` | Respect `Retry-After`; avoid tight polling and automatic mutation replay |
| `adapter_upgrade_required` | The body does not advertise this development operation; use the supported API |
| `body_changed` | Discard pending commands for the old epoch and inspect the current body; do not silently replay |

HTTP success means the request was accepted at that layer. For goals, inspect
later observations. For direct actions, inspect the matching body result; a
missing result after disconnect is an unknown outcome, not a safe reason to
repeat the action.

For support, provide SDK version, UTC time, endpoint/method, HTTP status and error
code, request/action ID if relevant, and a minimal redacted reproduction. Include
adapter version and capability list when available. Omit tokens, login codes,
private `.env` files, world saves and unrelated player data.
