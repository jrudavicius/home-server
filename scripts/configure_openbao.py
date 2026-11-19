#!/usr/bin/env python3
"""Configure an unsealed local OpenBao service using an operator token or userpass login."""

import argparse
import getpass
import json
from pathlib import Path
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

from komodo_signing import read_core_signer

ROOT = Path(__file__).resolve().parents[1]


def seed_signing_secret(request, container, workload):
    value = read_core_signer(container, workload)
    path = 'kv/data/komodo/' + workload
    existing = request(path, missing_ok=True).get('data')
    if existing is not None:
        if (existing.get('data') or {}).get('secret') != value:
            raise SystemExit(f'The existing OpenBao {workload} value differs from Core. Reconcile the two before cutover.')
        return
    # Create-only also protects a soft-deleted version and concurrent operator writes.
    request(path, {'options': {'cas': 0}, 'data': {'secret': value}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=Path('/srv/server/openbao'))
    parser.add_argument('--port', type=int, default=18200)
    parser.add_argument('--userpass', metavar='USERNAME', help='sign in with an OpenBao administrator password')
    parser.add_argument('--userpass-mount', default='userpass', help='mounted path of the username/password auth method')
    parser.add_argument('--rotate-backup-identity', action='store_true',
                        help='trust the installed backup certificate and revoke tokens issued by the dedicated backup auth method')
    roles = parser.add_mutually_exclusive_group()
    roles.add_argument('--komodo-webhook', action='store_true', help='configure the dedicated Komodo webhook role')
    roles.add_argument('--komodo-jwt', action='store_true', help='configure the dedicated Komodo session signing role')
    parser.add_argument('--seed-from-core', metavar='CONTAINER',
                        help='import the selected active signing value from Core using a create-only KV write')
    parser.add_argument('--rotate-komodo-webhook-identity', action='store_true',
                        help='pin the replacement Komodo certificate and revoke tokens from its auth method')
    parser.add_argument('--rotate-komodo-jwt-identity', action='store_true', help='pin the replacement session signing certificate')
    args = parser.parse_args()
    if args.seed_from_core and not (args.komodo_jwt or args.komodo_webhook):
        parser.error('Select a Komodo signing role for --seed-from-core')
    if ((args.rotate_komodo_webhook_identity and not args.komodo_webhook)
            or (args.rotate_komodo_jwt_identity and not args.komodo_jwt)):
        parser.error('Select the corresponding Komodo role for certificate rotation')
    if (args.komodo_webhook or args.komodo_jwt) and args.rotate_backup_identity:
        parser.error('Choose one workload identity per invocation')
    context = ssl.create_default_context(cafile=str(args.state_dir / 'trust/ca.crt'))
    prompt = f'OpenBao password for {args.userpass}: ' if args.userpass else 'OpenBao operator token: '
    credential = getpass.getpass(prompt) if sys.stdin.isatty() else sys.stdin.readline().rstrip('\r\n')
    if not credential:
        parser.error('An OpenBao operator credential is required')
    token = None if args.userpass else credential

    def request(path, data=None, *, missing_ok=False):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        req = urllib.request.Request(f'https://127.0.0.1:{args.port}/v1/' + path,
                                     json.dumps(data).encode() if data is not None else None, headers)
        try:
            with urllib.request.urlopen(req, context=context, timeout=30) as res:
                return json.loads(res.read() or '{}')
        except urllib.error.HTTPError as exc:
            if missing_ok and exc.code == 404:
                return {}
            if not token:
                raise SystemExit(f'OpenBao login returned HTTP {exc.code}. Check the username, password and userpass mount.') from None
            if path.startswith('kv/data/komodo/'):
                raise SystemExit(f'OpenBao returned HTTP {exc.code} at {path}. Check KV permissions and version.') from None
            errors = json.loads(exc.read() or b'{}').get('errors', [])
            detail = ' '.join(str(e) for e in errors).replace(token, '[redacted]')[:600]
            raise SystemExit(f'OpenBao returned HTTP {exc.code} at {path}. {detail}') from None

    if args.userpass:
        mount = urllib.parse.quote(args.userpass_mount.strip('/'), safe='/')
        username = urllib.parse.quote(args.userpass, safe='')
        token = request(f'auth/{mount}/login/{username}', {'password': credential})['auth']['client_token']
    del credential
    try:
        configure_role(args, request)
    finally:
        if args.userpass:
            request('auth/token/revoke-self', {})


def configure_role(args, request):
    if args.komodo_webhook or args.komodo_jwt:
        workload = 'jwt' if args.komodo_jwt else 'webhook'
        name = 'komodo-' + workload
        identity, policy = name + '-tls', f'management/{name}/policy.hcl'
        rotate = args.rotate_komodo_jwt_identity if args.komodo_jwt else args.rotate_komodo_webhook_identity
    else:
        name, identity, policy = 'openbao-backup', 'backup-tls', 'stacks/openbao-backup/snapshot.hcl'
        rotate = args.rotate_backup_identity
    leaf = (args.state_dir / identity / 'current/cert.pem').read_text()

    def enable(path, name, kind, **extra):
        mounts = request(path)['data']
        if name + '/' in mounts:
            current = mounts[name + '/']
            options = current.get('options') or {}
            if current['type'] != kind or any(str(options.get(k)) != str(v)
                                              for k, v in extra.get('options', {}).items()):
                raise SystemExit('Existing mount has different settings at ' + path + '/' + name)
        else:
            request(path + '/' + name, {'type': kind, **extra})

    audit = request('sys/audit')['data'].get('file/', {})
    if audit.get('type') != 'file' or audit.get('options', {}).get('file_path') != '/audit/audit.json':
        raise SystemExit('The declared file audit device is missing. Check the deployed server.hcl.')
    enable('sys/mounts', 'kv', 'kv', options={'version': '2'})
    enable('sys/auth', name, 'cert')
    role = f'auth/{name}/certs/{name}'
    previous = request(role, missing_ok=True).get('data', {}).get('certificate', '')
    if previous and previous.strip() != leaf.strip() and not rotate:
        flag = '--rotate-' + name.removeprefix('openbao-') + '-identity'
        raise SystemExit(f'Use {flag} to replace the {name} certificate and retire its existing tokens')
    if args.seed_from_core:
        seed_signing_secret(request, args.seed_from_core, workload)
    request('sys/policies/acl/' + name, {'policy': (ROOT / policy).read_text()})
    request(role, {
        'certificate': leaf, 'allowed_common_names': [name],
        'token_policies': [name], 'token_no_default_policy': True,
        'token_ttl': '10m', 'token_max_ttl': '30m',
    })
    if rotate:
        request(f'sys/leases/revoke-prefix/auth/{name}/login', {'sync': True})
    print(f'Verified file auditing and configured KV v2 and the certificate-authenticated {name} role.')


if __name__ == '__main__':
    main()
