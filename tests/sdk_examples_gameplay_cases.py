"""SDK-01/04/05, VERIFY-06: clean installed SDK and documented examples.

Requires an offline wheelhouse containing the pinned build/runtime dependencies.
Runs only against the disposable fixture, with synthetic owner authentication.
It does not claim actual in-game code delivery or production HTTPS acceptance.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import ssl
import subprocess
import textwrap
import time
import urllib.parse
import urllib.request
import venv

from isolated_game_fixture import SOURCE, OWNER, wait_for


def clean_environment():
    allowed = {'PATH', 'SystemRoot', 'WINDIR', 'TEMP', 'TMP', 'HOME', 'LANG', 'LC_ALL', 'TZ'}
    environment = {key: value for key, value in os.environ.items() if key in allowed}
    environment.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
                       PIP_CONFIG_FILE=os.devnull, PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1',
                       NO_PROXY='127.0.0.1,localhost')
    return environment


def run_process(arguments, *, cwd, environment, label, timeout=60):
    """No raw subprocess errors enter public fixture evidence or expose credentials."""
    try:
        completed = subprocess.run(arguments, cwd=cwd, env=environment, capture_output=True,
                                   text=True, encoding='utf-8', errors='replace', timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(label + ' exceeded its finite subprocess timeout') from None
    # Logs stay inside the private fixture directory, including failed runs.
    (cwd / (label + '.stdout')).write_text(completed.stdout, encoding='utf-8')
    (cwd / (label + '.stderr')).write_text(completed.stderr, encoding='utf-8')
    if completed.returncode:
        raise RuntimeError(label + ' failed with exit status ' + str(completed.returncode) + '; inspect private fixture logs')
    return completed.stdout


@contextlib.contextmanager
def tls_front(fixture, directory):
    """Private, loopback-only TLS origin; exact examples retain HTTPS validation."""
    origin = urllib.parse.urlsplit(fixture.public_url)
    if origin.scheme != 'http' or origin.hostname != '127.0.0.1' or not origin.port or origin.path not in ('', '/'):
        raise ValueError('The example TLS front accepts only the fixture loopback HTTP origin')
    nginx = shutil.which('nginx') or ('/usr/sbin/nginx' if Path('/usr/sbin/nginx').is_file() else None)
    openssl = shutil.which('openssl')
    if not nginx or not openssl:
        raise RuntimeError('The packaged example fixture requires nginx and openssl')
    directory.mkdir(mode=0o700)
    certificate, key = directory/'certificate.pem', directory/'private-key.pem'
    environment = clean_environment()
    run_process([openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                 '-keyout', str(key), '-out', str(certificate), '-subj', '/CN=SCRUCraft isolated examples',
                 '-addext', 'subjectAltName=IP:127.0.0.1,DNS:localhost'],
                cwd=directory, environment=environment, label='certificate', timeout=30)
    key.chmod(0o600)
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0));port = reservation.getsockname()[1]
    config = directory/'nginx.conf'
    config.write_text(f'''worker_processes 1;
daemon off;
pid "{directory}/nginx.pid";
error_log "{directory}/nginx-error.log" warn;
events {{ worker_connections 64; }}
http {{
  access_log off;
  client_body_temp_path "{directory}/client-temp";
  proxy_temp_path "{directory}/proxy-temp";
  server {{
    listen 127.0.0.1:{port} ssl;
    ssl_certificate "{certificate}";
    ssl_certificate_key "{key}";
    location /internal/ {{ return 404; }}
    location = /v1/events {{
      proxy_pass {fixture.public_url}/v1/events;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_buffering off;
      proxy_read_timeout 60s;
    }}
    location / {{
      proxy_pass {fixture.public_url};
      proxy_http_version 1.1;
      proxy_set_header Connection "";
      proxy_buffering off;
    }}
  }}
}}
''', encoding='utf-8')
    url = 'https://127.0.0.1:' + str(port)
    context = ssl.create_default_context(cafile=str(certificate))
    with (directory/'nginx-start.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([nginx, '-p', str(directory), '-c', str(config)],
                                   stdout=log, stderr=subprocess.STDOUT, env=environment)
        try:
            def ready():
                if process.poll() is not None:
                    raise RuntimeError('Private example TLS proxy exited; inspect its fixture log')
                try:
                    with urllib.request.urlopen(url+'/v1/access', context=context, timeout=1) as response:
                        return response.status == 200
                except OSError:
                    return False
            wait_for(ready, 10, 'Private example TLS origin readiness')
            yield url, certificate
        finally:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


def run_cases(fixture, stream=None):
    def packaged_examples():
        wheelhouse_value = os.environ.get('SDK_EXAMPLE_WHEELHOUSE')
        if not wheelhouse_value:
            raise RuntimeError('Set SDK_EXAMPLE_WHEELHOUSE to staged offline setuptools, wheel and websockets 15.0.1 wheels')
        wheelhouse = Path(wheelhouse_value).resolve(strict=True)
        wheels = sorted(wheelhouse.glob('*.whl'))
        if not wheels:
            raise RuntimeError('The offline example wheelhouse contains no wheel files')
        directory = fixture.root/'sdk-packaged-examples'
        directory.mkdir(mode=0o700)
        source = directory/'source'
        source.mkdir()
        # Source allowlist: never copy local .env files or operational artifacts.
        for filename in ('pyproject.toml', 'README.md'):
            shutil.copyfile(SOURCE/'sdk'/filename, source/filename)
        expected = {}
        for package in ('scru_minecraft', 'syn_minecraft'):
            for path in (SOURCE/'sdk'/package).rglob('*.py'):
                relative = path.relative_to(SOURCE/'sdk')
                destination = source/relative;destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
                expected[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        environment = clean_environment()
        environment['PIP_FIND_LINKS'] = str(wheelhouse)
        virtual = directory/'venv'
        venv.EnvBuilder(with_pip=True, clear=False).create(virtual)
        python = virtual/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        run_process([str(python), '-m', 'pip', 'install', '--no-index', '--find-links', str(wheelhouse),
                     str(source)+'[stream]'], cwd=directory, environment=environment, label='install', timeout=180)
        verification = '''import hashlib,importlib.metadata,json,pathlib,sys
import scru_minecraft,websockets
root=pathlib.Path(scru_minecraft.__file__).parent.parent
expected=json.loads(pathlib.Path('source-hashes.json').read_text())
assert sys.prefix!=sys.base_prefix
assert pathlib.Path(scru_minecraft.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve())
assert importlib.metadata.version('websockets')=='15.0.1'
for name,digest in expected.items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
print(json.dumps({'sdk':importlib.metadata.version('scru-minecraft'),'websockets':importlib.metadata.version('websockets'),
                  'clean_virtual_environment':True,'module_hashes_match':True}))
'''
        (directory/'source-hashes.json').write_text(json.dumps(expected), encoding='utf-8')
        (directory/'verify-install.py').write_text(verification, encoding='utf-8')
        installed = json.loads(run_process([str(python), 'verify-install.py'], cwd=directory,
                                          environment=environment, label='verify-install'))
        run_process([str(python), '-m', 'scru_minecraft', '--help'], cwd=directory,
                    environment=environment, label='login-help')
        reference = (SOURCE/'sdk/docs/python-reference.md').read_text(encoding='utf-8')
        snippets = re.findall(r'```python\s*\n(.*?)```', reference, re.S)
        if len(snippets) != 2 or 'agent="MyAgent"' not in snippets[0] or 'client.async_realtime()' not in snippets[1]:
            raise AssertionError('Review runner coverage after Python reference examples change')
        # Preserve the actual snippets; top-level async documentation requires a
        # normal asyncio entry wrapper, not a patched client or transport shim.
        program = snippets[0] + '\nimport asyncio\nasync def documented_async_example():\n' + textwrap.indent(snippets[1], '    ')
        program += '\nasyncio.run(documented_async_example())\nprint("DOCUMENTED_EXAMPLES_COMPLETED")\n'
        (directory/'reference-examples.py').write_text(program, encoding='utf-8')
        for filename in ('observe.py', 'rest.py'):
            shutil.copyfile(SOURCE/'sdk/examples'/filename, directory/filename)
        # The docs use this literal placeholder. Never reuse/remove a pre-existing body.
        with fixture.gateway.changed:
            if fixture.gateway.db.execute('SELECT 1 FROM bodies WHERE name=?', ('MyAgent',)).fetchone():
                raise RuntimeError('Documented example body MyAgent already exists in this fixture')
            token = fixture.gateway.issue(OWNER['name'], 'player', player_uuid=OWNER['uuid'])
        digest = hashlib.sha256(token.encode()).hexdigest()
        credentials = directory/'.scru-player.env'
        try:
            for command in ('fill -2 64 -2 8 70 8 air', 'fill -2 63 -2 8 63 8 stone'):
                fixture.console(command)
            with tls_front(fixture, directory/'tls') as (url, certificate):
                descriptor = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with open(descriptor, 'w') as output:
                    output.write('SCRU_AGENT_URL='+url+'\nSCRU_AGENT_TOKEN='+token+'\n')
                environment.update(SSL_CERT_FILE=str(certificate), SCRU_AGENT_URL=url, SCRU_AGENT_TOKEN=token)
                reference_output = run_process([str(python), 'reference-examples.py'], cwd=directory,
                                               environment=environment, label='reference', timeout=120)
                assert 'DOCUMENTED_EXAMPLES_COMPLETED' in reference_output
                observe_output = run_process([str(python), 'observe.py', 'MyAgent', '--frames', '2'],
                                             cwd=directory, environment=environment, label='observe')
                observations = [json.loads(line) for line in observe_output.splitlines() if line.strip()]
                assert len(observations) == 2 and all(row['agent'] == 'MyAgent' for row in observations)
                assert all(not row['control']['lease_active'] for row in observations), 'Read-only example acquired control'
                stop_output = run_process([str(python), 'rest.py', 'MyAgent', '--from-env', '--control'],
                                          cwd=directory, environment=environment, label='rest')
                assert 'Native stop: done' in stop_output and 'Control released.' in stop_output
                with fixture.gateway.changed:
                    assert fixture.gateway.active('MyAgent') is None
                    assert fixture.gateway.body('MyAgent')['owner'] == OWNER['name']
                for log in directory.glob('*.std*'):
                    assert token not in log.read_text(encoding='utf-8'), 'Example output exposed a fixture credential'
                return {'installed': installed, 'source_sha256': expected,
                        'wheelhouse_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in wheels},
                        'python_reference_sha256': hashlib.sha256(reference.encode()).hexdigest(),
                        'readme_install': 'exact local candidate installed offline with stream extra; public download not substituted',
                        'login_command': 'help only; no real in-game enrollment claimed',
                        'python_reference_sync_and_async': 'unmodified snippets; async entry wrapper only',
                        'read_only_example_frames': len(observations), 'native_stop_example': 'done',
                        'tls_certificate_verified': True, 'plaintext_fallback': False,
                        'identity': 'synthetic fixture owner, not participating-player login',
                        'credentials_in_command_arguments': False, 'credential_output_check': 'passed'}
        finally:
            # Cleanup is fixture lifecycle management, not measured example behavior.
            with fixture.gateway.changed:
                row = fixture.gateway.db.execute('SELECT 1 FROM bodies WHERE name=?', ('MyAgent',)).fetchone()
            try:
                if row:
                    from scru_minecraft import AgentClient
                    cleanup = AgentClient(fixture.public_url, token, 'MyAgent', allow_local_http=True)
                    cleanup.remove_agent()
            finally:
                with fixture.gateway.changed:
                    fixture.gateway.db.execute('UPDATE tokens SET enabled=0 WHERE hash=?', (digest,));fixture.gateway.db.commit()
                if credentials.exists():credentials.unlink()
                environment.pop('SCRU_AGENT_TOKEN', None)

    fixture.case('packaged_sdk_documented_sync_async_observe_and_stop_examples',
                 ['SDK-01', 'SDK-04', 'SDK-05', 'VERIFY-06'], packaged_examples)
