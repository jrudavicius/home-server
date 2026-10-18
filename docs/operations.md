# Operational alerts and validation

The repository provides optional Discord delivery for Komodo and Grafana, an
external HTTP check in GitHub Actions, and configuration CI. Delivery and the
scheduled HTTP check are disabled until you supply their private settings.
No notification account is required to deploy the default configuration.

## What is monitored

| Source | Signals | Default |
| --- | --- | --- |
| Komodo | Failed deployment/backup Procedures, failed Actions/builds, Stack/container state changes, Periphery disconnects, CPU/memory pressure, disk pressure, version mismatch | Alerts visible in Komodo; Discord Alerter disabled |
| Grafana | Repeated container errors, fatal/panic logs, silence in Docker log ingestion | Rules evaluate; receiver `empty` has no integrations |
| GitHub Actions | Public endpoint returns HTTP 200 and expected page text | Scheduled job skipped until enabled |

`komodo/servers.toml` manages the existing `home-server` Server. It enables
statistics and health alerts, with disk warning at **80%** and critical at
**90%** usage. CPU/memory thresholds retain their existing Komodo settings.
Keep `KOMODO_FIRST_SERVER_NAME=home-server`, as required by the Stack definitions.
Connection keys are not declared in TOML and stay in Komodo's server metadata.
Verify the disks reported under **Servers → home-server** include the storage
you use; Periphery can only alert on mounts it can see.

The `home-server-discord` Alerter subscribes to operational failures and host
health across resources. Both managed Procedures already have failure alerts
enabled. A failed deployment inside `home-server-deploy` therefore generates a
Procedure failure; container/Stack state changes cover runtime health.

Core and Grafana cannot send alerts when the entire Pi or its internet
connection is down. The external HTTP check covers availability from outside
the Pi; it cannot distinguish a Pi outage from a tunnel or ISP failure.

## Optional Discord setup

Discord is a supported starting point; you can leave it disabled while choosing
a notification service. To enable it:

1. Create a channel webhook using Discord's
   [webhook instructions](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks).
   Two webhooks allow separate names for Komodo and Grafana; using the same
   webhook for both also works.
2. Put the URLs in the Pi's private `/srv/komodo/bootstrap.env`, never in Git:

   ```dotenv
   KOMODO_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your-id/your-token
   GRAFANA_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your-id/your-token
   ```

   These optional values must be single-line. The bootstrap renderer stores
   Komodo's URL as a native Core secret and prepares Grafana's URL for the
   generated Stack environment. Remove any UI Variables with the same names,
   because they override Core secrets.
3. Update the Pi's checkout and run from the repository root:

   ```sh
   docker compose --env-file /srv/komodo/bootstrap.env up -d
   ```

   This loads the updated secret renderer and restarts Core after the bootstrap
   configuration is prepared. Do this before syncing the new Stack definition,
   including when leaving notification URLs empty.
4. In Git, set `enabled = true` in `komodo/alerters.toml`. In the **observability**
   block of `komodo/stacks.toml`, change the Compose file list to:

   ```toml
   file_paths = ["docker-compose.yml", "docker-compose.discord.yml"]
   ```

   Commit and push those changes, then run the `home-server-deploy` Procedure.
   If its push webhook already runs deployments, wait for that run instead.
   The overlay requires a nonempty Grafana webhook URL and provisions its
   contact point from `grafana/notifications/discord.json`.
5. In Komodo, open **Alerters → home-server-discord** and use **Test**. In Grafana,
   open **Alerting → Contact points → home-server-discord** and send a test.
   Confirm both messages arrive in the intended channel. Check that the three
   Grafana rules select `home-server-discord` and that Komodo shows `home-server`
   connected with current disk statistics.

For manual observability deployments, put `GRAFANA_DISCORD_WEBHOOK_URL` in the
private `stacks/observability/.env`, then use both Compose files:

```sh
docker compose --env-file stacks/observability/.env \
  -f stacks/observability/docker-compose.yml \
  -f stacks/observability/docker-compose.discord.yml up -d
```

Grafana expands the receiver name and webhook URL from container environment
variables during [file provisioning](https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/file-provisioning/).
The existing notification policy tree is preserved. Rule annotations still use
Grafana's alert templates. Keep the `empty` contact point without integrations.

To disable delivery, set the Komodo Alerter back to `enabled = false`, remove
the Discord overlay from the observability file list, then sync and redeploy.
Grafana's rules return to `empty`; an old Discord contact point may remain in
its database but is no longer selected by these rules. To rotate URLs, update
the private bootstrap file, rerun root `up -d`, and manually redeploy observability
so its generated environment is refreshed. Secrets changed outside Git do not
trigger `DeployStackIfChanged`.

## Optional external availability check

After these workflows are on `main`, configure the repository under
**Settings → Secrets and variables → Actions**:

| Setting | Type | Value |
| --- | --- | --- |
| `AVAILABILITY_URL` | Repository secret | Public entrypoint URL, reachable without login |
| `AVAILABILITY_EXPECTED_TEXT` | Repository variable | A stable phrase from the healthy landing page, for example `Raspberry Pi services` |
| `AVAILABILITY_ENABLED` | Repository variable | `true` to enable scheduled checks; absent or `false` disables them |

Use the public landing page that ngrok forwards to Traefik. This needs no new
ingress route. The expected text must match your customized page and should
not appear in a generic tunnel error or login page. The check skips ngrok's
browser warning and follows redirects, but still requires the final page's
status and text to match. It never prints the configured URL.

Open **Actions → Public availability → Run workflow** to verify the settings.
Manual runs always check, even while the scheduled job is disabled. Confirm a
failure run also reaches you: enable GitHub Actions notifications in your
account's [notification settings](https://github.com/settings/notifications),
and temporarily set an incorrect expected phrase for one manual run before
restoring it. No Discord webhook is used by this workflow.

Scheduled checks run every 15 minutes and retry failures three times with a
10-second request timeout and 10-second pauses. GitHub schedules can be delayed;
this is a basic external check, not a guaranteed response time. Public-repository
schedules can be disabled after 60 days of inactivity, and private repositories
use Actions minutes. See GitHub's
[schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
If you later need faster detection or recovery notifications, configure a
dedicated uptime service against the same URL and expected text.

## CI and local verification

`.github/workflows/validate.yml` runs on pull requests, pushes to `main`, and
manual dispatch. It parses all Komodo TOML and stack JSON, checks resource/file/
service/secret references, and renders all five Compose projects plus the
optional Discord overlay with dummy credentials. It enforces image tags and
SHA-256 digests, runs unit tests, and runs three isolated Docker smoke suites:

- Management readiness, network isolation, native alert delivery, and backup/restore.
- Grafana rules and dashboards with the default empty receiver.
- The same Grafana rules with the Discord overlay, checking actual delivery to
  a local receiver after a synthetic fatal log.

CI uses no repository secrets, production volumes, or actual Discord webhooks.
The action dependency is pinned to a commit. Local equivalents require
**Python 3.11+** and **Docker Compose 2.33.1+**, with Docker running for smoke tests:

```sh
python3 scripts/validate_config.py
python3 -m unittest discover -s tests -v
python3 tests/smoke_management.py
python3 stacks/observability/tests/smoke.py
python3 stacks/observability/tests/smoke.py --discord
```

CI does not delay the existing Komodo push webhook. To prevent invalid changes
from reaching `main`, use pull requests and configure repository rules to
require the configuration and all three smoke checks before merging.
