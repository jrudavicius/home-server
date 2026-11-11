#!/usr/bin/env python3
"""Check active gateway and rollback proxy boundaries with disposable containers."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[1]
CADDY_IMAGE = 'caddy:2.11.9-alpine@sha256:0bbb055bda6793c999bde78b1b5ce3e89f829fb031af2cf50056ea1246559fee'


def main():
    env = {key: value for key, value in os.environ.items()
           if key in ('PATH', 'HOME', 'TMPDIR', 'DOCKER_HOST', 'DOCKER_CONTEXT')}
    entrypoint = ROOT / 'stacks/entrypoint'
    production = json.loads(subprocess.check_output([
        'docker', 'compose', '--env-file', str(entrypoint / '.env.example'),
        '-f', str(entrypoint / 'docker-compose.yml'), 'config', '--format', 'json',
    ], env=env, text=True))['services']
    project = 'private-access-smoke-' + uuid.uuid4().hex[:8]
    with tempfile.TemporaryDirectory(prefix=project + '-') as temporary:
        folder = Path(temporary)
        folder.chmod(0o755)
        (folder / 'nginx.conf').write_text(
            'events {}\nhttp { server { listen 9120; location / { return 204; } } }\n')
        # Adapt the production Caddyfile, then replace only TLS/listener settings
        # for the isolated fixture. No public certificates or services are used.
        gateway = json.loads(subprocess.check_output([
            'docker', 'run', '--rm',
            '-e', 'WEBHOOK_PUBLIC_IP=203.0.113.10',
            '-e', 'WEBHOOK_UPSTREAM=management-control-plane:9120',
            '-v', str(ROOT / 'host/netcup-webhook/Caddyfile') + ':/etc/caddy/Caddyfile:ro',
            CADDY_IMAGE, 'caddy', 'adapt', '--config', '/etc/caddy/Caddyfile',
        ], env=env, text=True))
        servers = gateway['apps']['http']['servers']
        secure = next(server for server in servers.values() if ':443' in server['listen'])
        plaintext = next(server for server in servers.values() if ':80' in server['listen'])
        for server, port in [(secure, 8080), (plaintext, 8081)]:
            server['listen'] = [':' + str(port)]
            server.pop('tls_connection_policies', None)
            server['automatic_https'] = {'disable': True}
        gateway['apps'].pop('tls', None)
        gateway['admin'] = {'disabled': True}
        (folder / 'caddy.json').write_text(json.dumps(gateway))
        config = {'services': {
            'gateway': {
                'image': CADDY_IMAGE,
                'command': ['caddy', 'run', '--config', '/etc/caddy/config.json'],
                'ports': ['127.0.0.1::8080', '127.0.0.1::8081'],
                'volumes': [str(folder / 'caddy.json') + ':/etc/caddy/config.json:ro'],
            },
            'proxy': {
                'image': production['reverse-proxy']['image'],
                'command': production['reverse-proxy']['command'],
                'ports': ['127.0.0.1::9121'],
                'volumes': [str(entrypoint / 'traefik/dynamic.yml') + ':/etc/traefik/dynamic/dynamic.yml:ro'],
            },
            'management-control-plane': {
                'image': production['landing-page']['image'],
                'volumes': [str(folder / 'nginx.conf') + ':/etc/nginx/nginx.conf:ro'],
            },
        }}
        compose = folder / 'compose.json'
        compose.write_text(json.dumps(config))
        command = ['docker', 'compose', '--env-file', os.devnull,
                   '-p', project, '-f', str(compose)]

        def run(*args):
            return subprocess.check_output(command + list(args), env=env, text=True).strip()

        try:
            run('up', '-d', '--wait', '--wait-timeout', '60')
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

            def status(base, method, path):
                request = urllib.request.Request(base + path, method=method,
                                                 headers={'Host': '203.0.113.10'},
                                                 data=b'{}' if method == 'POST' else None)
                try:
                    with opener.open(request, timeout=5) as response:
                        return response.status
                except urllib.error.HTTPError as error:
                    return error.code

            allowed = '/listener/github/procedure/home-server-deploy/main'
            blocked = [
                ('GET', allowed), ('PUT', allowed), ('GET', '/'),
                ('GET', '/dashboard/'), ('GET', '/api/overview'),
                ('POST', '/auth/login/LoginLocalUser'), ('POST', '/read/GetVersion'),
                ('POST', '/write/UpdateStack'), ('POST', '/execute/DeployStack'),
                ('POST', '/listener/github-elsewhere/'),
                ('POST', '/listener/github/stack/media/deploy'),
                ('POST', '/listener/github/../../auth/login/LoginLocalUser'),
            ]
            for service, port in [('proxy', '9121'), ('gateway', '8080')]:
                base = 'http://' + run('port', service, port)
                for attempt in range(30):
                    if status(base, 'POST', allowed) == 204:
                        break
                    time.sleep(1)
                else:
                    raise AssertionError(service + ' did not reach the fixture backend')
                cases = list(blocked)
                if service == 'gateway':
                    cases += [('POST', path) for path in [
                        allowed + '/', allowed + '?extra=1',
                        allowed.replace('/main', '/%6dain'),
                        allowed + '/../main', allowed + '/%2e%2e/main',
                        allowed.replace('/procedure/', '//procedure/'),
                        '/listener/github/%2e%2e/%2e%2e/auth/login/LoginLocalUser',
                    ]]
                for method, path in cases:
                    actual = status(base, method, path)
                    assert actual == 404, (service, method, path, actual)
                assert status(base, 'POST', allowed) == 204
                print(service + ': exact GitHub POST succeeds; other methods, paths and traversal are blocked.')
            plaintext = 'http://' + run('port', 'gateway', '8081')
            assert status(plaintext, 'POST', allowed) == 404
            assert status(plaintext, 'GET', '/') == 404
            print('Gateway plaintext requests are rejected.')
        finally:
            run('down', '--volumes', '--remove-orphans')


if __name__ == '__main__':
    main()
