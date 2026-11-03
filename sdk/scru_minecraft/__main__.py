"""Player-initiated Minecraft identity verification; never prints the issued token."""
import argparse
import getpass
import os
from pathlib import Path
from . import AgentClient


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
    challenge = AgentClient.start_login(args.username)
    code = getpass.getpass('Code from your private Minecraft chat: ').strip()
    access = AgentClient.finish_login(challenge['request_id'], code)
    with open(os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as output:
        output.write('SCRU_AGENT_URL=https://uk.syn.gl/minecraft-agents\nSCRU_AGENT_TOKEN='+access['token']+'\n')
    print('Player access saved to '+str(destination)+'. Keep this file private; do not put it in prompts or Git.')


if __name__ == '__main__':
    main()
