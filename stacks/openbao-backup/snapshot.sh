#!/bin/sh
set -eu
umask 077
export LC_ALL=C
keep=${OPENBAO_SNAPSHOT_KEEP:-14}
case "$keep" in ''|0|0*|*[!0-9]*) echo 'Snapshot retention must be a positive integer.' >&2; exit 1;; esac
cd /snapshots
exec 9>>.capture.lock
flock 9
# A delayed first login after unseal is normal. Let Komodo report a failed run if it persists.
tries=0
until [ -s /session/token ]; do
  tries=$((tries + 1))
  [ "$tries" -le 30 ] || { echo 'Backup agent has no session. Check seal state and client certificate.' >&2; exit 1; }
  sleep 2
done
tmp=$(mktemp .partial.XXXXXXXX)
trap 'rm -f "$tmp"' EXIT
trap 'exit 1' HUP INT TERM
for attempt in 1 2 3; do
  # Re-read the agent's token if the first request crossed a reauthentication.
  BAO_TOKEN=$(cat /session/token)
  export BAO_TOKEN
  if bao operator raft snapshot save "$tmp"; then break; fi
  [ "$attempt" -lt 3 ] || exit 1
  sleep 2
done
unset BAO_TOKEN
gzip -t "$tmp"
name="openbao-$(date -u +%Y%m%dT%H%M%SZ)-${tmp##*.}.snap"
mv "$tmp" "$name"
# Names sort by UTC timestamp. Keep this capture when two jobs land in the same second.
set -- openbao-????????T??????Z-????????.snap
excess=$(( $# - keep ))
for old in "$@"; do
  [ "$excess" -gt 0 ] || break
  [ "$old" != "$name" ] || continue
  rm -f "./$old"
  excess=$((excess - 1))
done
echo "Saved $name"
