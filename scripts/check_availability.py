#!/usr/bin/env python3
"""Check a public endpoint from outside the Pi, without logging its private URL."""

import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def validate_settings(url, expected_text):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname
            or parsed.username or parsed.password):
        raise ValueError('Set AVAILABILITY_URL to an HTTP(S) URL without embedded credentials.')
    if not expected_text.strip():
        raise ValueError('Set AVAILABILITY_EXPECTED_TEXT to a stable phrase on the healthy page.')


def check_url(url, expected_text):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'home-server-availability-check',
        'ngrok-skip-browser-warning': 'true',
    })
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError(f'Endpoint returned HTTP {response.status}.')
            body = response.read(1024 * 1024).decode('utf-8', errors='replace')
            if expected_text not in body:
                raise RuntimeError('Endpoint did not contain the expected healthy-page text.')
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'Endpoint returned HTTP {error.code}.') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError('Endpoint could not be reached within the timeout.') from None


def main():
    url = os.environ.get('AVAILABILITY_URL', '')
    expected_text = os.environ.get('AVAILABILITY_EXPECTED_TEXT', '')
    try:
        validate_settings(url, expected_text)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    for attempt in range(1, 4):
        try:
            check_url(url, expected_text)
            print('Public endpoint is available and contains the expected text.')
            return 0
        except RuntimeError as error:
            print(f'Attempt {attempt}/3: {error}', file=sys.stderr)
            if attempt < 3:
                time.sleep(10)
    return 1


if __name__ == '__main__':
    sys.exit(main())
