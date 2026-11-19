"""Exercise backup authorization, retention and restoration using disposable clusters."""

import json
from pathlib import Path
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request


def until(description, check, seconds=120):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(1)
    raise RuntimeError('Timed out waiting for ' + description)


class Vault:
    def __init__(self, port, ca, host='127.0.0.1'):
        self.port = port
        self.url = f'https://{host}:{port}/v1/'
        self.tls = ssl.create_default_context(cafile=str(ca))

    def presents(self, certificate):
        with socket.create_connection(('127.0.0.1', self.port), timeout=5) as connection:
            with self.tls.wrap_socket(connection, server_hostname='127.0.0.1') as handshake:
                return handshake.getpeercert(binary_form=True) == ssl.PEM_cert_to_DER_cert(certificate.read_text())

    def request(self, path, body=None, token='', method=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        headers = {'Content-Type': 'application/octet-stream' if isinstance(body, bytes) else 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        req = urllib.request.Request(self.url + path, data, headers, method=method)
        with urllib.request.urlopen(req, timeout=90, context=self.tls) as res:
            return json.loads(res.read() or b'{}')

    def starting(self):
        try:
            return self.request('sys/init').get('initialized') is False
        except (urllib.error.URLError, ConnectionError):
            return False

    def expect_denied(self, path, body=None, token=''):
        try:
            self.request(path, body, token)
        except urllib.error.HTTPError as error:
            if error.code not in (400, 403):
                raise
            return
        raise AssertionError('Retired or unauthorized identity was accepted at ' + path)

    def initialize(self, until):
        until('fresh OpenBao listener', self.starting)
        keys = self.request('sys/init', {'secret_shares': 1, 'secret_threshold': 1}, method='PUT')
        assert not self.request('sys/unseal', {'key': keys['keys_base64'][0]})['sealed']
        return keys['root_token'], keys['keys_base64'][0]


def backup_and_restore(execute, source, root_token, key, backup_token, snapshots, restore_snapshot):
    marker = 'kv/data/restore-check'
    source.request(marker, {'data': {'generation': 'in-snapshot'}}, root_token)
    paths = ['sys/storage/raft/snapshot', 'sys/storage/raft/snapshot-force', marker]
    permissions = source.request('sys/capabilities', {'token': backup_token, 'paths': paths}, root_token)['data']
    assert permissions[paths[0]] == ['read']
    assert permissions[paths[1]] == ['deny'] and permissions[marker] == ['deny']
    source.expect_denied(marker, token=backup_token)

    for _ in range(3):
        execute('RunProcedure', procedure='Backup OpenBao')
    files = sorted(snapshots.glob('openbao-*.snap'))
    assert len(files) == 2 and all(f.stat().st_size > 0 for f in files)
    assert not list(snapshots.glob('.partial.*'))
    print('Komodo ran the backup Procedure three times and retained two complete test snapshots.', flush=True)
    source.request(marker, {'data': {'generation': 'after-snapshot'}}, root_token)

    restore_snapshot(files[-1], root_token, key)
    assert source.request(marker, token=root_token)['data']['data']['generation'] == 'after-snapshot'
    print('PASS: restored the snapshot into a second cluster and recovered the original KV value.', flush=True)


if __name__ == '__main__':
    # Runs only in the disposable client on the recovery network.
    data = json.load(sys.stdin)
    target = Vault(8200, '/trust/ca.crt', host='openbao-server')
    root_token, key = data['token'], data['key']
    marker = 'kv/data/restore-check'
    temporary_token, _ = target.initialize(until)
    target.request('sys/storage/raft/snapshot-force', (Path('/snapshots') / data['snapshot']).read_bytes(), temporary_token)

    def restored():
        try:
            if target.request('sys/seal-status')['sealed']:
                target.request('sys/unseal', {'key': key})
            return target.request(marker, token=root_token)['data']['data']['generation'] == 'in-snapshot'
        except (urllib.error.URLError, ConnectionError):
            return False

    until('restored marker with the original unseal key', restored)
