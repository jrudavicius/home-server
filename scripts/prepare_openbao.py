#!/usr/bin/env python3
"""Install the OpenBao host directories, signed TLS identities, and Docker bridge."""

import argparse
import fcntl
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def owner(value):
    if not re.fullmatch(r'[0-9]+:[0-9]+', value):
        raise argparse.ArgumentTypeError('Use numeric UID:GID')
    return tuple(map(int, value.split(':')))


def set_owner(path, who):
    if (path.stat().st_uid, path.stat().st_gid) != who:
        os.chown(path, *who)


def install_identity(directory, source, name, who):
    expected = {dest: (source / src).read_bytes() for dest, src in
                [('ca.crt', 'ca.crt'), ('cert.pem', name + '.crt'), ('key.pem', name + '.key')]}
    current = directory / 'current'
    if current.is_dir() and all((current / key).is_file() and (current / key).read_bytes() == data
                                for key, data in expected.items()):
        return
    generation = Path(tempfile.mkdtemp(prefix='cert-', dir=directory))
    # All three files become visible together. A running server reloads them on SIGHUP.
    for key, data in expected.items():
        f = generation / key
        f.write_bytes(data)
        f.chmod(0o400 if key == 'key.pem' else 0o444)
        set_owner(f, who)
    set_owner(generation, who)
    pending = directory / ('.next-' + generation.name)
    pending.symlink_to(generation.name)
    pending.replace(current)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('certificates', type=Path, help='signed output of openbao_certificates.sh')
    parser.add_argument('--state-dir', type=Path, default=Path('/srv/server/openbao'))
    parser.add_argument('--network', default='openbao-link')
    parser.add_argument('--server-user', type=owner, default=(10001, 10001))
    parser.add_argument('--backup-user', type=owner, default=(10002, 10002))
    args = parser.parse_args()
    base, source = args.state_dir.resolve(), args.certificates.resolve()
    if not args.state_dir.is_absolute() or base == Path('/') or base == ROOT or ROOT in base.parents:
        parser.error('Choose an absolute, dedicated state directory outside the checkout')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', args.network):
        parser.error('Invalid Docker bridge name')
    if os.geteuid() != 0 and any(who != (os.geteuid(), os.getegid()) for who in (args.server_user, args.backup_user)):
        parser.error('Run as root to install files for different service users')
    if shutil.which('openssl') is None:
        parser.error('OpenSSL is required')
    os.umask(0o077)
    # Verify purpose, names, trust and private key match before touching the running install.
    ca = str(source / 'ca.crt')
    for name, purpose, subject in [('server', 'sslserver', 'openbao-server'), ('backup', 'sslclient', 'openbao-backup')]:
        cert = str(source / (name + '.crt'))
        command('openssl', 'verify', '-x509_strict', '-purpose', purpose, '-verify_hostname', subject, '-CAfile', ca, cert)
        if name == 'server':
            command('openssl', 'verify', '-verify_ip', '127.0.0.1', '-CAfile', ca, cert)
        else:
            cn = command('openssl', 'x509', '-in', cert, '-noout', '-subject', '-nameopt', 'RFC2253')
            if not re.search(r'(?:subject=\s*|,)CN=openbao-backup(?:,|$)', cn):
                parser.error('The client certificate must have CN=openbao-backup')
        public = command('openssl', 'x509', '-in', cert, '-pubkey', '-noout')
        if public != command('openssl', 'pkey', '-in', str(source / (name + '.key')), '-pubout'):
            parser.error(name + ' private key does not match its certificate')
    command('docker', 'info', '--format', '{{.ServerVersion}}')
    base.mkdir(parents=True, exist_ok=True)
    if any(base.iterdir()) and not (base / '.prepare.lock').is_file():
        parser.error('Use an empty, dedicated state directory or one previously prepared for OpenBao')
    with (base / '.prepare.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        trusted = base / 'trust' / 'ca.crt'
        if trusted.exists() and trusted.read_bytes() != Path(ca).read_bytes():
            parser.error('A different CA is already installed. Plan a trust migration before replacing it.')
        for name, who in [('raft', args.server_user), ('audit', args.server_user), ('server-tls', args.server_user),
                          ('backup-tls', args.backup_user), ('snapshots', args.backup_user)]:
            path = base / name
            path.mkdir(exist_ok=True, mode=0o700)
            set_owner(path, who)
            path.chmod(0o700)
        trusted.parent.mkdir(exist_ok=True)
        trusted.parent.chmod(0o755)
        if not trusted.exists():
            with tempfile.NamedTemporaryFile(dir=trusted.parent, delete=False) as tmp:
                tmp.write(Path(ca).read_bytes())
                os.fchmod(tmp.fileno(), 0o444)
            Path(tmp.name).replace(trusted)
        install_identity(base / 'server-tls', source, 'server', args.server_user)
        install_identity(base / 'backup-tls', source, 'backup', args.backup_user)
        if args.network not in command('docker', 'network', 'ls', '--format', '{{.Name}}').splitlines():
            command('docker', 'network', 'create', '--driver', 'bridge', args.network)
        if command('docker', 'network', 'inspect', '--format', '{{.Driver}}/{{.Scope}}', args.network) != 'bridge/local':
            parser.error('The client network must be a local Docker bridge')
    print('OpenBao host directories, certificate pairs and client network are ready.')


if __name__ == '__main__':
    main()
