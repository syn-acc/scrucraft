# Configuration and secret handling

The public repository contains source, documentation and synthetic test fixtures.
Production credentials, login files, provider keys, worlds and operational backups
do not belong here. Variable names are part of the API; their secret values are not.

## Player SDK

| Variable | Meaning | Sensitive value? |
| --- | --- | --- |
| `SCRU_AGENT_URL` | Gateway base URL; default `https://uk.syn.gl/minecraft-agents` | No |
| `SCRU_AGENT_ID` | Selected owned body name | No credential |
| `SCRU_AGENT_TOKEN` | Private player or scoped-body credential | **Yes** |
| `SYN_AGENT_URL`, `SYN_AGENT_ID`, `SYN_AGENT_TOKEN` | Legacy aliases | Token is sensitive |

`python -m scru_minecraft login YourUsername` saves `.scru-player.env` privately.
Use `AgentClient.from_file()` to load it or `AgentClient.from_env()` to read the
environment. Do not commit the file, print its contents, or send tokens to a model.
Keep credentials with the application running the SDK, outside agent prompts.

## Server components

| Variable or setting | Meaning | Handling |
| --- | --- | --- |
| `SYN_GATEWAY_CONFIG` | Path to private gateway settings | Keep deployment file outside Git |
| `SYN_GATEWAY_STATE` | Gateway state directory | Exclude databases and runtime state |
| `SYN_MODEL_PROVIDER` | Legacy controller provider selection | Non-secret configuration name |
| `SYN_MODEL_API_KEY` | Legacy controller provider credential | **Secret; never needed by external player agents** |
| `internal_token_file` / `token_file` | Paths to private bridge credentials | File contents must never enter Git |

Some `SCRU_*` names are assembled dynamically in the SDK. Do not assume a search
for literal variable names alone constitutes a credential audit. Read defaults
and configuration-loading code, and scan the full Git history before publishing.

## Repository checks

- The initial seven source commits were scanned with Gitleaks 8.30.1 across all
  refs: zero findings across 89 distinct historical file versions. No tracked
  `.env`, private-key, credential-store or database files were found.
- Provider keys are read from the environment with an empty key default. Bridge
  tokens are read from private files. Fixed tokens in isolated tests are synthetic
  fixtures, not server credentials.
- `.gitignore` excludes common secret/configuration files and runtime artifacts.
  Ignore rules do not remove files from history and are not a substitute for scanning.
- Before pushing, scan history with `gitleaks git --log-opts="--all" --redact=100`.
  Review findings privately. Do not post raw scanner output containing credentials.

A clean scan reduces risk; it is not a guarantee that every possible secret format
was detected. If a real credential is exposed, revoke it and follow
[the security reporting guidance](../SECURITY.md).
