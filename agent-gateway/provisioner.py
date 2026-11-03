"""Narrow local broker: only validated spawn/remove commands, never arbitrary console input."""
import json
import os
import pathlib
import re
import socketserver
import stat

ROOT = pathlib.Path('/data/minecraft-syn-smp/server')
SOCKET = '/run/minecraft-syn-provisioner/control.sock'
JOBS = {'farmer', 'miner', 'builder', 'guard', 'medic', 'engineer'}


def members(root=ROOT):
    return json.loads((root/'whitelist.json').read_text())


def enrollment_message(value, root=ROOT):
    if set(value) != {'operation', 'name', 'uuid', 'code'}:
        raise ValueError('invalid_enrollment')
    name, code = value['name'], value['code']
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,16}', name):
        raise ValueError('invalid_name')
    if not isinstance(code, str) or not re.fullmatch(r'[0-9]{8}', code):
        raise ValueError('invalid_code')
    if not any(row['name'] == name and row['uuid'] == value['uuid'] for row in members(root)):
        raise ValueError('not_whitelisted')
    # Fixed private authentication message only; never accept arbitrary chat/commands.
    message = {'text': '[SCRU] Agent access verification: '+code+
        '. Expires in 5 minutes. Enter only in the SDK login you just requested. Ignore unsolicited codes.', 'color': 'aqua'}
    return 'tellraw '+name+' '+json.dumps(message, ensure_ascii=True)+'\n'


def command(value, root=ROOT):
    if not isinstance(value, dict) or set(value) != {'operation', 'name', 'job'}:
        raise ValueError('invalid_request')
    operation, name, job = value['operation'], value['name'], value['job']
    if operation not in {'spawn', 'remove'} or not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,16}', name):
        raise ValueError('invalid_name_or_operation')
    if not isinstance(job, str) or job not in JOBS:
        raise ValueError('invalid_job')
    # Never impersonate a real whitelisted player or administrator, even offline.
    reserved = set()
    for file in ('whitelist.json', 'ops.json'):
        for row in json.loads((root/file).read_text()):
            reserved.add(row['name'].lower())
    if name.lower() in reserved:
        raise ValueError('human_name_reserved')
    roster = json.loads((root/'config/syn-agents.json').read_text()).get('agents', [])
    existing = next((r for r in roster if r['name'].lower() == name.lower()), None)
    if operation == 'spawn' and existing:
        if existing['name'] != name or existing['job'] != job:
            raise ValueError('name_reserved')
        return None
    if operation == 'spawn' and len(roster) >= 10:
        raise ValueError('agent_cap')
    return f'synagent spawn {name} {job}\n' if operation == 'spawn' else f'synagent remove {name}\n'


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(3)
        try:
            value = json.loads(self.rfile.readline(4096))
            if value == {'operation': 'whitelist'}:
                self.wfile.write((json.dumps({'ok': True, 'members': members()})+'\n').encode())
                return
            line = enrollment_message(value) if isinstance(value, dict) and value.get('operation') == 'enroll' else command(value)
            if line:
                pipe = ROOT/'console.pipe'
                if not stat.S_ISFIFO(pipe.stat().st_mode):
                    raise ValueError('console_unavailable')
                fd = os.open(pipe, os.O_WRONLY | os.O_NONBLOCK)
                try:
                    os.write(fd, line.encode('ascii'))
                finally:
                    os.close(fd)
            result = {'ok': True, 'status': 'command_queued' if line else 'already_present'}
        except (ValueError, KeyError, TypeError):
            result = {'ok': False, 'error': 'invalid_or_reserved_agent'}
        except Exception:
            result = {'ok': False, 'error': 'console_unavailable'}
        self.wfile.write((json.dumps(result)+'\n').encode())


if __name__ == '__main__':
    path = pathlib.Path(SOCKET)
    if path.exists():
        path.unlink()
    with socketserver.UnixStreamServer(SOCKET, Handler) as server:
        path.chmod(0o660)
        server.serve_forever()
