#!/usr/bin/env python3
"""Configure an unsealed local OpenBao service using an operator token on stdin or a hidden prompt."""

import argparse
import getpass
import json
from pathlib import Path
import ssl
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=Path('/srv/server/openbao'))
    parser.add_argument('--port', type=int, default=18200)
    parser.add_argument('--rotate-backup-identity', action='store_true',
                        help='trust the installed backup certificate and revoke tokens issued by the dedicated backup auth method')
    args = parser.parse_args()
    context = ssl.create_default_context(cafile=str(args.state_dir / 'trust/ca.crt'))
    leaf = (args.state_dir / 'backup-tls/current/cert.pem').read_text()
    token = getpass.getpass('OpenBao operator token: ') if sys.stdin.isatty() else sys.stdin.readline().strip()
    if not token:
        parser.error('An authorized operator token is required')

    def request(path, data=None, *, missing_ok=False):
        req = urllib.request.Request(f'https://127.0.0.1:{args.port}/v1/' + path,
                                     json.dumps(data).encode() if data is not None else None,
                                     {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, context=context, timeout=30) as res:
                return json.loads(res.read() or '{}')
        except urllib.error.HTTPError as exc:
            if missing_ok and exc.code == 404:
                return {}
            errors = json.loads(exc.read() or b'{}').get('errors', [])
            detail = ' '.join(str(e) for e in errors).replace(token, '[redacted]')[:600]
            raise SystemExit(f'OpenBao returned HTTP {exc.code} at {path}. {detail}') from None

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
    enable('sys/auth', 'openbao-backup', 'cert')
    request('sys/policies/acl/openbao-backup', {
        'policy': (ROOT / 'stacks/openbao-backup/snapshot.hcl').read_text()})
    role = 'auth/openbao-backup/certs/openbao-backup'
    previous = request(role, missing_ok=True).get('data', {}).get('certificate', '')
    if previous and previous.strip() != leaf.strip() and not args.rotate_backup_identity:
        parser.error('Use --rotate-backup-identity to replace the backup certificate and retire its existing tokens')
    request(role, {
        'certificate': leaf, 'allowed_common_names': ['openbao-backup'],
        'token_policies': ['openbao-backup'], 'token_no_default_policy': True,
        'token_ttl': '10m', 'token_max_ttl': '30m',
    })
    if args.rotate_backup_identity:
        request('sys/leases/revoke-prefix/auth/openbao-backup/login', {'sync': True})
    print('Verified file auditing and configured KV v2 and the certificate-authenticated backup role.')


if __name__ == '__main__':
    main()
