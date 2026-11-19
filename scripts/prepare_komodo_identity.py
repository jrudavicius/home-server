#!/usr/bin/env python3
"""Prepare a private Pi-local certificate and cache for a Komodo OpenBao Agent."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile

from prepare_openbao import install_identity, owner, set_owner


def initialize_session(directory, who):
    directory.mkdir(mode=0o700, exist_ok=True)
    destination = directory / 'core.config.json'
    if destination.exists() or any(directory.iterdir()):
        raise SystemExit('Fresh-install initialization requires an empty session directory.')
    directory.chmod(0o700)
    set_owner(directory, who)
    with tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
        temporary = Path(output.name)
        try:
            value = json.dumps({'jwt_secret': secrets.token_urlsafe(48)}, separators=(',', ':'))
            output.write(value.encode())
            output.flush()
            os.fsync(output.fileno())
            set_owner(temporary, who)
            temporary.chmod(0o400)
            os.link(temporary, destination)  # Create-only, even if another process initialized it.
        finally:
            temporary.unlink(missing_ok=True)
    print('Created a private session signing file for the new Komodo installation.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=Path('/srv/server/openbao'))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--jwt', action='store_true', help='prepare the session signing Agent')
    mode.add_argument('--init-new-session', action='store_true', help='generate a first signing key for a fresh Komodo installation')
    parser.add_argument('--session-dir', type=Path, default=Path('/srv/komodo/session-signing'))
    parser.add_argument('--user', type=owner)
    parser.add_argument('--renew', action='store_true', help='issue a replacement for the existing client certificate')
    args = parser.parse_args()
    name = 'komodo-jwt' if args.jwt or args.init_new_session else 'komodo-webhook'
    uid = 10004 if name == 'komodo-jwt' else 10003
    who = args.user or (uid, uid)
    state = args.state_dir.resolve()
    ca = state / 'trust/ca.crt'
    if os.geteuid() and who != (os.geteuid(), os.getegid()):
        parser.error('Run as root to install files for another service user')
    os.umask(0o077)
    if args.init_new_session:
        if args.renew:
            parser.error('A fresh session key is independent of certificate renewal')
        initialize_session(args.session_dir, who)
        return
    if not (state / '.prepare.lock').is_file() or not ca.is_file():
        parser.error('Use the existing prepared OpenBao state directory')
    identity = state / (name + '-tls')
    cache = args.session_dir if args.jwt else state / 'komodo-webhook-cache'
    with (state / '.prepare.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for directory in (identity, cache):
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
