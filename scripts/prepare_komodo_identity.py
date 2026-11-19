#!/usr/bin/env python3
"""Prepare a private Pi-local certificate and cache for a Komodo OpenBao Agent."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import tempfile

from komodo_signing import SESSION_FILE, cached_session, read_core_signer
from prepare_openbao import install_identity, owner, set_owner


def private_mode(fd, who, mode):
    metadata = os.fstat(fd)
    if (metadata.st_uid, metadata.st_gid) != who:
        os.fchown(fd, *who)
    os.fchmod(fd, mode)


def prepare_session(directory, who, value=None, *, fresh=False):
    if not directory.is_absolute() or directory == Path('/') or directory.resolve() != directory:
        raise SystemExit('Choose an absolute, dedicated session directory without symlinks.')
    directory.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        entries = os.listdir(fd)
        if entries:
            if entries != [SESSION_FILE]:
                raise SystemExit('Use an empty session directory or one containing only the known signing file.')
            if fresh:
                raise SystemExit('Fresh-install initialization requires an empty session directory.')
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            try:
                cache = os.fdopen(os.open(SESSION_FILE, flags, dir_fd=fd), 'rb')
            except OSError:
                raise SystemExit('The session cache must be a readable regular file without links.') from None
            with cache:
                metadata = os.fstat(cache.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                    raise SystemExit('The session cache must be a regular file without links.')
                existing = cached_session(cache.read())
                if value is not None and existing != value:
                    raise SystemExit('The local session signer differs from Core. The existing file was preserved.')
                private_mode(cache.fileno(), who, 0o400)
        private_mode(fd, who, 0o700)
        if value is not None and not entries:
            with tempfile.NamedTemporaryFile(dir=directory) as output:
                output.write(json.dumps({'jwt_secret': value}, separators=(',', ':')).encode())
                output.flush()
                private_mode(output.fileno(), who, 0o400)
                os.fsync(output.fileno())
                os.link(output.name, SESSION_FILE, dst_dir_fd=fd)
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=Path('/srv/server/openbao'))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--jwt', action='store_true', help='prepare the session signing Agent')
    mode.add_argument('--init-new-session', action='store_true', help='generate a first signing key for a fresh Komodo installation')
    mode.add_argument('--import-session-from-core', metavar='CONTAINER', help='create the local session cache from the existing Core')
    parser.add_argument('--session-dir', type=Path, default=Path('/srv/komodo/session-signing'))
    parser.add_argument('--user', type=owner)
    parser.add_argument('--renew', action='store_true', help='issue a replacement for the existing client certificate')
    args = parser.parse_args()
    local_session = args.init_new_session or args.import_session_from_core
    name = 'komodo-jwt' if args.jwt or local_session else 'komodo-webhook'
    uid = 10004 if name == 'komodo-jwt' else 10003
    who = args.user or (uid, uid)
    state = args.state_dir.resolve()
    ca = state / 'trust/ca.crt'
    if os.geteuid() and who != (os.geteuid(), os.getegid()):
        parser.error('Run as root to install files for another service user')
    os.umask(0o077)
    if local_session:
        if args.renew:
            parser.error('Choose a separate invocation for certificate renewal')
        value = secrets.token_urlsafe(48) if args.init_new_session else read_core_signer(args.import_session_from_core, 'jwt')
        prepare_session(args.session_dir, who, value, fresh=args.init_new_session)
        print('Private session signing file is ready.')
        return
    if not (state / '.prepare.lock').is_file() or not ca.is_file():
        parser.error('Use the existing prepared OpenBao state directory')
    identity = state / (name + '-tls')
    with (state / '.prepare.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.jwt:
            prepare_session(args.session_dir, who)
        directories = [identity] if args.jwt else [identity, state / 'komodo-webhook-cache']
        for directory in directories:
            directory.mkdir(mode=0o700, exist_ok=True)
            set_owner(directory, who)
            directory.chmod(0o700)
        if not (identity / 'current').exists() or args.renew:
            # The operator pins this exact client leaf. The existing CA authenticates the server.
            with tempfile.TemporaryDirectory(dir=state) as temporary:
                release = Path(temporary)
                shutil.copyfile(ca, release / 'ca.crt')
                subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:3072', '-nodes', '-sha256',
                                '-days', '365', '-subj', '/CN=' + name,
                                '-addext', 'basicConstraints=critical,CA:FALSE',
                                '-addext', 'keyUsage=critical,digitalSignature', '-addext', 'extendedKeyUsage=clientAuth',
                                '-keyout', str(release / (name + '.key')), '-out', str(release / (name + '.crt'))],
                               capture_output=True, check=True)
                install_identity(identity, release, name, who)
    print(name + ' client identity and private cache are ready.')


if __name__ == '__main__':
    main()
