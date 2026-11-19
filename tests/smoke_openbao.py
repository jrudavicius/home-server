#!/usr/bin/env python3
"""Run the real Git-backed OpenBao stacks through an isolated Komodo on local Docker."""

import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid

from openbao_backup_checks import Vault, backup_and_restore, until
from komodo_webhook_checks import exercise_webhook

ROOT = Path(__file__).resolve().parents[1]

# Core is reachable only from its test network. Passwords and tokens stay on pipes.
API_CLIENT = """
import json, sys, urllib.request
path, body, token = json.load(sys.stdin)
headers = {'Content-Type': 'application/json'}
if token:
    headers['Authorization'] = token
req = urllib.request.Request('http://control-plane:9120/' + path, json.dumps(body).encode(), headers)
with urllib.request.urlopen(req, timeout=90) as response:
    print(json.dumps(json.load(response)))
"""


def run(args, env, *, data=None, cwd=None, timeout=240, check=True):
    result = subprocess.run(args, cwd=cwd, env=env, input=data, capture_output=True,
                            text=True, timeout=timeout, check=False)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip()[-2500:] or 'Command failed')
    return result


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def write_env(path, values):
    path.write_text(''.join(f'{k}={v}\n' for k, v in values.items()))


def git_origin(folder, env, settings, projects):
    checkout = folder / 'checkout'
    (checkout / 'komodo').mkdir(parents=True)
    for name in projects:
        shutil.copytree(ROOT / 'stacks' / name, checkout / 'stacks' / name,
                        ignore=shutil.ignore_patterns('.env', '__pycache__'))
        definition = (ROOT / 'komodo' / (name + '.toml')).read_text()
        # Only test-specific names, paths, retention and registry pull behavior differ.
        label = f'project_name = "{name}"'
        assert definition.count(label) == 1
        fixtures = '\n'.join(f'{k}={v}' for k, v in settings[name].items())
        definition = definition.replace(label, f'project_name = "{projects[name]}"\nenvironment = """\n{fixtures}\n"""')
        (checkout / 'komodo' / (name + '.toml')).write_text(definition.replace('auto_pull = true', 'auto_pull = false'))
    repo = (ROOT / 'komodo/repos.toml').read_text().replace('"github.com"', '"test-git"').replace('git_https = true', 'git_https = false')
    (checkout / 'komodo/repos.toml').write_text(repo)
    # Exercise the production deployment procedure with the unrelated Pi workloads omitted.
    deploy = (ROOT / 'komodo/procedures.toml').read_text().split('\n[[procedure]]', 1)[0]
    header, *stages = deploy.split('[[procedure.config.stage]]')
    stages = [s for s in stages if 'execution.type = "RunSync"' in s or
              any(f'execution.params.stack = "{name}"' in s for name in projects)]
    assert len(stages) == 3
    (checkout / 'komodo/procedures.toml').write_text(header + ''.join('[[procedure.config.stage]]' + s for s in stages))
    origin = folder / 'origin/jrudavicius'
    origin.mkdir(parents=True)
    git = ['git', '-c', 'user.name=OpenBao smoke', '-c', 'user.email=smoke@example.invalid',
           '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false']
    clean = {**env, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull}
    for args in (['init', '-b', 'main'], ['add', 'komodo', 'stacks'], ['commit', '-qm', 'Fixture stacks'],
                 ['clone', '--bare', '.', str(origin / 'home-server.git')]):
        run(git + args, clean, cwd=checkout)
    (origin / 'home-server').symlink_to('home-server.git', target_is_directory=True)


def management(folder, project, env, *, legacy_signer=None):
    integrated = legacy_signer is None
    cmd = ['docker', 'compose', '--env-file', str(ROOT / 'bootstrap.env.example'), '-f', str(ROOT / 'docker-compose.yml')]
    if integrated:
        cmd.extend(['-f', str(ROOT / 'docker-compose.openbao.yml')])
    config = json.loads(run(cmd + ['config', '--format', 'json'], env).stdout)
    config['name'] = project
    for resource in [*config['networks'].values(), *config['volumes'].values()]:
        if resource.get('external'):
            assert integrated and resource['name'] == env['OPENBAO_NETWORK']
            continue
        resource.pop('name', None)
    config['networks']['default']['internal'] = True
    config['volumes']['test-backups'] = {}
    services = config['services']
    for service in services.values():
        for field in ('container_name', 'ports', 'labels', 'dns'):
            service.pop(field, None)
        service['restart'] = 'no'

    core, agent = services['control-plane'], services['host-agent']
    core['volumes'] = [m for m in core['volumes'] if m['type'] == 'volume' or m['target'] in
                       ('/run/komodo-webhook', '/run/komodo-session', '/config/start-core.sh')]
    if integrated:
        session = str(folder / 'session-signing')
        next(m for m in core['volumes'] if m['target'] == '/run/komodo-session')['source'] = session
        delivery = services['session-agent']
        delivery['user'] = services['webhook-agent']['user']
        next(m for m in delivery['volumes'] if m['target'] == '/session')['source'] = session
    else:
        # Model the pre-migration deployment, which already has signed-in users.
        core.pop('command')
        core['volumes'] = [m for m in core['volumes'] if m['target'] != '/run/komodo-session']
        core['environment'].pop('KOMODO_CONFIG_PATHS')
        core['environment'].update(KOMODO_CONFIG_PATH='/config/bootstrap/core.config.json',
                                   KOMODO_JWT_SECRET=legacy_signer)
    core['volumes'].append('test-backups:/backups')
    # The Docker daemon and Periphery must resolve checked-out bind mounts at the same path.
    agent['environment'].update(PERIPHERY_DISABLE_TERMINALS='true', PERIPHERY_DISABLE_CONTAINER_TERMINALS='true')
    # file:// starts a second Git process. On Linux the read-only fixture belongs to the runner.
    git_config = folder / 'test.gitconfig'
    git_config.write_text('[url "file:///test-origin/"]\n\tinsteadOf = http://test-git/\n'
                          '[safe]\n\tdirectory = /test-origin/jrudavicius/home-server\n'
                          '\tdirectory = /test-origin/jrudavicius/home-server.git\n')
    for service in (core, agent):
        service['volumes'].extend([str(folder / 'origin') + ':/test-origin:ro',
                                   str(git_config) + ':/etc/gitconfig:ro'])
    services['client'] = {'image': services['secret-bootstrap']['image'], 'networks': ['default'],
                          'command': ['python', '-c', 'import time; time.sleep(3600)'],
                          'volumes': [str(ROOT / 'tests/openbao_backup_checks.py') + ':/test/restore.py:ro',
                                      str(folder / 'state/trust') + ':/trust:ro',
                                      str(folder / 'state/snapshots') + ':/snapshots:ro']}
    if integrated:
        assert 'KOMODO_WEBHOOK_SECRET' not in core['environment']
    target = folder / ('management-openbao.json' if integrated else 'management.json')
    target.write_text(json.dumps(config).replace('$', '$$'))
    target.chmod(0o600)
    return ['docker', 'compose', '--env-file', os.devnull, '-p', project, '-f', str(target)]


def certificates(folder, app, env):
    ca, signer = folder / 'ca.crt', folder / 'ca.key'
    run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-sha256', '-days', '2',
         '-subj', '/CN=OpenBao smoke CA', '-addext', 'basicConstraints=critical,CA:TRUE',
         '-addext', 'keyUsage=critical,keyCertSign,cRLSign', '-addext', 'subjectKeyIdentifier=hash',
         '-keyout', str(signer), '-out', str(ca)], env)
    run(['sh', str(ROOT / 'scripts/openbao_certificates.sh'), str(ca), str(signer), str(folder / 'certs')], env)
    # Only the fixture database uses this identity. The issuer verifies its TLS hostname.
    tls = app / 'local/db-tls'
    tls.mkdir(parents=True)
    request = str(folder / 'db.csr')
    run(['openssl', 'req', '-new', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=monitor-db',
         '-keyout', str(tls / 'server.key'), '-out', request], env)
    extensions = folder / 'extensions'
    extensions.write_text('extendedKeyUsage=serverAuth\nsubjectAltName=DNS:monitor-db,DNS:db\n')
    run(['openssl', 'x509', '-req', '-sha256', '-in', request, '-CA', str(ca), '-CAkey', str(signer),
         '-set_serial', '2', '-days', '2', '-extfile', str(extensions), '-out', str(tls / 'server.crt')], env)
    shutil.copyfile(ca, app / 'local/ca.crt')
    (app / 'local/ca.crt').chmod(0o444)
    (app / 'local/postgres-password').write_text(secrets.token_hex(32))
    (app / 'local/postgres-password').chmod(0o600)
    (app / 'local/approle').mkdir(mode=0o700)


def exercise(folder, prefix, env):
    env['PERIPHERY_ROOT_DIRECTORY'] = str(folder / 'periphery')
    (folder / 'periphery').mkdir()
    projects = {'openbao': prefix + '-bao', 'openbao-backup': prefix + '-backup'}
    app_project, restore_project = prefix + '-app', prefix + '-restore'
    net, pgdata = prefix + '-link', prefix + '-pg'
    state, restored = folder / 'state', folder / 'restored'
    app = folder / 'monitor'
    shutil.copytree(ROOT / 'tests/fixtures/openbao-monitor', app, ignore=shutil.ignore_patterns('local', '.env', '__pycache__'))
    uid, gid = (os.geteuid(), os.getegid()) if os.geteuid() else (10001, 10001)
    buid, bgid = (uid, gid) if os.geteuid() else (10002, 10002)
    port = free_port()
    server_settings = dict(OPENBAO_STATE_DIR=state, OPENBAO_NETWORK=net, OPENBAO_PORT=port, OPENBAO_UID=uid, OPENBAO_GID=gid)
    backup_settings = dict(OPENBAO_STATE_DIR=state, OPENBAO_NETWORK=net, OPENBAO_BACKUP_UID=buid,
                           OPENBAO_BACKUP_GID=bgid, OPENBAO_SNAPSHOT_KEEP=2)
    settings = {'openbao': server_settings, 'openbao-backup': backup_settings}
    for name, values in settings.items():
        write_env(folder / (name + '.env'), values)
    write_env(app / '.env', dict(RUN_UID=uid, RUN_GID=gid, OPENBAO_LINK=net, BAO_PORT=port, MONITOR_DB_VOLUME=pgdata))
    certificates(folder, app, env)
    if not os.geteuid():
        os.chown(app / 'local/approle', uid, gid)
    git_origin(folder, env, settings, projects)
    original_jwt = ' "special$\\ž\n' + secrets.token_hex(24) + ' '
    manager = management(folder, prefix, env, legacy_signer=original_jwt)

    def docker(*args, **kwargs):
        return run(['docker', *args], env, **kwargs)

    def stack(name, *args, **kwargs):
        return docker('compose', '--env-file', str(folder / (name + '.env')), '-p', projects[name],
                      '-f', str(ROOT / 'stacks' / name / 'docker-compose.yml'), *args, **kwargs)

    def monitor(*args, **kwargs):
        return docker('compose', '--env-file', str(app / '.env'), '-p', app_project, '-f', str(app / 'compose.yaml'), *args, **kwargs)

    def prep(root, network, release='certs'):
        run([sys.executable, str(ROOT / 'scripts/prepare_openbao.py'), str(folder / release),
             '--state-dir', str(root), '--network', network, '--server-user', f'{uid}:{gid}', '--backup-user', f'{buid}:{bgid}'], env)

    token = ''

    def api(path, body, ready=True):
        result = run(manager + ['exec', '-T', 'client', 'python', '-c', API_CLIENT], env,
                     data=json.dumps([path, body, token]), check=ready)
        return json.loads(result.stdout) if result.returncode == 0 else None

    def execute(action, **body):
        identifier = api('execute/' + action, body)['_id']['$oid']

        def complete():
            item = api('read/GetUpdate', {'id': identifier})
            if item['status'] == 'Complete':
                if not item['success']:
                    messages = [log.get('stderr') or log.get('stdout', '') for log in item.get('logs', [])]
                    raise RuntimeError(action + ' failed: ' + ' '.join(messages)[-2400:])
                return True

        until(action, complete, seconds=240)

    restore_cmd = None

    def restore_snapshot(snapshot, token, key):
        nonlocal restore_cmd
        new_port = free_port()
        docker('network', 'create', '--internal', prefix + '-recovery-link')
        prep(restored, prefix + '-recovery-link')
        path = folder / 'restore.env'
        write_env(path, {**server_settings, 'OPENBAO_STATE_DIR': restored, 'OPENBAO_NETWORK': prefix + '-recovery-link',
                         'OPENBAO_PORT': new_port})
        restore_cmd = ['compose', '--env-file', str(path), '-p', restore_project, '-f', str(ROOT / 'stacks/openbao/docker-compose.yml')]
        docker(*restore_cmd, 'up', '-d')
        client_id = run(manager + ['ps', '-q', 'client'], env).stdout.strip()
        docker('network', 'connect', prefix + '-recovery-link', client_id)
        # Internal Docker bridges have no published host ports. The client is the only other member.
        run(manager + ['exec', '-T', 'client', 'python', '/test/restore.py'], env,
            data=json.dumps({'snapshot': snapshot.name, 'token': token, 'key': key}))


    try:
        prep(state, net)
        prep(state, net)  # Existing identities, network and data must survive another preparation.
        docker('volume', 'create', pgdata)
        run(manager + ['up', '-d'], env)
        login = until('Komodo login', lambda: api('auth/login/LoginLocalUser', {
            'username': env['KOMODO_INIT_ADMIN_USERNAME'], 'password': env['KOMODO_INIT_ADMIN_PASSWORD']}, ready=False))
        token = login['data']['jwt']
        until('Periphery', lambda: api('read/GetServerState', {'server': 'home-server'})['status'] == 'Ok')
        api('write/CreateResourceSync', {'name': 'home-server-resources', 'config': {
            'repo': 'jrudavicius/home-server', 'git_provider': 'test-git', 'git_https': False, 'branch': 'main',
            'resource_path': ['komodo'], 'delete': False, 'managed': False, 'webhook_enabled': False}})
        execute('RunSync', sync='home-server-resources')
        for name in projects:
            config = api('read/GetStack', {'stack': name})['config']
            assert config['linked_repo'] and not config['files_on_host'] and config['run_directory'] == 'stacks/' + name
        schedule = next(p['info'] for p in api('read/ListProcedures', {}) if p['name'] == 'Backup OpenBao')
        assert not schedule.get('schedule_error') and schedule['next_scheduled_run'] > time.time() * 1000, schedule
        execute('RunProcedure', procedure='home-server-deploy')
        source = Vault(port, state / 'trust/ca.crt')
        root_token, key = source.initialize(until)
        configure = [sys.executable, str(ROOT / 'scripts/configure_openbao.py'), '--port', str(port),
                     '--state-dir', str(state)]
        for _ in range(2):
            run(configure, env, data=root_token + '\n')
        until('backup agent to authenticate by certificate', lambda:
              stack('openbao-backup', 'exec', '-T', 'agent', 'test', '-s', '/session/token', check=False).returncode == 0)
        print('Komodo synced from Git and deployed both production stacks. The backup agent authenticated.', flush=True)
        backup_token = stack('openbao-backup', 'exec', '-T', 'agent', 'cat', '/session/token').stdout.strip()
        backup_and_restore(execute, source, root_token, key, backup_token, state / 'snapshots', restore_snapshot)

        original = stack('openbao', 'ps', '-q', 'server').stdout.strip()
        assert original
        started = docker('inspect', '--format', '{{.State.StartedAt}}', original).stdout
        execute('RunProcedure', procedure='home-server-deploy')
        execute('StopStack', stack='openbao-backup')
        assert not stack('openbao-backup', 'ps', '-q', '--status', 'running').stdout.strip()
        assert source.request('sys/seal-status')['sealed'] is False
        assert stack('openbao', 'ps', '-q', 'server').stdout.strip() == original
        assert docker('inspect', '--format', '{{.State.StartedAt}}', original).stdout == started
        old_client = Vault(port, folder / 'ca.crt')
        old_client.tls.load_cert_chain(str(folder / 'certs/backup.crt'), str(folder / 'certs/backup.key'))
        login_path = 'auth/openbao-backup/login'
        login_request = {'name': 'openbao-backup'}
        old_token = old_client.request(login_path, login_request)['auth']['client_token']
        assert old_client.request('auth/token/lookup-self', token=old_token)['data']['renewable']
        run(['sh', str(ROOT / 'scripts/openbao_certificates.sh'), str(folder / 'ca.crt'),
             str(folder / 'ca.key'), str(folder / 'renewed-certs')], env)
        prep(state, net, 'renewed-certs')
        cert = folder / 'renewed-certs/server.crt'
        digest = hashlib.sha256(cert.read_bytes()).hexdigest()
        until('updated public certificate on the server bind mount', lambda:
              docker('exec', original, 'sha256sum', '/tls/current/cert.pem').stdout.split()[0] == digest)
        docker('kill', '--signal=HUP', original)
        until('renewed server certificate', lambda: source.presents(cert))
        run(configure + ['--rotate-backup-identity'], env, data=root_token + '\n')
        old_client.expect_denied(login_path, login_request)
        source.expect_denied('auth/token/lookup-self', token=old_token)
        assert source.request('sys/seal-status')['sealed'] is False
        execute('StartStack', stack='openbao-backup')
        def authenticated_again():
            current = stack('openbao-backup', 'exec', '-T', 'agent', 'cat', '/session/token', check=False)
            return current.returncode == 0 and current.stdout.strip() and current.stdout.strip() != backup_token

        until('backup agent to authenticate with its replacement certificate', authenticated_again)
        execute('RunProcedure', procedure='Backup OpenBao')
        assert (state / 'audit/audit.json').stat().st_size > 0
        print('PASS: both TLS identities renewed. The old certificate and token were denied; the new agent backed up successfully.', flush=True)
        print('PASS: unchanged deployment and certificate renewal left the server running and unsealed.', flush=True)

        monitor('up', '-d', 'monitor-db')
        until('PostgreSQL', lambda: monitor('exec', '-T', 'monitor-db', 'pg_isready', '-h', 'monitor-db', '-d', 'telemetry', check=False).returncode == 0)
        run([sys.executable, str(app / 'provision.py')], {**env, 'COMPOSE_PROJECT_NAME': app_project}, data=root_token + '\n')
        monitor('up', '-d')
        print('Verifying expiry and revocation with the long-running database client.', flush=True)
        proof = monitor('exec', '-T', 'monitor', 'sh', '/config/verify.sh', timeout=300)
        print(proof.stdout.strip(), flush=True)

        # The webhook recovery check deliberately seals the vault and restarts Core.
        # Finish the scenarios that use the running scheduler and database leases first.
        webhook_env = {**env, 'OPENBAO_STATE_DIR': str(state), 'OPENBAO_NETWORK': net,
                       'KOMODO_WEBHOOK_UID': str(uid), 'KOMODO_WEBHOOK_GID': str(gid)}
        del webhook_env['KOMODO_WEBHOOK_SECRET']
        integrated = management(folder, prefix, webhook_env)
        def session_works():
            return (api('read/GetServerState', {'server': 'home-server'}, ready=False) or {}).get('status') == 'Ok'
        exercise_webhook(folder, run, integrated, env, configure, source, root_token, key, uid, gid,
                         original_jwt, session_works)
    finally:
        # Stop the scheduler and any in-flight Periphery deployments before removing their consumers.
        run(manager + ['exec', '-T', 'host-agent', 'chown', '-R', f'{os.geteuid()}:{os.getegid()}',
                       str(folder / 'periphery')], env, check=False)
        run(manager + ['down', '--volumes', '--remove-orphans'], env)
        if restore_cmd:
            docker(*restore_cmd, 'down', '--volumes')
        monitor('down', '--volumes')
        for name in ('openbao-backup', 'openbao'):
            stack(name, '--profile', '*', 'down', '--volumes')
        if pgdata in docker('volume', 'ls', '--format', '{{.Name}}').stdout.splitlines():
            docker('volume', 'rm', pgdata)
        networks = docker('network', 'ls', '--format', '{{.Name}}').stdout.splitlines()
        for name in (net, prefix + '-recovery-link'):
            if name in networks:
                docker('network', 'rm', name)


def main():
    env = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'TMPDIR', 'DOCKER_CONTEXT', 'DOCKER_HOST', 'DOCKER_CONFIG')}
    if env.get('DOCKER_HOST') and not env.get('DOCKER_CONTEXT'):
        endpoint = env['DOCKER_HOST']
    else:
        endpoint = run(['docker', 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'], env).stdout.strip()
    if not endpoint.startswith('unix://'):
        raise SystemExit('Run this test with a local Unix-socket Docker engine.')
    env['DOCKER_SOCKET_PATH'] = '/var/run/docker.sock' if sys.platform == 'darwin' else endpoint[len('unix://'):]
    for key in ('KOMODO_DATABASE_USERNAME', 'KOMODO_DATABASE_PASSWORD', 'KOMODO_INIT_ADMIN_PASSWORD',
                'KOMODO_WEBHOOK_SECRET', 'GRAFANA_ADMIN_PASSWORD'):
        env[key] = secrets.token_hex(24)
    env.update(KOMODO_INIT_ADMIN_USERNAME='smoke-admin', GRAFANA_ADMIN_USER='smoke-admin',
               TRANSMISSION_USERNAME='smoke-user', KOMODO_HOST='http://control-plane:9120')
    prefix = 'openbao-smoke-' + uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix=prefix + '-', dir='/tmp') as temp:
        exercise(Path(temp).resolve(), prefix, env)
    print('Removed disposable projects, networks, volumes and credentials.', flush=True)


if __name__ == '__main__':
    main()
