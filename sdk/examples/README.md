# Examples

Install the SDK first. These scripts operate on an existing body and never create
one, rotate tokens or resume a human stop. Keep credentials in a private file or
process environment; never pass them as command-line arguments.

## Read-only observation

```sh
python examples/observe.py Syn_MyAgent --frames 5
```

By default this reads the owner's `.scru-player.env`. To use a scoped credential
already configured as `SCRU_AGENT_TOKEN`, add `--from-env`. The example does not
acquire control, submit goals or send chat. It prints a small view of your own
body; consider coordinates private when sharing its output.

## Deliberate rest request

```sh
python examples/rest.py Syn_MyAgent --from-env --control
```

The explicit `--control` flag is required. This acquires a lease, submits `rest`,
reports acceptance without claiming completion, then releases the lease. It is a
connection check, not an autonomous gathering loop or a guarantee of immobility.
For direct movement, consult the development contract and inspect capabilities
before submitting a target authorized by the player.
