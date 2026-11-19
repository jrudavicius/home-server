"""Verify production webhook enrollment, delivery, rotation and sealed startup in the smoke project."""

import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sys

from openbao_backup_checks import Vault, until


ROOT = Path(__file__).resolve().parents[1]
BRANCH_PROBE = b'{"ref":"refs/heads/openbao-smoke-ignore"}'
SEND_PROBE = """
import json, sys, urllib.request, urllib.error
body, signature = json.load(sys.stdin)
req = urllib.request.Request('http://control-plane:9120/listener/github/procedure/home-server-deploy/main',
                             body.encode(), {'X-Hub-Signature-256': 'sha256=' + signature,
                                             'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=4) as res:
        print(res.status)
except urllib.error.HTTPError as error:
    print(error.code)
"""


def exercise_webhook(folder, run, manager, env, configure, vault, operator, unseal_key, uid, gid,
                     original_jwt, session_works):
    state = folder / 'state'
    identity = state / 'komodo-webhook-tls/current'
    run([sys.executable, str(ROOT / 'scripts/prepare_komodo_webhook.py'),
         '--state-dir', str(state), '--user', f'{uid}:{gid}'], env)
    session_dir = folder / 'session-signing'
    run([sys.executable, str(ROOT / 'scripts/prepare_komodo_identity.py'), '--jwt',
         '--state-dir', str(state), '--session-dir', str(session_dir), '--user', f'{uid}:{gid}'], env)

    def compose(*args, **kwargs):
        return run(manager + list(args), env, **kwargs)

    core = compose('ps', '-q', 'control-plane').stdout.strip()
    assert session_works()
    enroll_jwt = configure + ['--komodo-jwt', '--seed-from-core', core]
    run(enroll_jwt, env, data=operator + '\n')
    run(enroll_jwt, env, data=operator + '\n')
    jwt_path = 'kv/data/komodo/jwt'
    stored = vault.request(jwt_path, token=operator)['data']
    assert stored['metadata']['version'] == 1 and stored['data']['secret'] == original_jwt
    session_client = Vault(vault.port, folder / 'ca.crt')
    jwt_identity = state / 'komodo-jwt-tls/current'
    session_client.tls.load_cert_chain(str(jwt_identity / 'cert.pem'), str(jwt_identity / 'key.pem'))
    reader = session_client.request('auth/komodo-jwt/login', {'name': 'komodo-jwt'})['auth']['client_token']
    session_client.expect_denied('kv/data/komodo/webhook', token=reader)
    session_client.expect_denied(jwt_path, {'data': {'secret': 'must-be-denied'}}, token=reader)
    empty = compose('run', '--rm', '--no-deps', 'control-plane', check=False)
    assert empty.returncode and 'session signing file is missing or invalid' in empty.stderr
    compose('up', '-d', '--no-deps', 'session-agent')
    cache_jwt = session_dir / 'core.config.json'
    until('Agent to deliver the original session signer', lambda:
          cache_jwt.is_file() and json.loads(cache_jwt.read_bytes()) == {'jwt_secret': original_jwt})
    modes = compose('exec', '-T', 'session-agent', 'stat', '-c', '%a', '/session/core.config.json', '/session').stdout.split()
    assert modes == ['400', '700'], modes
    enroll = configure + ['--komodo-webhook', '--seed-from-core', core]
    run(enroll, env, data=operator + '\n')
    vault.request('sys/auth/home-admins', {'type': 'userpass'}, operator)
    permissions = {
        'sys/audit': ['read', 'sudo'], 'sys/mounts': ['read'], 'sys/auth': ['read'],
        'kv/data/komodo/webhook': ['read'], 'sys/policies/acl/komodo-webhook': ['create', 'update'],
        'auth/komodo-webhook/certs/komodo-webhook': ['read', 'create', 'update'],
    }
    policy = '\n'.join(f'path "{p}" {{ capabilities = {json.dumps(c)} }}' for p, c in permissions.items())
    vault.request('sys/policies/acl/test-webhook-operator', {'policy': policy}, operator)
    password = secrets.token_urlsafe(24)
    vault.request('auth/home-admins/users/manager', {'password': password, 'token_policies': ['test-webhook-operator']}, operator)
    result = run(enroll + ['--userpass', 'manager', '--userpass-mount', 'home-admins'], env, data=password + '\n')
    assert password not in result.stdout + result.stderr
    path = 'kv/data/komodo/webhook'
    record = vault.request(path, token=operator)['data']
    original = env['KOMODO_WEBHOOK_SECRET']
    assert record['metadata']['version'] == 1 and record['data']['secret'] == original

    client = Vault(vault.port, folder / 'ca.crt')
    client.tls.load_cert_chain(str(identity / 'cert.pem'), str(identity / 'key.pem'))
    token = client.request('auth/komodo-webhook/login', {'name': 'komodo-webhook'})['auth']['client_token']
    assert client.request(path, token=token)['data']['data']['secret'] == original
    for forbidden in ['sys/storage/raft/snapshot', 'kv/data/other', 'kv/metadata/komodo', jwt_path]:
        client.expect_denied(forbidden, token=token)
    client.expect_denied(path, {'data': {'secret': 'must-be-denied'}}, token=token)

    empty = compose('run', '--rm', '--no-deps', 'control-plane', check=False)
    assert empty.returncode and 'secret file is missing or empty' in empty.stderr
    compose('up', '-d', '--no-deps', 'webhook-agent')
    cache = state / 'komodo-webhook-cache/signing-secret'
    until('Agent to deliver the signing secret', lambda: cache.is_file() and cache.read_bytes() == original.encode())
    # Docker Desktop can translate guest permissions on a bind mount. Check
    # the effective mode seen by the service, as on the production Linux host.
    modes = compose('exec', '-T', 'webhook-agent', 'stat', '-c', '%a', '/webhook/signing-secret', '/webhook').stdout.split()
    assert modes == ['400', '700'], modes
    vault.request(path, {'data': {'secret': ''}}, operator)
    mismatch = run(enroll, env, data=operator + '\n', check=False)
    assert mismatch.returncode and 'differs from Core' in mismatch.stderr
    compose('restart', 'webhook-agent')
    until('Agent to reject an empty KV value', lambda:
          'Webhook secret must be a nonempty' in compose('logs', '--no-color', 'webhook-agent').stdout)
    assert cache.read_bytes() == original.encode()
    vault.request(path, {'data': {'secret': original}}, operator)
    compose('restart', 'webhook-agent')
    compose('up', '-d', '--no-deps', 'control-plane')
    migrated = compose('ps', '-q', 'control-plane').stdout.strip()
    assert migrated != core
    until('Migrated Core to accept the existing login session', session_works)
    run(configure + ['--komodo-jwt', '--seed-from-core', migrated], env, data=operator + '\n')

    def status(secret):
        signature = hmac.new(secret.encode(), BRANCH_PROBE, hashlib.sha256).hexdigest()
        result = compose('exec', '-T', 'client', 'python', '-c', SEND_PROBE, check=False,
                         data=json.dumps([BRANCH_PROBE.decode(), signature]))
        return result.stdout.strip()

    until('Core to verify the migrated signing value', lambda: status(original) == '200')
    assert status('wrong-fixture-key') == '401'
    replacement = "changed $ special # ' \\" + original
    vault.request(path, {'data': {'secret': replacement}}, operator)
    # A fresh Agent reads immediately instead of waiting for its KV polling interval.
    compose('restart', 'webhook-agent')
    until('Agent to update the private copy', lambda: cache.read_bytes() == replacement.encode())
    assert status(original) == '200'
    vault.request('sys/seal', {}, operator)
    assert vault.request('sys/seal-status')['sealed']
    try:
        compose('restart', 'webhook-agent', 'session-agent')
        compose('restart', 'control-plane')
        until('Core to use the new signing value while sealed', lambda: status(replacement) == '200')
        assert status(original) == '401'
        assert cache.read_bytes() == replacement.encode()
        until('Sealed startup to preserve the existing Komodo session', session_works)
        assert json.loads(cache_jwt.read_bytes()) == {'jwt_secret': original_jwt}
    finally:
        assert not vault.request('sys/unseal', {'key': unseal_key})['sealed']
    print('PASS: Komodo verified signed webhooks with the OpenBao value before and after a sealed restart.', flush=True)
    print('PASS: the same Komodo session survived the environment migration and a sealed restart.', flush=True)
