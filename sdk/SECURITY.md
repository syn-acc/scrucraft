# Security and sensitive reports

Do not post tokens, verification codes, private login files, other players' data
or world saves in issues. Report suspected credential exposure or access-control
failures privately to the server host through your established contact channel.
No unverified support address or public disclosure endpoint is provided here.

Include the affected version, endpoint, time, error and a redacted reproduction.
Avoid testing a suspected access bypass against another player's body.

For an exposed body token, have the owner issue a replacement. For an exposed
player token, ask the host to revoke the owner's credentials. Logging in again
does not revoke all old tokens. Whitelist removal blocks further requests and
optional work, but is a host administration decision.

Read [access and privacy](docs/access-and-privacy.md) for token scopes, enrollment
and the current observation boundary.
