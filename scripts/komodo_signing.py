#!/usr/bin/env python3
"""Verify both Agents' first deliveries against signing values captured from the running Core."""

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


SESSION_FILE = 'core.config.json'
SESSION_PATH = '/run/komodo-session/' + SESSION_FILE
# Rust str::trim uses the Unicode White_Space property. Python str.strip also
# removes four ASCII record separators, which may be part of a legacy file key.
FILE_WHITESPACE = (' \t\n\v\f\r\x85\xa0\u1680' + ''.join(chr(c) for c in range(0x2000, 0x200b))
                   + '\u2028\u2029\u202f\u205f\u3000')


def signing_value(value, workload):
    if not isinstance(value, str) or not value or '\0' in value:
        raise SystemExit(f'The {workload} signing value must be a nonempty string without NUL.')
    if workload == 'webhook' and (value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise SystemExit('The webhook signing value has control characters or surrounding whitespace. '
                         'Coordinate a replacement with GitHub before switching to file input.')
    return value


def cached_session(data):
    try:
        record = json.loads(data)
    except (UnicodeError, ValueError):
        raise SystemExit('Invalid private session signing file.') from None
    if not isinstance(record, dict) or set(record) != {'jwt_secret'}:
        raise SystemExit('Expected a private session file containing only jwt_secret.')
    return signing_value(record['jwt_secret'], 'jwt')


def read_core_signer(container, workload):
    name = {'jwt': 'KOMODO_JWT_SECRET', 'webhook': 'KOMODO_WEBHOOK_SECRET'}[workload]
    # Send only the selected input over stdout. An explicitly set file pointer,
    # even an unreadable one, takes precedence in the pinned Core.
    command = r'''
if [ "${SIGNER_FILE+x}" ]; then
    printf 'file\n'; cat < "$SIGNER_FILE"
elif [ "${SIGNER+x}" ]; then
    printf 'env\n%s' "$SIGNER"
elif [ "$1" = jwt ]; then
    case ",${KOMODO_CONFIG_PATHS:-${KOMODO_CONFIG_PATH:-}}" in
        *,"$2") printf 'interpolated\n' ;;
        *) printf 'cache\n' ;;
    esac
    cat < "$2"
else
    exit 1
fi'''.replace('SIGNER', name)
    result = subprocess.run(['docker', 'exec', container, 'sh', '-ec', command, 'sh', workload, SESSION_PATH],
                            capture_output=True)
    if result.returncode:
        raise SystemExit(f'Could not read the active {workload} signing value from Core.')
    source, _, data = result.stdout.partition(b'\n')
    if source in (b'cache', b'interpolated'):
        if source == b'cache':
            launch = subprocess.check_output(['docker', 'inspect', '--type', 'container', '--format',
                                              '{{json .Config.Cmd}}', container])
            if json.loads(launch) != ['perl', '/config/start-core.pl']:
                raise SystemExit('Cannot identify the active session signer for this Core command.')
        value = cached_session(data)
        if source == b'interpolated' and re.search(r'\$(?:\{[A-Za-z0-9_]+\}|\([A-Za-z0-9_]+\))', value):
            raise SystemExit('The previous Core config interpolates this signer. Reconcile its effective value before importing.')
        return value
    try:
        value = data.decode('utf-8')
    except UnicodeDecodeError:
        raise SystemExit(f'The {workload} signing value is not UTF-8.') from None
    return signing_value(value.strip(FILE_WHITESPACE) if source == b'file' else value, workload)


def verify_deliveries(container, compose):
    expected = {role: read_core_signer(container, role) for role in ('jwt', 'webhook')}
    services = json.loads(subprocess.check_output(
        [*compose, 'config', '--format', 'json', 'session-agent', 'webhook-agent']))['services']
    # A file-backed Core can share the Agent's cache. Render on the same filesystem
    # and only publish verified outputs, so a failed check also preserves the rollback files.
    deliveries = []
    with ExitStack() as cleanup:
        for role, service, target, filename in [('jwt', 'session-agent', '/session', SESSION_FILE),
                                                ('webhook', 'webhook-agent', '/webhook', 'signing-secret')]:
            mount = next(m for m in services[service]['volumes'] if m['type'] == 'bind' and m['target'] == target)
            cache = Path(mount['source'])
            staging = Path(cleanup.enter_context(tempfile.TemporaryDirectory(dir=cache)))
            owner = cache.stat()
            staged_owner = staging.stat()
            if (staged_owner.st_uid, staged_owner.st_gid) != (owner.st_uid, owner.st_gid):
                os.chown(staging, owner.st_uid, owner.st_gid)
            subprocess.run([*compose, 'run', '--rm', '--no-deps', '-T', '-v', f'{staging}:{target}',
                            service, 'agent', '-config=/config/agent.hcl', '-exit-after-auth'], check=True)
            candidate = staging / filename
            data = candidate.read_bytes()
            value = cached_session(data).encode() if role == 'jwt' else data
            if value != expected[role].encode():
                raise SystemExit(f'{service} delivered a different signer. Keep the existing Core running.')
            deliveries.append((candidate, cache / filename))
        for candidate, destination in deliveries:
            candidate.replace(destination)
    print('Both Agents delivered the signers captured from Core.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', default='management-control-plane')
    parser.add_argument('--env-file', default='/srv/komodo/bootstrap.env', help='bootstrap file selecting the management overlay')
    args = parser.parse_args()
    verify_deliveries(args.core, ['docker', 'compose', '--env-file', args.env_file])
