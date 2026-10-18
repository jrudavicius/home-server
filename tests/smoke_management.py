#!/usr/bin/env python3
"""Test management readiness, isolation, and recovery with disposable Docker state."""

import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

from management_backup_checks import check_backups, check_restored_login
from management_alert_checks import check_alerts


ROOT = Path(__file__).resolve().parents[1]


def eventually(check, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(1)
    raise AssertionError('Timed out waiting for ' + check.__name__)


def main():
    # Only fixtures are interpolated; never read the deployment's private .env.
    env = {key: value for key, value in os.environ.items()
           if key in ('PATH', 'HOME', 'TMPDIR', 'DOCKER_HOST', 'DOCKER_CONTEXT')}
    env.update({
        'KOMODO_DATABASE_USERNAME': 'readiness-test',
        'KOMODO_DATABASE_PASSWORD': 'test-only-$pass:word/with@symbols',
        'KOMODO_INIT_ADMIN_USERNAME': 'smoke-admin',
        'KOMODO_INIT_ADMIN_PASSWORD': 'test-only-admin-password',
        'KOMODO_WEBHOOK_SECRET': 'test-only-webhook-secret',
        'KOMODO_JWT_SECRET': 'test-only-jwt-secret',
        'GRAFANA_ADMIN_USER': 'test-only-admin',
        'GRAFANA_ADMIN_PASSWORD': 'test-only-password',
        'TRANSMISSION_USERNAME': 'test-only-user',
        'NGROK_AUTHTOKEN': 'test-only-token',
        'KOMODO_DISCORD_WEBHOOK_URL': 'http://app-probe:8080/api/webhooks/fixture/fixture',
    })
    production = json.loads(subprocess.check_output([
        'docker', 'compose', '--env-file', str(ROOT / 'bootstrap.env.example'),
        '-f', str(ROOT / 'docker-compose.yml'), 'config', '--format', 'json',
    ], env=env, text=True))
    project = 'management-smoke-' + uuid.uuid4().hex[:8]
    with tempfile.TemporaryDirectory(prefix=project + '-') as temporary:
        folder = Path(temporary)
        folder.chmod(0o755)
        gate = folder / 'gate.sh'
        gate.write_text('echo "READINESS_TEST_INITIALIZING"\n'
                        'until test -f /test-control/release; do sleep 1; done\n')
        config = copy.deepcopy(production)
        config['name'] = project
        # Re-scope every network and volume to this unique project.
        for network in config['networks'].values():
            assert not network.get('external')
            network.pop('name', None)
        for volume in config['volumes'].values():
            assert not volume.get('external')
            volume.pop('name', None)
        config['volumes'].update({'test-backups': {}, 'test-agent-state': {}})
        for service in config['services'].values():
            service.pop('container_name', None)
            service.pop('ports', None)
            service.pop('labels', None)
            service['restart'] = 'no'
        config['services']['database']['volumes'].extend([
            {'type': 'bind', 'source': str(gate),
             'target': '/docker-entrypoint-initdb.d/00-readiness-test.sh', 'read_only': True},
            {'type': 'bind', 'source': str(folder),
             'target': '/test-control', 'read_only': True},
        ])
        core = config['services']['control-plane']
        core['environment']['KOMODO_CLI_MAX_BACKUPS'] = '2'
        core['volumes'] = [mount for mount in core['volumes'] if mount['target'] != '/backups']
        core['volumes'].append({'type': 'volume', 'source': 'test-backups', 'target': '/backups'})
        agent = config['services']['host-agent']
        agent['volumes'] = [mount for mount in agent['volumes'] if mount['type'] == 'volume']
        agent['volumes'].append({'type': 'volume', 'source': 'test-agent-state',
                                'target': agent['environment']['PERIPHERY_ROOT_DIRECTORY']})
        # Probes have no host mounts. Periphery has no Docker socket in this test.
        for name, network in [('app-probe', 'default'), ('backend-probe', 'backend')]:
            config['services'][name] = {
                'image': config['services']['secret-bootstrap']['image'],
                'command': ['python', '-c', 'import time; time.sleep(1200)'],
                'networks': [network],
            }
        config['services']['app-probe']['command'] = [
            'python', '-c', (ROOT / 'tests/notification_sink.py').read_text(),
        ]
        compose = folder / 'compose.json'
        # Compose will parse this rendered configuration again; preserve dollars.
        compose.write_text(json.dumps(config).replace('$', '$$'))
        command = ['docker', 'compose', '--env-file', os.devnull,
                   '-p', project, '-f', str(compose)]

        def run(*args, check=True, input=None):
            result = subprocess.run(command + list(args), env=env, text=True,
                                    input=input, capture_output=True, timeout=180)
            if check and result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            return result

        def inspect(service):
            container = run('ps', '--all', '--quiet', service).stdout.strip()
            if not container:
                return None
            return json.loads(subprocess.check_output(
                ['docker', 'inspect', container], env=env, text=True))[0]

        def initializing():
            return 'READINESS_TEST_INITIALIZING' in run('logs', 'database').stdout

        def core_created():
            return inspect('control-plane') is not None

        def core_responds():
            return run('exec', '-T', 'app-probe', 'python', '-c',
                       'import urllib.request; '
                       'assert urllib.request.urlopen("http://control-plane:9120", timeout=2).status == 200',
                       check=False).returncode == 0

        def database_healthy():
            return inspect('database')['State']['Health']['Status'] == 'healthy'

        def can_connect(service, host, port):
            return run('exec', '-T', service, 'python', '-c',
                       'import socket,sys; socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=2).close()',
                       host, str(port), check=False).returncode == 0

        pending = None
        try:
            run('up', '-d', 'database', 'secret-bootstrap', 'app-probe', 'backend-probe')
            eventually(initializing)
            health_command = config['services']['database']['healthcheck']['test']
            assert health_command[0] == 'CMD'
            assert run('exec', '-T', 'database', *health_command[1:], check=False).returncode != 0
            with (folder / 'startup.log').open('w') as output:
                pending = subprocess.Popen(command + ['up', '-d', 'control-plane', 'host-agent'],
                                           env=env, stdout=output, stderr=subprocess.STDOUT)
                eventually(core_created)
                assert inspect('control-plane')['State']['Status'] == 'created'
                assert not database_healthy()
                print('Core waits while MongoDB is still initializing.', flush=True)
                (folder / 'release').touch()
                assert pending.wait(timeout=180) == 0, (folder / 'startup.log').read_text()
            eventually(database_healthy)
            eventually(core_responds)
            print('Authenticated MongoDB is healthy; Core serves HTTP on the application network.', flush=True)

            assert run('exec', '-T', '-e', 'MONGO_INITDB_ROOT_PASSWORD=wrong-test-password',
                       'database', *health_command[1:], check=False).returncode != 0
            assert run('exec', '-T', 'database', *health_command[1:]).returncode == 0
            print('Readiness accepts the configured credentials and rejects incorrect credentials.', flush=True)

            database = inspect('database')
            database_ip = database['NetworkSettings']['Networks'][project + '_backend']['IPAddress']
            assert can_connect('backend-probe', 'database', 27017)
            assert not can_connect('app-probe', 'database', 27017)
            assert not can_connect('app-probe', database_ip, 27017)
            print('Application containers cannot reach MongoDB by DNS name or backend IP.', flush=True)

            run('restart', 'database')
            eventually(database_healthy)
            eventually(core_responds)
            print('Existing database volume restarts successfully.', flush=True)

            check_alerts(run, ROOT, env)
            restored_database = check_backups(run, ROOT, folder, env)
            core['environment']['KOMODO_DATABASE_DB_NAME'] = restored_database
            compose.write_text(json.dumps(config).replace('$', '$$'))
            run('up', '-d', 'control-plane', 'host-agent')
            eventually(core_responds)
            check_restored_login(run, env)
            print('Core starts against the restored database and accepts login. All management smoke checks passed.', flush=True)
        finally:
            (folder / 'release').touch()
            if pending is not None and pending.poll() is None:
                pending.terminate()
                try:
                    pending.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pending.kill()
                    pending.wait()
            run('down', '--volumes', '--remove-orphans')


if __name__ == '__main__':
    main()
