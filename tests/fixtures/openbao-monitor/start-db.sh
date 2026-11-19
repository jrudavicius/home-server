#!/bin/sh
set -eu
cp /bootstrap/tls/server.key /run/db-tls/server.key
chown postgres:postgres /run/db-tls/server.key
chmod 600 /run/db-tls/server.key
cp /bootstrap/tls/server.crt /run/db-tls/server.crt
chmod 644 /run/db-tls/server.crt
exec docker-entrypoint.sh postgres \
  -c ssl=on -c ssl_cert_file=/run/db-tls/server.crt \
  -c ssl_key_file=/run/db-tls/server.key -c hba_file=/config/pg_hba.conf
