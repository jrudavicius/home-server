# Gateway GitHub webhook

Caddy on the public gateway receives GitHub HTTPS deliveries and forwards one
exact POST route to Komodo over the existing private WireGuard tunnel. The Pi's
home address can change. Its applications remain private. The ngrok
`public-access` Stack is retained, stopped, as a rollback option.

```text
GitHub -> gateway public IP:443 -> WireGuard -> Pi VPN IP:9120 -> Komodo
```

## Configuration

Use Caddy 2.10.1 or newer; the deployed version and isolated test image are
2.11.9. Debian 13's stock Caddy predates IP certificate support. Install from
the [official stable package repository](https://caddyserver.com/docs/install#debian-ubuntu-raspbian).
The package supplies the `caddy` systemd service and persistent certificate
storage. Preserve that storage across updates.

Install `Caddyfile` as `/etc/caddy/Caddyfile`, copy `webhook.env.example` to
`/etc/caddy/webhook.env`, and set the actual public IPv4 and private Pi upstream.
Install `webhook.conf` as
`/etc/systemd/system/caddy.service.d/webhook.conf`. The environment file should
be owned by root with mode 600. Keep deployment-specific values out of Git.

```sh
sudo caddy adapt --config /etc/caddy/Caddyfile \
  --envfile /etc/caddy/webhook.env --validate >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now caddy
```

Allow inbound TCP 80 and 443 in the existing gateway firewall, preserving SSH,
WireGuard and forwarding rules. Port 80 is used for ACME validation and rejects
ordinary requests. HTTPS accepts only POST to
`/listener/github/procedure/home-server-deploy/main`; all other routes return
404. The original URI comparison also rejects encoded paths, traversal,
suffixes and query strings. Komodo validates the original GitHub HMAC signature.
The gateway does not need the webhook secret. The Caddy admin API stays on
loopback, and request access logging is disabled so signature headers are not
recorded in an access log.

The explicit ACME issuer requests Let's Encrypt's `shortlived` profile for the
IP address. Certificates last 160 hours and Caddy renews them automatically.
Keep Caddy enabled and ports 80/443 reachable. Do not delete
`/var/lib/caddy/.local/share/caddy`; it contains certificate/account state.
`default_sni` selects the IP certificate for clients that omit SNI. No custom
domain, DNS provider token, or separate certificate renewal job is required.

The gateway must reach the private upstream through WireGuard. This is a
connection from the gateway itself, not public-IP forwarding or a new Pi
router port-forward. Preserve the Pi guard's existing gateway peer allowance.

Set the Pi's private `KOMODO_WEBHOOK_BASE_URL` to `https://<gateway-public-ip>`.
Recreate only Core using its existing Compose file, environment and image.
Configure the single GitHub push hook with:

```text
https://<gateway-public-ip>/listener/github/procedure/home-server-deploy/main
```

Keep `application/json`, certificate verification enabled, and the existing
matched webhook secret. Direct Stack, Repo and Resource Sync webhooks stay
disabled. `home-server-deploy` runs four sequential stages: resource sync,
entrypoint, observability and media. The gateway is managed separately from
that Pi Procedure.

## Migration and verification

1. Preserve gateway firewall/configuration and package state, Pi bootstrap
   environment, root Compose, ngrok Compose/environment/image ID, Komodo
   resources, GitHub hook settings and source. Encrypt off-server copies and
   verify decryption and checksums. Preserve the webhook secret privately;
   GitHub does not return it in hook settings.
2. Leave ngrok running while configuring Caddy. Validate the gateway rules with
   `python3 tests/smoke_private_access.py`, then verify the public IP's trusted
   certificate and the deny rules. Unsigned and incorrectly signed deliveries
   to the allowed route must fail without starting a Procedure.
3. Pause the single GitHub hook during source reconciliation. When changing the
   Procedure definition, sync while the Procedure is idle. Validate the four
   stages and private applications before switching the hook's URL.
4. Request a real GitHub push test and confirm HTTP 200, the expected `main`
   commit, and a successful Procedure update. Only then stop the ngrok
   container. Keep its image, private environment and Stack definition.
5. Restart Caddy and verify certificate persistence, service enablement and a
   second real delivery with ngrok stopped. Check private applications and
   Proton egress. Verify delivery reaches Komodo during a bounded Proton outage
   while ordinary egress remains blocked; deployment Git fetches still need
   Proton, so do not trigger an actual deployment during that outage.

Inspect renewal and service errors with `journalctl -u caddy`. A fresh issued
certificate and restart test do not prove a future renewal has occurred.

## Rollback to ngrok

Pause the single GitHub hook and let active deployments finish. Start the
retained `public-access` Stack manually in Komodo. Its exact Compose image and
configuration are still present, and its credential remains in private
bootstrap/Core settings. Query `http://127.0.0.1:4040/api/tunnels` on the Pi and
use the current HTTPS endpoint; an automatically assigned URL can change.

Restore `KOMODO_WEBHOOK_BASE_URL` to that ngrok base and recreate only Core with
its existing image. Restore the hook's URL to the same exact Procedure path,
with its preserved JSON content type, signature secret and TLS verification.
Enable only that hook and test a real push delivery and Procedure completion.
The current four-stage Procedure works with either ingress, so restoring ngrok
does not require reverting unrelated application changes or data.

After successful ngrok delivery, stop/disable Caddy and remove only the
recorded HTTP/HTTPS firewall allowance. Preserve the gateway WireGuard and
SSH rules. A full pre-migration gateway snapshot is available if needed, but
restoring it wholesale would discard subsequent gateway changes. Original Pi,
application-volume and portability recovery archives remain separate.

References: [IP certificates](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability),
[ACME profiles](https://letsencrypt.org/docs/profiles/),
[Caddy TLS](https://caddyserver.com/docs/caddyfile/directives/tls#acme),
[GitHub signature validation](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries).
