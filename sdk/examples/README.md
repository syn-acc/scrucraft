# Examples

Install the SDK first. These scripts operate on an existing body and never create
one, rotate tokens or resume a human stop. Keep credentials in a private file or
process environment; never pass them as command-line arguments.

## Read-only observation

```sh
python examples/observe.py MyAgent --frames 5
```

By default this reads the owner's `.scru-player.env`. To use a scoped credential
already configured as `SCRU_AGENT_TOKEN`, add `--from-env`. The example does not
acquire control, submit goals or send chat. It prints a small view of your own
body; consider coordinates private when sharing its output.

## Deliberate stop request

```sh
python examples/rest.py MyAgent --from-env --control
```

The explicit `--control` flag is required. This uses WebSockets to acquire a lease,
submit native `stop`, wait for its terminal result, then release the lease. The
historical filename remains `rest.py`; it no longer calls disabled goal APIs.
It works with the live and candidate direct-control releases. Install the `stream`
extra. Stopping releases controls; external forces may still move the body.
For candidate gameplay methods, read the [candidate guide](../candidate-guidance.md).
