#!/usr/bin/env python3
"""Check the public webhook boundary using disposable Traefik/nginx containers."""

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
        config = {'services': {
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
            base = 'http://' + run('port', 'proxy', '9121')
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

            def status(method, path):
                request = urllib.request.Request(base + path, method=method,
                                                 data=b'{}' if method == 'POST' else None)
                try:
                    with opener.open(request, timeout=5) as response:
                        return response.status
                except urllib.error.HTTPError as error:
                    return error.code

            allowed = '/listener/github/procedure/home-server-deploy/main'
            for attempt in range(30):
                if status('POST', allowed) == 204:
                    break
                time.sleep(1)
            else:
                raise AssertionError('Webhook route did not reach the fixture backend')
            for method, path in [
                ('GET', allowed), ('PUT', allowed), ('GET', '/'),
                ('GET', '/dashboard/'), ('GET', '/api/overview'),
                ('POST', '/auth/login/LoginLocalUser'), ('POST', '/read/GetVersion'),
                ('POST', '/write/UpdateStack'), ('POST', '/execute/DeployStack'),
                ('POST', '/listener/github-elsewhere/'),
                ('POST', '/listener/github/stack/media/deploy'),
                ('POST', '/listener/github/../../auth/login/LoginLocalUser'),
            ]:
                actual = status(method, path)
                assert actual == 404, (method, path, actual)
            assert status('POST', allowed) == 204
            print('GitHub POST delivery works; application/API paths, other methods, and traversal are blocked.')
        finally:
            run('down', '--volumes', '--remove-orphans')


if __name__ == '__main__':
    main()
