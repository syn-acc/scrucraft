"""VERIFY-06: stage the exact public compile dependency from pack.lock.json.

Use --source to verify and copy an already downloaded JAR without network access.
No server configuration, credentials or proprietary world data are required.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='Existing locked LuckPerms JAR (offline mode)')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    lock = json.loads((root.parent/'pack.lock.json').read_text(encoding='utf-8'))
    artifact = next(mod['file'] for mod in lock['mods'] if mod['slug'] == 'luckperms')
    expected = artifact['hashes']['sha512']
    destination = root/'build/dependencies/LuckPerms.jar'
    if destination.is_file() and hashlib.sha512(destination.read_bytes()).hexdigest() == expected:
        print('Locked LuckPerms dependency already verified.')
        return
    if args.source:
        data = args.source.read_bytes()
    else:
        if not artifact['url'].startswith('https://cdn.modrinth.com/'):
            raise ValueError('Expected a public HTTPS Modrinth artifact')
        with urllib.request.urlopen(artifact['url'], timeout=60) as response:
            data = response.read(32*1024*1024+1)
    if len(data) > 32*1024*1024 or hashlib.sha512(data).hexdigest() != expected:
        raise ValueError('LuckPerms dependency does not match pack.lock.json SHA-512')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.tmp')
    temporary.write_bytes(data)
    temporary.replace(destination)
    print('Verified and staged locked public LuckPerms compile dependency.')


if __name__ == '__main__':
    main()
