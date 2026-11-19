#!/usr/bin/env python3
"""Prepare a private Pi-local identity and persistent cache for Komodo's webhook Agent."""

import argparse
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from prepare_openbao import install_identity, owner, set_owner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=Path('/srv/server/openbao'))
    parser.add_argument('--user', type=owner, default=(10003, 10003))
    parser.add_argument('--renew', action='store_true', help='issue a replacement for the existing client certificate')
    args = parser.parse_args()
    state = args.state_dir.resolve()
    ca = state / 'trust/ca.crt'
    if not (state / '.prepare.lock').is_file() or not ca.is_file():
        parser.error('Use the existing prepared OpenBao state directory')
    if os.geteuid() and args.user != (os.geteuid(), os.getegid()):
        parser.error('Run as root to install files for another service user')
    os.umask(0o077)
    identity = state / 'komodo-webhook-tls'
    with (state / '.prepare.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for directory in (identity, state / 'komodo-webhook-cache'):
            directory.mkdir(mode=0o700, exist_ok=True)
            set_owner(directory, args.user)
            directory.chmod(0o700)
        if not (identity / 'current').exists() or args.renew:
            # The operator pins this exact client leaf. The existing CA authenticates the server.
            with tempfile.TemporaryDirectory(dir=state) as temporary:
                release = Path(temporary)
                shutil.copyfile(ca, release / 'ca.crt')
                subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:3072', '-nodes', '-sha256',
                                '-days', '365', '-subj', '/CN=komodo-webhook',
                                '-addext', 'basicConstraints=critical,CA:FALSE',
                                '-addext', 'keyUsage=critical,digitalSignature', '-addext', 'extendedKeyUsage=clientAuth',
                                '-keyout', str(release / 'komodo-webhook.key'), '-out', str(release / 'komodo-webhook.crt')],
                               capture_output=True, check=True)
                install_identity(identity, release, 'komodo-webhook', args.user)
    print('Komodo webhook client identity and private cache are ready.')


if __name__ == '__main__':
    main()
