# Supply Komodo’s GitHub webhook signing secret from OpenBao

Komodo Core 2.3.3 reads `KOMODO_WEBHOOK_SECRET_FILE` at startup. An OpenBao Agent in the management project authenticates with its own pinned client certificate and reads one KV v2 entry, `kv/komodo/webhook`. Only the Agent joins the OpenBao bridge. Core mounts the Agent’s output directory read-only. The local copy survives a reboot, so the management UI and deployment webhook can recover while OpenBao awaits its unseal quorum. [Komodo file settings](https://github.com/moghtech/komodo/blob/v2.3.3/config/core.config.toml#L440-L447) · [Komodo guidance for dedicated secret managers](https://komo.do/docs/configuration/variables) · [OpenBao certificate authentication](https://openbao.org/docs/auth/cert/)

## Migrate an existing Pi

Run these commands on the Pi from the management Compose checkout containing this integration. Start with the current Core running and OpenBao unsealed. Keep the existing signing value in your password manager for rollback. With a customized installation, use the actual Core container name, `--state-dir`, and loopback `--port`. Set matching `OPENBAO_STATE_DIR` and `OPENBAO_NETWORK` in the private bootstrap file if they differ from the repository defaults.

1. Create the client key and certificate locally, then enroll the public certificate and import the signing value from the running Core. The second command prompts privately for an authorized OpenBao operator token. The client key stays on the Pi. Repeating the import accepts an identical existing value and refuses to overwrite a different value.

   ```sh
   sudo python3 scripts/prepare_komodo_webhook.py
   sudo python3 scripts/configure_openbao.py --komodo-webhook --seed-from-core management-control-plane
   ```

   On the home Pi, the `manager` administrator signs in through the `home-admins` username/password mount. Use this enrollment command and enter the OpenBao password at the hidden prompt. The script uses the login token in memory and revokes that session when it finishes. For another installation, substitute its username and mount. [OpenBao username/password login](https://openbao.org/docs/auth/userpass/)

   ```sh
   sudo python3 scripts/configure_openbao.py --komodo-webhook --seed-from-core management-control-plane \
     --userpass manager --userpass-mount home-admins
   ```

2. Start just the Agent. Wait until its delivered bytes match the active signing value. The comparison prints no credential. A successful comparison exits zero.

   ```sh
   docker compose --env-file /srv/komodo/bootstrap.env -f docker-compose.yml -f docker-compose.openbao.yml up -d --no-deps webhook-agent
   sudo test -s /srv/server/openbao/komodo-webhook-cache/signing-secret &&
     docker exec management-control-plane sh -ec 'test -n "$KOMODO_WEBHOOK_SECRET" && printf %s "$KOMODO_WEBHOOK_SECRET"' |
     sudo cmp -s - /srv/server/openbao/komodo-webhook-cache/signing-secret
   ```

3. After the comparison succeeds, set `COMPOSE_FILE=docker-compose.yml:docker-compose.openbao.yml` in the private `/srv/komodo/bootstrap.env` so future root Compose commands include the Agent. If other override files are already active, preserve them and include the webhook overlay last. Run these commands from the management checkout while its deployment Procedure is idle. Recreating Core briefly interrupts the UI and webhook listener.

   ```sh
   docker compose --env-file /srv/komodo/bootstrap.env config --services
   docker compose --env-file /srv/komodo/bootstrap.env up -d --no-deps control-plane
   docker exec management-control-plane sh -ec 'test -z "${KOMODO_WEBHOOK_SECRET+x}" && test -s "$KOMODO_WEBHOOK_SECRET_FILE"'
   ```

   Verify `webhook-agent` is listed, Core is reachable, and Periphery reconnects. In GitHub’s webhook delivery history, redeliver a push whose `ref` names a branch other than `main`. HTTP 200 verifies the signature through the gateway, and Komodo’s branch filter keeps the deployment Procedure idle. The next normal push to `main` exercises the Procedure. After verifying the signing value and its recovery copy, remove the old `KOMODO_WEBHOOK_SECRET` assignment from the private bootstrap file.

## Operation and recovery

- **Reboot or outage.** The Agent retries and serves no requests. Core starts from the last successfully rendered file, including while OpenBao is sealed. If the cache is missing or empty, Core stops before opening the listener. Unseal OpenBao, wait for the Agent to repopulate the cache, and start Core. A replacement host needs the vault and identity restored, or a new enrolled identity, before its first render.
- **Permissions.** The Agent’s key and cache live in separate private directories owned by UID/GID 10003 by default. Keep the public Agent configuration, `management/komodo-webhook/agent.hcl`, readable by that account (mode 0644). The Agent writes the signing file with mode 0400. Treat the cache and its backups as plaintext credentials. Core gets the cache only, and the Agent keeps its OpenBao token in memory. If changing the service account, pass `--user UID:GID` to preparation and set `KOMODO_WEBHOOK_UID` and `KOMODO_WEBHOOK_GID` for Compose.
- **Signing-secret rotation.** Coordinate a quiet window with GitHub. Update the `secret` field of `kv/komodo/webhook` through an authorized private OpenBao session and update the GitHub webhook Secret field to the same value. Verify the new file has been delivered, then restart Core and check the next normal delivery. The Agent periodically rereads static KV secrets. Restarting only the Agent forces an immediate fetch. Restarting Core is what activates a delivered change. [OpenBao Agent template refresh](https://openbao.org/docs/agent-and-proxy/agent/template/)
- **Client certificate renewal.** Check expiry with `sudo openssl x509 -in /srv/server/openbao/komodo-webhook-tls/current/cert.pem -noout -enddate`. Before the one-year expiry, stop the webhook Agent, run `sudo python3 scripts/prepare_komodo_webhook.py --renew` once, then `sudo python3 scripts/configure_openbao.py --komodo-webhook --rotate-komodo-webhook-identity`. Start the Agent and verify it authenticates and delivers the current value. This repins only the webhook role and revokes tokens from its dedicated auth mount. Core can continue using its existing file throughout renewal.
- **Rollback.** Restore the matching signing value to `KOMODO_WEBHOOK_SECRET` in the private bootstrap file. Stop `webhook-agent` while the overlay is still selected. Remove the webhook overlay from `COMPOSE_FILE` (remove the assignment if only the base file remains). Recreate `control-plane` with the root `up -d --no-deps control-plane` command above. Check a GitHub delivery. The OpenBao record and private cache remain available for another cutover.
