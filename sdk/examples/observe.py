"""Read a finite number of frames from an existing body; no control or mutation."""
import argparse
import json
import time

from scru_minecraft import AgentClient, GatewayError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('agent')
    parser.add_argument('--frames', type=int, default=5)
    parser.add_argument('--from-env', action='store_true')
    parser.add_argument('--credentials', default='.scru-player.env')
    args = parser.parse_args()
    if not 1 <= args.frames <= 60:
        parser.error('--frames must be between 1 and 60')
    try:
        client = (AgentClient.from_env(agent=args.agent) if args.from_env else
                  AgentClient.from_file(args.credentials, agent=args.agent))
        for index in range(args.frames):
            frame = client.observe()
            print(json.dumps({key: frame.get(key) for key in
                              ('id', 'agent', 'position', 'health', 'food', 'control')}))
            if index + 1 < args.frames:
                time.sleep(1.1)
    except GatewayError as error:
        parser.exit(1, f'Gateway {error.status}: {error.code}; see troubleshooting.\n')
    except (OSError, ValueError, KeyError):
        parser.exit(1, 'Could not read credentials or observation; check private configuration and connectivity.\n')


if __name__ == '__main__':
    main()
