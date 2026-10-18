import contextlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
import io
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/check_availability.py'
spec = importlib.util.spec_from_file_location('availability', SCRIPT)
availability = importlib.util.module_from_spec(spec)
spec.loader.exec_module(availability)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/redirect':
            self.send_response(302)
            self.send_header('Location', '/warning')
            self.end_headers()
            return
        self.send_response(503 if self.path == '/unavailable' else 200)
        self.end_headers()
        body = b'Home Server fixture' if self.path == '/healthy' else b'Tunnel warning'
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class AvailabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_healthy_page_succeeds(self):
        availability.check_url(self.base + '/healthy', 'Home Server')

    def test_wrong_content_and_redirect_to_warning_fail(self):
        for path in ('/warning', '/redirect'):
            with self.subTest(path=path), self.assertRaisesRegex(RuntimeError, 'expected'):
                availability.check_url(self.base + path, 'Home Server')

    def test_http_error_fails_without_exposing_url(self):
        with self.assertRaisesRegex(RuntimeError, '^Endpoint returned HTTP 503.$'):
            availability.check_url(self.base + '/unavailable', 'Home Server')

    def test_invalid_or_missing_configuration_fails(self):
        for url, text in (('', 'Home'), ('file:///etc/passwd', 'Home'),
                          ('https://user:password@example.invalid', 'Home'),
                          (self.base, '   ')):
            with self.subTest(url=url), self.assertRaises(ValueError):
                availability.validate_settings(url, text)

    def run_check(self, results):
        output = io.StringIO()
        with patch.dict(os.environ, {'AVAILABILITY_URL': self.base,
                                    'AVAILABILITY_EXPECTED_TEXT': 'Home Server'}, clear=True), \
                patch.object(availability, 'check_url', side_effect=results) as check, \
                patch.object(availability.time, 'sleep') as sleep, \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = availability.main()
        self.assertNotIn(self.base, output.getvalue())
        return code, check.call_count, sleep.call_count

    def test_transient_failure_retries_and_recovers(self):
        self.assertEqual(self.run_check([RuntimeError('temporary failure'), None]), (0, 2, 1))

    def test_persistent_failure_exits_nonzero(self):
        self.assertEqual(self.run_check([RuntimeError('unavailable')] * 3), (1, 3, 2))
