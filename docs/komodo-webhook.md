# Supply Komodo’s GitHub webhook signing secret from OpenBao

Komodo Core 2.3.3 reads `KOMODO_WEBHOOK_SECRET_FILE` at startup. An OpenBao Agent in the management project authenticates with its own pinned client certificate and reads one KV v2 entry, `kv/komodo/webhook`. Only the Agent joins the OpenBao bridge. Core mounts the Agent’s output directory read-only. The local copy survives a reboot, so the management UI and deployment webhook can recover while OpenBao awaits its unseal quorum. [Komodo file settings](https://github.com/moghtech/komodo/blob/v2.3.3/config/core.config.toml#L440-L447) · [Komodo guidance for dedicated secret managers](https://komo.do/docs/configuration/variables) · [OpenBao certificate authentication](https://openbao.org/docs/auth/cert/)

## Migrate an existing Pi

Run these commands from the management checkout with the existing Core running and OpenBao unsealed. Keep a signed-in browser tab open on **Servers**. Pause signing-key changes during enrollment. For legacy native file inputs, confirm the files still contain the values in effect at Core's last start. Keep the matching recovery copies in your password manager. If the Agents already run, stop them during verification so the first render has a single writer per cache.

1. Prepare **both** clients, including on standalone installations with a private session cache. Enroll the pinned certificates and seed each KV record from the running Core. The importer reads a configured native secret file with Core's whitespace trimming, then falls back to the literal environment value only when the pointer is absent. It also recognizes the private session cache. Each KV write is create-only. A mismatch stops enrollment.

   ```sh
   sudo python3 scripts/prepare_komodo_identity.py --jwt
   sudo python3 scripts/prepare_komodo_webhook.py
   sudo python3 scripts/configure_openbao.py --komodo-jwt --seed-from-core management-control-plane \
     --userpass manager --userpass-mount home-admins
   sudo python3 scripts/configure_openbao.py --komodo-webhook --seed-from-core management-control-plane \
     --userpass manager --userpass-mount home-admins
   ```

   These commands use the home Pi's administrator and prompt privately for its OpenBao password. Omit the two userpass options to use an operator token. Substitute your Core container, state directory and loopback port where needed. Set matching `OPENBAO_STATE_DIR` and `OPENBAO_NETWORK` in the private bootstrap file. [OpenBao username/password login](https://openbao.org/docs/auth/userpass/)

2. In `/srv/komodo/bootstrap.env`, set `COMPOSE_FILE=docker-compose.yml:docker-compose.openbao.yml`. Append every site override **after** the OpenBao overlay, preserving the order among site files. For example, `docker-compose.yml:docker-compose.openbao.yml:site.yml` keeps Core's `env_file` entries from `site.yml`. The overlay clears the standalone webhook input and selects the mounted webhook file. Remove legacy signer overrides from the site's Core environment and env files so they cannot supply a stale JWT or webhook setting. Future configuration edits take effect when Core is recreated.

3. Verify the first delivery while the old Core is still serving. The verifier captures both current signers in memory, then runs each Agent once to authenticate and render into an empty private directory. It compares both delivered values before installing either startup file. A failed comparison preserves both existing caches. Continue only after the verifier succeeds.

   ```sh
   sudo python3 scripts/komodo_signing.py --core management-control-plane --env-file /srv/komodo/bootstrap.env
   ```

4. When deployment procedures are idle, start both persistent Agents and recreate Core. This briefly interrupts the UI and webhook listener.

   ```sh
   docker compose --env-file /srv/komodo/bootstrap.env up -d --no-deps session-agent webhook-agent
   docker compose --env-file /srv/komodo/bootstrap.env up -d --no-deps control-plane
   ```

   Reload **Servers** in the original browser session and confirm Periphery reconnects. In GitHub's webhook history, redeliver a push for a branch other than `main`. HTTP 200 verifies the signature while the branch filter keeps deployment idle. After both checks, remove obsolete signer assignments and pointers from private environment files, templates and plaintext recovery copies.

## Operation and recovery

- **Reboot or outage.** The Agent retries and serves no requests. Core starts from the last successfully rendered file, including while OpenBao is sealed. If the cache is missing or empty, Core stops before opening the listener. Unseal OpenBao, wait for the Agent to repopulate the cache, and start Core. A replacement host needs the vault and identity restored, or a new enrolled identity, before its first render.
- **Permissions.** The Agent’s key and cache live in separate private directories owned by UID/GID 10003 by default. Keep the public Agent configuration, `management/komodo-webhook/agent.hcl`, readable by that account (mode 0644). The Agent writes the signing file with mode 0400. Treat the cache and its backups as plaintext credentials. Core gets the cache only, and the Agent keeps its OpenBao token in memory. If changing the service account, pass `--user UID:GID` to preparation and set `KOMODO_WEBHOOK_UID` and `KOMODO_WEBHOOK_GID` for Compose.
- **Signing-secret rotation.** Coordinate a quiet window with GitHub. Update the `secret` field of `kv/komodo/webhook` through an authorized private OpenBao session and update the GitHub webhook Secret field to the same value. Verify the new file has been delivered, then restart Core and check the next normal delivery. The Agent periodically rereads static KV secrets. Restarting only the Agent forces an immediate fetch. Restarting Core is what activates a delivered change. [OpenBao Agent template refresh](https://openbao.org/docs/agent-and-proxy/agent/template/)
- **Client certificate renewal.** Check expiry with `sudo openssl x509 -in /srv/server/openbao/komodo-webhook-tls/current/cert.pem -noout -enddate`. Before the one-year expiry, stop the webhook Agent, run `sudo python3 scripts/prepare_komodo_webhook.py --renew` once, then `sudo python3 scripts/configure_openbao.py --komodo-webhook --rotate-komodo-webhook-identity`. Start the Agent and verify it authenticates and delivers the current value. This repins only the webhook role and revokes tokens from its dedicated auth mount. Core can continue using its existing file throughout renewal.
- **Rollback.** To roll back a webhook signing value, restore the KV version matching GitHub, restart `webhook-agent`, verify delivery to its private file, then restart Core and check a GitHub delivery. The session Agent keeps running. To retire the shared overlay entirely, first stop both Agents and restore the matching webhook value to the standalone bootstrap field. Remove the overlay from `COMPOSE_FILE` and recreate only Core. The standalone configuration still reads the private session file.
