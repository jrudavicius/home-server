#!/bin/sh
set -eu

# Both writers use one compact JSON field. Core parses the fragment after this
# check. A missing key would otherwise let Core choose a new signer on startup.
if ! grep -Eq '^\{"jwt_secret":"[^"]' /run/komodo-session/core.config.json; then
    echo 'Komodo session signing file is missing or invalid' >&2
    exit 1
fi
if [ -n "${KOMODO_WEBHOOK_SECRET_FILE:-}" ] && [ ! -s "$KOMODO_WEBHOOK_SECRET_FILE" ]; then
    echo 'Komodo webhook secret file is missing or empty' >&2
    exit 1
fi
exec core
