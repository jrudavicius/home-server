#!/usr/bin/env python3
"""Exercise the provisioned dashboards and alerts against the pinned Docker images."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = 'local-observability-smoke-test'


def request(base, path, data=None, auth=False):
    headers = {}
    if auth:
        headers['Authorization'] = 'Basic ' + base64.b64encode(
            ('admin:' + PASSWORD).encode()).decode()
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(base + path, headers=headers,
                                 data=None if data is None else json.dumps(data).encode())
    with urllib.request.urlopen(req, timeout=20) as response:
        body = response.read()
        return json.loads(body) if body else None


def eventually(check, timeout=90):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            last_error = error
        time.sleep(2)
    raise AssertionError('Timed out waiting for readiness or alert state: ' + str(last_error))


def deployment_services(discord):
    # Read the same pins used in production without loading private .env files
    # or requiring production credentials. This command does not start services.
    command = [
        'docker', 'compose', '--env-file', os.devnull,
        '-f', str(ROOT / 'docker-compose.yml'),
    ]
    if discord:
        command.extend(['-f', str(ROOT / 'docker-compose.discord.yml')])
    env = {key: value for key, value in os.environ.items()
           if key in ('PATH', 'HOME', 'TMPDIR', 'DOCKER_HOST', 'DOCKER_CONTEXT')}
    env.update(GRAFANA_ADMIN_USER='admin', GRAFANA_ADMIN_PASSWORD=PASSWORD,
               GRAFANA_DISCORD_WEBHOOK_URL='http://notification-sink:8080/api/webhooks/fixture/fixture')
    config = json.loads(subprocess.check_output(command + ['config', '--format', 'json'],
                                               env=env, text=True))
    return config['services']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keep', action='store_true', help='Keep the isolated stack for visual inspection')
    parser.add_argument('--discord', action='store_true', help='Verify delivery to a local Discord-compatible receiver')
    args = parser.parse_args()
    services = deployment_services(args.discord)
    project = 'observability-smoke-' + uuid.uuid4().hex[:8]
    temp = Path(tempfile.mkdtemp(prefix=project + '-'))
    compose_path = temp / 'compose.json'
    # No Alloy or Docker socket: only synthetic logs enter this test stack.
    compose = {
        'services': {
            'log-store': {
                'image': services['log-store']['image'],
                'command': ['-config.file=/etc/loki/loki.yml', '-config.expand-env=true'],
                'ports': ['127.0.0.1::3100'],
                'volumes': [str(ROOT / 'loki/loki.yml') + ':/etc/loki/loki.yml:ro', 'loki-data:/loki'],
            },
            'log-dashboard': {
                'image': services['log-dashboard']['image'],
                'ports': ['127.0.0.1::3000'],
                'environment': {
                    **services['log-dashboard']['environment'],
                    'GF_SECURITY_ADMIN_PASSWORD': PASSWORD,
                    'GF_PLUGINS_PREINSTALL_DISABLED': 'true',
                    'GF_ANALYTICS_CHECK_FOR_UPDATES': 'false',
                    'GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES': 'false',
                    'GF_ANALYTICS_REPORTING_ENABLED': 'false',
                    'GF_UNIFIED_ALERTING_ENABLED': 'true',
                    'GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH': '/var/lib/grafana/dashboards/home-server-overview.json',
                },
                'volumes': services['log-dashboard']['volumes'],
            },
        },
        'volumes': {'grafana-data': {}, 'loki-data': {}},
    }
    if args.discord:
        root = ROOT.parents[1]
        management = json.loads(subprocess.check_output([
            'docker', 'compose', '--env-file', os.devnull,
            '-f', str(root / 'docker-compose.yml'),
            'config', '--no-interpolate', '--format', 'json',
        ], text=True))
        compose['services']['notification-sink'] = {
            'image': management['services']['secret-bootstrap']['image'],
            'command': ['python', '-c', (root / 'tests/notification_sink.py').read_text()],
        }
    compose_path.write_text(json.dumps(compose))
    command = ['docker', 'compose', '-p', project, '-f', str(compose_path)]

    def docker(*arguments):
        return subprocess.check_output(command + list(arguments), text=True).strip()

    try:
        docker('up', '-d', '--wait', '--wait-timeout', '90')
        loki = 'http://' + docker('port', 'log-store', '3100')
        grafana = 'http://' + docker('port', 'log-dashboard', '3000')
        eventually(lambda: request(grafana, '/api/health')['database'] == 'ok')
        # Loki's /ready response is plaintext; querying also verifies the query path.
        def query(expr, instant=True):
            params = {'query': expr}
            if not instant:
                params.update(start=str(time.time_ns() - 3600 * 10**9), end=str(time.time_ns()), step='60', limit='500')
            return request(loki, '/loki/api/v1/' + ('query' if instant else 'query_range') + '?' + urllib.parse.urlencode(params))['data']['result']

        eventually(lambda: query('vector(1)'))
        print('Grafana and Loki are ready.', flush=True)
        assert float(query('sum(absent_over_time({job="docker"}[15m])) or vector(0)')[0]['value'][1]) == 1

        source = json.loads((ROOT / 'grafana/provisioning/alerting/docker-alerts.json').read_text())
        rules = source['groups'][0]['rules']
        provisioned = request(grafana, '/api/v1/provisioning/alert-rules', auth=True)
        assert {r['uid'] for r in rules} == {r['uid'] for r in provisioned}
        expected_receiver = 'home-server-discord' if args.discord else 'empty'
        for rule in provisioned:
            assert rule['notification_settings']['receiver'] == expected_receiver
        config = request(grafana, '/api/alertmanager/grafana/config/api/v1/alerts', auth=True)['alertmanager_config']
        receiver = next(r for r in config['receivers'] if r['name'] == 'empty')
        assert not receiver.get('grafana_managed_receiver_configs')
        if args.discord:
            receiver = next(r for r in config['receivers'] if r['name'] == expected_receiver)
            assert receiver['grafana_managed_receiver_configs'][0]['type'] == 'discord'
        for rule in rules[:2]:
            assert query(rule['data'][0]['model']['expr']) == []
        print('Three alert rules provisioned; no-data behavior and receiver ' + expected_receiver + ' verified.', flush=True)

        stamp = time.time_ns() - 30 * 10**9
        fixtures = {
            'healthy': ['level=info msg="ready"', '{"level":"info","error":null,"errors":0}', 'level=info query=' + rules[0]['data'][0]['model']['expr'], 'path C:\\data "quoted"'],
            'errors': ['level=error msg="connection refused"'] * 10,
            'fatal': ['panic: fixture failure'],
            'mongo': ['{"s":"E","msg":"fixture error"}'],
        }
        streams = [{'stream': {'job': 'docker', 'compose_project': 'smoke', 'service': name, 'container': 'fixture-' + name},
                    'values': [[str(stamp + i), line] for i, line in enumerate(lines)]}
                   for name, lines in fixtures.items()]
        request(loki, '/loki/api/v1/push', {'streams': streams})
        error_counts = {r['metric']['container']: float(r['value'][1]) for r in query(rules[0]['data'][0]['model']['expr'])}
        assert error_counts == {'fixture-healthy': 0, 'fixture-errors': 10, 'fixture-fatal': 1, 'fixture-mongo': 1}, error_counts
        critical_counts = {r['metric']['container']: float(r['value'][1]) for r in query(rules[1]['data'][0]['model']['expr'])}
        assert critical_counts == {'fixture-healthy': 0, 'fixture-errors': 0, 'fixture-fatal': 1, 'fixture-mongo': 0}, critical_counts
        assert float(query(rules[2]['data'][0]['model']['expr'])[0]['value'][1]) == 0

        for dashboard_path in sorted((ROOT / 'grafana/dashboards').glob('*.json')):
            dashboard = json.loads(dashboard_path.read_text())
            stored = request(grafana, '/api/dashboards/uid/' + dashboard['uid'], auth=True)['dashboard']
            assert len(stored['panels']) == len(dashboard['panels'])
            # Execute all actual panel queries, expanding Grafana variables to their defaults.
            for panel in dashboard['panels']:
                for target in panel.get('targets', []):
                    expr = target['expr']
                    for key in ('compose_project', 'service', 'container'):
                        expr = expr.replace('${' + key + ':regex}', '.*')
                    expr = expr.replace('${severity:raw}', '.*').replace('${search:raw}', '')
                    expr = expr.replace('$__interval', '1m').replace('$__range', '1h')
                    query(expr, target['queryType'] == 'instant')
            print('Queries passed: ' + dashboard['title'], flush=True)
        # Literal search must retain quotes and backslashes as data.
        search = 'C:\\data "quoted"'
        log_dashboard = json.loads((ROOT / 'grafana/dashboards/docker-logs.json').read_text())
        log_expr = next(p for p in log_dashboard['panels'] if p['id'] == 2)['targets'][0]['expr']
        for key in ('compose_project', 'service', 'container'):
            log_expr = log_expr.replace('${' + key + ':regex}', '.*')
        results = query(log_expr.replace('${severity:raw}', '.*').replace('${search:raw}', search), False)
        assert sum(len(r['values']) for r in results) == 1
        presets = next(v for v in log_dashboard['templating']['list'] if v['name'] == 'severity')['options']
        for preset in presets:
            results = query(log_expr.replace('${severity:raw}', preset['value']).replace('${search:raw}', ''), False)
            count = sum(len(r['values']) for r in results)
            assert count == {'All': 16, 'Errors': 12, 'Warnings': 0, 'Fatal / panic': 1}[preset['text']], (preset['text'], count)
        home = request(grafana, '/api/dashboards/home', auth=True)
        assert home['dashboard']['uid'] == 'home-server-overview'

        def critical_fired():
            groups = request(grafana, '/api/prometheus/grafana/api/v1/rules', auth=True)['data']['groups']
            actual = [rule for group in groups for rule in group['rules'] if rule['name'] == 'Docker container fatal or panic']
            return actual and actual[0]['state'] == 'firing' and actual[0]['health'] == 'ok'

        eventually(critical_fired, timeout=90)
        print('Critical alert fired from the injected panic log.', flush=True)

        def error_burst_fired():
            groups = request(grafana, '/api/prometheus/grafana/api/v1/rules', auth=True)['data']['groups']
            actual = [rule for group in groups for rule in group['rules'] if rule['name'] == 'Docker container error burst']
            return actual and actual[0]['state'] == 'firing' and actual[0]['health'] == 'ok'

        eventually(error_burst_fired, timeout=150)
        print('Error-burst alert fired after the two-minute pending period.', flush=True)
        if args.discord:
            def notification_received():
                payloads = docker('exec', '-T', 'notification-sink', 'python', '-c',
                                  'from pathlib import Path; p=Path("/tmp/notifications.jsonl"); '
                                  'print(p.read_text() if p.exists() else "")')
                return 'Docker container fatal or panic' in payloads and 'fixture-fatal' in payloads
            eventually(notification_received, timeout=60)
            print('Grafana delivered the firing alert to the local Discord receiver.', flush=True)
        print('All observability smoke checks passed.', flush=True)
        if args.keep:
            print('Grafana: ' + grafana + ' (admin / ' + PASSWORD + ')')
            print('Cleanup: ' + ' '.join(command + ['down', '-v', '--remove-orphans']))
    except Exception:
        print(docker('logs', '--tail', '20', 'log-dashboard', 'log-store'), flush=True)
        raise
    finally:
        if not args.keep:
            subprocess.run(command + ['down', '-v', '--remove-orphans'], check=True)
            compose_path.unlink(missing_ok=True)
            temp.rmdir()


if __name__ == '__main__':
    main()
