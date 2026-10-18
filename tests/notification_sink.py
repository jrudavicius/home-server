"""Local Discord-compatible receiver for isolated smoke tests; no outbound calls."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path


class Receiver(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        with Path('/tmp/notifications.jsonl').open('a') as output:
            output.write(json.dumps(body) + '\n')
        self.send_response(204)
        self.end_headers()


if __name__ == '__main__':
    HTTPServer(('0.0.0.0', 8080), Receiver).serve_forever()
