# Komodo session signing

Core signs user sessions with the `jwt_secret` field in its native configuration. Keeping the exact key through a restart preserves unexpired login sessions. The `session-agent` service authenticates to OpenBao with its own pinned certificate. Its policy can read only the application record `kv/komodo/jwt`. The Agent writes a private configuration fragment at `/srv/komodo/session-signing/core.config.json`. Core mounts this directory read-only and loads the fragment alongside its application configuration. [Komodo Core configuration loading](https://github.com/moghtech/komodo/blob/v2.3.3/bin/core/src/config.rs#L113-L167)

## Move an existing signer

1. Keep the old Core container running and leave an authenticated browser tab open. Open the **Servers** page and confirm the Pi is online. The shared management overlay also serves the existing GitHub webhook, so complete its enrollment if it is still using a bootstrap value. [Webhook enrollment](komodo-webhook.md)
2. From the Pi's management checkout, prepare the local client and import the current signer. Enter the OpenBao password at the hidden prompt. Repeating the import accepts an identical KV value and refuses to overwrite a different one.

   ```sh
   sudo python3 scripts/prepare_komodo_identity.py --jwt
   sudo python3 scripts/configure_openbao.py --komodo-jwt --seed-from-core management-control-plane \
     --userpass manager --userpass-mount home-admins
   ```

3. Start the session Agent on its own. The explicit Compose files also work during first enrollment, before the overlay becomes the default. Compare its first delivery to the running legacy Core using this local check. It prints only the result.

   ```sh
   docker compose --env-file /srv/komodo/bootstrap.env -f docker-compose.yml -f docker-compose.openbao.yml up -d --no-deps session-agent
   sudo python3 - <<'PY'
   import json, subprocess
   from pathlib import Path
   cache = Path('/srv/komodo/session-signing/core.config.json')
   old = subprocess.check_output(['docker', 'exec', 'management-control-plane', 'sh', '-ec',
                                  'test -n "$KOMODO_JWT_SECRET" && printf %s "$KOMODO_JWT_SECRET"'])
   if json.loads(cache.read_bytes())['jwt_secret'].encode() != old:
       raise SystemExit('Signing values differ. Keep the existing Core running.')
   print('The private startup file matches the running signer.')
   PY
   ```

4. Once both signing files are ready, select the management overlay in the private bootstrap file if needed, as described in the webhook guide. Wait for deployments to finish, then run `docker compose --env-file /srv/komodo/bootstrap.env up -d --no-deps control-plane`. Reload **Servers** in the same browser session and confirm it can still fetch Pi status without signing in again. Remove the previous session signer assignments and file pointers from the private bootstrap file, other environment files, templates, and plaintext recovery copies.

## Reboot and recovery

The Agent owns the directory (0700) and file (0400) as UID/GID 10004. Core can start from this file while OpenBao is sealed. If the file is missing or empty, startup stops. Unseal OpenBao and start `session-agent` to restore it, or restore the original private directory from an encrypted backup. Then start Core. Generating a new signing key invalidates existing sessions.

The client certificate lasts one year. For renewal, stop `session-agent`, run `sudo python3 scripts/prepare_komodo_identity.py --jwt --renew` and enroll it with `sudo python3 scripts/configure_openbao.py --komodo-jwt --rotate-komodo-jwt-identity --userpass manager --userpass-mount home-admins`. Start the Agent again. The signing value stays in KV throughout certificate renewal.
