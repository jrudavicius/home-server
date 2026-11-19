#!/bin/sh
# Runs inside the monitor. No password leaves its in-memory files.
set -eu
umask 077
tmp=$(mktemp -d /dev/shm/rotation.XXXXXX)
held=
cleanup() {
  if [ -n "$held" ]; then kill "$held" 2>/dev/null || true; fi
  rm -rf "$tmp"
}
trap cleanup EXIT
trap 'exit 1' INT TERM
fail() { echo "FAIL: $*" >&2; exit 1; }
query() {
  PGSERVICEFILE="$1" psql -XwAtq -v ON_ERROR_STOP=1 -d service=monitor -c "$2"
}
current=/run/issued/service.conf
old="$tmp/old.conf"
deadline=$(( $(date +%s) + 240 ))
while :; do
  if [ -s "$current" ] && [ -s /tmp/counts ]; then
    cp "$current" "$old"
    if snapshot=$(query "$old" "SELECT current_user || ' ' || ceil(extract(epoch FROM rolvaliduntil))::bigint FROM pg_roles WHERE rolname=current_user" 2>/dev/null); then
      read -r olduser expires <<EOF
$snapshot
EOF
      if [ "$expires" -gt "$(( $(date +%s) + 25 ))" ]; then break; fi
    fi
  fi
  [ "$(date +%s)" -lt "$deadline" ] || fail "no working login with sufficient lifetime"
  sleep 1
done
read -r start_ok start_failed start_role </tmp/counts
started=$(awk '{print $22}' /proc/1/stat)
echo "Original login accepted: $olduser"
appname="expiry-check-$$"
PGAPPNAME="$appname" PGSERVICEFILE="$old" psql -XwAtq -v ON_ERROR_STOP=1 \
  -d service=monitor -c 'SELECT pg_sleep(240)' >"$tmp/session.log" 2>&1 &
held=$!
for attempt in 1 2 3 4 5; do
  seen=$(query "$old" "SELECT count(*) FROM pg_stat_activity WHERE usename=current_user AND application_name='$appname'")
  if [ "$seen" = 1 ]; then break; fi
  sleep 1
done
[ "$seen" = 1 ] || fail "could not observe the already-open session"
echo "Holding a database session open through expiry."
replacement=
while [ "$(date +%s)" -lt "$deadline" ]; do
  read -r observed_ok observed_failed observed_role </tmp/counts
  if active=$(query "$current" "SELECT current_user FROM metrics.heartbeat WHERE id=1" 2>/dev/null) \
      && [ -n "$active" ] && [ "$active" != "$olduser" ] && [ "$active" = "$observed_role" ]; then
    if [ -z "$replacement" ]; then echo "Replacement login accepted: $active"; fi
    replacement=$active
    if [ "$(date +%s)" -ge "$expires" ] && ! query "$old" 'SELECT 1' >"$tmp/old.out" 2>"$tmp/denied"; then
      if grep -Eq 'password authentication failed|is not permitted to log in|role .* does not exist' "$tmp/denied" \
        && grep -q 'terminating connection due to administrator command' "$tmp/session.log"; then
        break
      fi
    fi
  fi
  sleep 1
done
[ "$(date +%s)" -lt "$deadline" ] || fail "old login rejection or open-session termination was not confirmed"
wait "$held" 2>/dev/null || true
held=
read -r end_ok end_failed end_role </tmp/counts
[ "$(awk '{print $22}' /proc/1/stat)" = "$started" ] || fail "monitor restarted"
[ "$end_ok" -gt "$start_ok" ] || fail "monitor made no progress"
[ "$end_failed" = "$start_failed" ] || fail "monitor recorded failed samples"
echo "PASS: PostgreSQL rejected the old password and terminated the old session."
echo "PASS: the same monitor process completed $((end_ok - start_ok)) checks with zero failed samples during this test."
