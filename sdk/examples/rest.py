"""Deliberately acquire realtime control, stop, and release an existing body."""
import argparse

from scru_minecraft import AgentClient, GatewayError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('agent')
    parser.add_argument('--control', action='store_true', required=True)
    parser.add_argument('--from-env', action='store_true')
    parser.add_argument('--credentials', default='.scru-player.env')
    args = parser.parse_args()
    try:
        client = (AgentClient.from_env(agent=args.agent) if args.from_env else
                  AgentClient.from_file(args.credentials, agent=args.agent))
        with client.realtime() as agent:
            receipt = agent.action('stop')
            result = agent.wait_action(receipt['id'])
            print('Native stop:', result['state'], result.get('reason', ''))
            if result['state'] != 'done':
                parser.exit(1, 'Stop did not complete; inspect the reported result.\n')
        print('Control released.')
    except GatewayError as error:
        parser.exit(1, f'Gateway {error.status}: {error.code}; no automatic retry or resume.\n')
    except (OSError, ValueError, KeyError):
        parser.exit(1, 'Request could not be confirmed; inspect body state before retrying.\n')


if __name__ == '__main__':
    main()
