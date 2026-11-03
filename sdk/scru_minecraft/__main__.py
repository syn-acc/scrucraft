"""Player-initiated Minecraft identity verification; never prints the issued token."""
import argparse
import getpass
import os
import warnings
from pathlib import Path
from . import AgentClient, GatewayError


def login_error(error):
    """Use fixed guidance, never a gateway's arbitrary payload or exception text."""
    messages = {
        'enrollment_expired': 'The login code expired or was already used. Run login again for a new private code.',
        'invalid_code': 'The code did not match. Check the latest private in-game message, then run login again for a new code.',
        'not_whitelisted': 'This Minecraft account is not currently whitelisted. Check your username and ask the server owner to confirm access.',
        'invalid_username': 'Use your Minecraft Java username (1–16 letters, digits or underscores).',
        'invalid_enrollment': 'The login request is no longer valid. Run login again for a new private code.',
        'identity_required': 'Your account must be verified again. Join Minecraft and run login for a new private code.',
        'rate_limited': 'Login is temporarily rate limited. Wait before requesting another private code.',
    }
    message = messages.get(error.code) if isinstance(error.code,str) else None
    if message is None:
        message = ('The login service is temporarily unavailable. Check connectivity and try again later.'
                   if isinstance(error.status,int) and error.status>=500 else
                   'Login was not accepted. Check your username and whitelist access, then request a new private code.')
    return message + ' No credential file was saved.\n'


def main():
    parser = argparse.ArgumentParser(prog='python -m scru_minecraft')
    parser.add_argument('command', choices=['login'])
    parser.add_argument('username', help='Your whitelisted Minecraft Java username')
    parser.add_argument('--output', default='.scru-player.env')
    args = parser.parse_args()
    destination = Path(args.output)
    if destination.exists():
        parser.error('Output already exists; use a different --output or your existing login file')
    print('Join uk.syn.gl in Minecraft before continuing. A private verification code will appear in-game.')
    try:
        challenge = AgentClient.start_login(args.username)
        with warnings.catch_warnings():
            warnings.simplefilter('error',getpass.GetPassWarning)
            code = getpass.getpass('Code from your private Minecraft chat: ').strip()
        access = AgentClient.finish_login(challenge['request_id'], code)
        token = access['token']
        if not isinstance(token,str) or not token or any(c in token for c in '\r\n'):
            raise ValueError('Invalid credential response')
    except GatewayError as error:
        parser.exit(1,login_error(error))
    except (EOFError,KeyboardInterrupt,getpass.GetPassWarning):
        parser.exit(1,'Login cancelled. Use an interactive terminal that can hide the private code, then run login again. No credential file was saved.\n')
    except OSError:
        parser.exit(1,'Could not reach the login gateway. Check your internet connection and server availability, then run login again. No credential file was saved.\n')
    except (KeyError,TypeError,ValueError):
        parser.exit(1,'The login service returned an invalid response. Request a new login later or contact the server owner. No credential file was saved.\n')
    created = False
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with open(descriptor, 'w') as output:
            output.write('SCRU_AGENT_URL=https://uk.syn.gl/minecraft-agents\nSCRU_AGENT_TOKEN='+token+'\n')
    except OSError:
        if created:
            try:destination.unlink()
            except OSError:pass
        parser.exit(1,'Could not save the private credential file. Check the output directory and permissions; use a new --output path and run login again.\n')
    print('Player access saved to '+str(destination)+'. Keep this file private; do not put it in prompts or Git.')


if __name__ == '__main__':
    main()
