#!/bin/sh
set -eu
umask 077
ok=0
failed=0
while [ ! -s "$PGSERVICEFILE" ]; do sleep 1; done
while :; do
  if role=$(psql -XwAtq -v ON_ERROR_STOP=1 -d service=monitor \
      -c "SELECT current_user FROM metrics.heartbeat WHERE id = 1") && [ -n "$role" ]; then
    ok=$((ok + 1))
    printf 'sample=%s database_role=%s\n' "$ok" "$role"
  else
    failed=$((failed + 1))
    printf 'database check failed\n' >&2
  fi
  printf '%s %s %s\n' "$ok" "$failed" "$role" >/tmp/counts.new
  mv /tmp/counts.new /tmp/counts
  sleep 1
done
