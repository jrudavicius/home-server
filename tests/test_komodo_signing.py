import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from configure_openbao import seed_signing_secret
import komodo_signing as signing
import prepare_komodo_identity as identity
sys.path.pop(0)


class KomodoSigningTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.session = self.root / 'session'
        self.who = (os.geteuid(), os.getegid())
        # Run the importer's actual in-container shell against fixture inputs.
        docker = self.root / 'docker'
        docker.write_text('#!/bin/sh\nif [ "$1" = inspect ]; then printf "%s" "$FIXTURE_COMMAND"; exit; fi\n'
                          '[ "$1/$2" = exec/fixture ] || exit 1\nshift 2\nexec "$@"\n')
        docker.chmod(0o700)
        self.env = {'PATH': str(self.root) + os.pathsep + os.defpath}

    def test_both_imports_prefer_native_file_and_use_core_whitespace_rules(self):
        secret_file = self.root / 'legacy secret'
        for role, expected in [('jwt', '\x1csession-${TZ}\x1c'), ('webhook', 'webhook-${TZ}')]:
            with self.subTest(role=role):
                name = f'KOMODO_{role.upper()}_SECRET'
                secret_file.write_bytes(('\u3000\t' + expected + '\r\n').encode())
                env = {**self.env, name: 'stale environment value', name + '_FILE': str(secret_file)}
                request = Mock(return_value={})
                with patch.dict(os.environ, env, clear=True):
                    seed_signing_secret(request, 'fixture', role)
                request.assert_called_with('kv/data/komodo/' + role, {'options': {'cas': 0}, 'data': {'secret': expected}})
                secret_file.unlink()
                request.reset_mock()
                with patch.dict(os.environ, env, clear=True), self.assertRaisesRegex(SystemExit, 'Could not read'):
                    seed_signing_secret(request, 'fixture', role)
                request.assert_not_called()

    def test_local_import_is_create_only_and_preserves_literal_environment_data(self):
        value = ' \t${TZ} ž " \\\n\r\n'
        with patch.dict(os.environ, {**self.env, 'KOMODO_JWT_SECRET': value}, clear=True):
            captured = signing.read_core_signer('fixture', 'jwt')
        self.assertEqual(captured, value)
        identity.prepare_session(self.session, self.who, captured)
        cache = self.session / signing.SESSION_FILE
        inode = cache.stat().st_ino
        identity.prepare_session(self.session, self.who, captured)
        with self.assertRaisesRegex(SystemExit, 'differs'):
            identity.prepare_session(self.session, self.who, 'different')
        with self.assertRaisesRegex(SystemExit, 'empty'):
            identity.prepare_session(self.session, self.who, 'new', fresh=True)
        self.assertEqual(inode, cache.stat().st_ino)
        self.assertEqual(signing.cached_session(cache.read_bytes()), value)
        self.assertEqual((stat.S_IMODE(self.session.stat().st_mode), stat.S_IMODE(cache.stat().st_mode)), (0o700, 0o400))

    def test_ambiguous_interpolated_cache_stops_before_kv_write(self):
        cache = self.root / signing.SESSION_FILE
        cache.write_text(json.dumps({'jwt_secret': 'literal-${TZ}'}))
        env = {**self.env, 'KOMODO_CONFIG_PATHS': '/config/bootstrap.json,' + str(cache)}
        request = Mock()
        with patch.object(signing, 'SESSION_PATH', str(cache)), patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(SystemExit, 'interpolates'):
                seed_signing_secret(request, 'fixture', 'jwt')
        request.assert_not_called()

    def test_an_unselected_cache_is_not_an_active_signer(self):
        cache = self.root / signing.SESSION_FILE
        cache.write_text('{"jwt_secret":"unused"}')
        with patch.object(signing, 'SESSION_PATH', str(cache)), \
             patch.dict(os.environ, {**self.env, 'FIXTURE_COMMAND': '["core"]'}, clear=True), \
             self.assertRaisesRegex(SystemExit, 'Cannot identify'):
            signing.read_core_signer('fixture', 'jwt')

    def test_rejects_unrelated_directory_and_links_before_changing_permissions(self):
        self.session.mkdir(mode=0o755)
        private = self.session / 'bootstrap.env'
        private.write_text('unrelated')
        link = self.root / 'alias'
        link.symlink_to(self.session, target_is_directory=True)
        with patch.object(identity, 'private_mode') as change_permissions:
            for directory in (self.session, link, link / 'new'):
                with self.subTest(directory=directory), self.assertRaises(SystemExit):
                    identity.prepare_session(directory, self.who)
            private.rename(self.root / 'other')
            cache = self.session / signing.SESSION_FILE
            cache.symlink_to(self.root / 'other')
            with self.assertRaises(SystemExit):
                identity.prepare_session(self.session, self.who)
            cache.unlink()
            os.link(self.root / 'other', cache)
            with self.assertRaises(SystemExit):
                identity.prepare_session(self.session, self.who)
            cache.unlink()
            cache.write_text('{}')
            with self.assertRaises(SystemExit):
                identity.prepare_session(self.session, self.who)
            change_permissions.assert_not_called()

    def test_failed_first_delivery_preserves_both_existing_caches(self):
        webhook = self.root / 'webhook'
        self.session.mkdir()
        webhook.mkdir()
        session_file = self.session / signing.SESSION_FILE
        session_file.write_text('{"jwt_secret":"before"}')
        webhook_file = webhook / 'signing-secret'
        webhook_file.write_text('original')
        config = {'services': {
            service: {'volumes': [{'type': 'bind', 'source': str(cache), 'target': target}]}
            for service, cache, target in [('session-agent', self.session, '/session'), ('webhook-agent', webhook, '/webhook')]
        }}
        active = {'jwt': 'before', 'webhook': 'original'}

        def render(args, **kwargs):
            stage, target = args[args.index('-v') + 1].split(':')
            if target == '/session':
                (Path(stage) / signing.SESSION_FILE).write_text('{ "jwt_secret": "before" }')
                active['webhook'] = 'different'
            else:
                (Path(stage) / 'signing-secret').write_text(active['webhook'])

        with patch.object(signing, 'read_core_signer', side_effect=lambda _, role: active[role]), \
             patch.object(signing.subprocess, 'check_output', return_value=json.dumps(config)), \
             patch.object(signing.subprocess, 'run', side_effect=render), \
             self.assertRaisesRegex(SystemExit, 'webhook-agent delivered a different signer'):
            signing.verify_deliveries('fixture', ['compose'])
        self.assertEqual(session_file.read_text(), '{"jwt_secret":"before"}')
        self.assertEqual(webhook_file.read_text(), 'original')
        self.assertEqual(list(self.session.iterdir()), [session_file])
        self.assertEqual(list(webhook.iterdir()), [webhook_file])
