# Raspberry Pi Server Entry Point

This project is the deployment entry point for a Raspberry Pi based server.
The root `docker-compose.yml` bootstraps Komodo. Application stacks live under
`stacks/` so Komodo can manage them after the server is connected.

## Purpose

The Raspberry Pi is used as a lightweight home/server entry point for:

- Managing the stack with Komodo.
- Running a local Komodo periphery agent.
- Routing local web traffic with Traefik through the `entrypoint` stack.
- Opening a local home server landing page through the `entrypoint` stack.
- Collecting and searching Docker container logs through the `observability`
  stack.
- Exposing Home Server through ngrok for outside access and GitHub webhooks.
- Hosting Plex Media Server through the `media` stack.
- Routing only Transmission through the MikroTik Proton VPN using a dedicated LAN identity.

## Services

| Service | Container | Purpose |
| --- | --- | --- |
| `komodo-mongo` | `komodo-database` | MongoDB database used by Komodo. |
| `komodo-core` | `komodo-core` | Main Komodo control plane and web UI. |
| `komodo-periphery` | `komodo-agent` | Local Komodo agent connected to Docker on the Raspberry Pi. |
| `traefik` | `home-server-proxy` | Reverse proxy, defined in `stacks/entrypoint/docker-compose.yml`. |
| `entrypoint` | `home-server-entrypoint` | Landing page, defined in `stacks/entrypoint/docker-compose.yml`. |
| `grafana` | `observability-grafana` | Log search and dashboards, defined in `stacks/observability/docker-compose.yml`. |
| `loki` | `observability-loki` | Log storage and query API, defined in `stacks/observability/docker-compose.yml`. |
| `alloy` | `observability-alloy` | Docker log collector, defined in `stacks/observability/docker-compose.yml`. |
| `plex` | `media-server` | Plex Media Server, defined in `stacks/media/docker-compose.yml`. |
| `transmission` | `torrent-client` | Transmission torrent client, defined in `stacks/media/docker-compose.yml`. |
| `ngrok` | `home-server-ngrok` | Public tunnel, defined in `stacks/ngrok/docker-compose.yml`. |

## Requirements

- Raspberry Pi running a 64-bit Linux distribution.
- Docker Engine.
- Docker Compose 2.33.1 or newer.
- A wired Linux host for Transmission macvlan networking; Docker Desktop on macOS can validate configuration but cannot run this network.
- The [MikroTik Transmission policy](router/README.md), installed and tested before deploying media.
- Persistent directories for configuration, media, backups, and transcode data.
- A `.env` file containing the required environment variables.
- A Komodo periphery work directory outside this repository, for example
  `/srv/komodo/periphery`.

## Configuration

Create a `.env` file next to the root `docker-compose.yml` for the Komodo
bootstrap stack:

```env
HOST_BIND_ADDRESS=0.0.0.0

KOMODO_DATABASE_USERNAME=
KOMODO_DATABASE_PASSWORD=
KOMODO_IMAGE_TAG=2
KOMODO_PORT=
KOMODO_HOST=
KOMODO_WEBHOOK_BASE_URL=
KOMODO_TRAEFIK_HOST=
KOMODO_INIT_ADMIN_USERNAME=
KOMODO_INIT_ADMIN_PASSWORD=
KOMODO_FIRST_SERVER_NAME=
KOMODO_WEBHOOK_SECRET=
KOMODO_JWT_SECRET=
KOMODO_BACKUPS_PATH=

PERIPHERY_ROOT_DIRECTORY=/srv/komodo/periphery
DOCKER_SOCKET_PATH=/var/run/docker.sock
```

Do not point `PERIPHERY_ROOT_DIRECTORY` at this repository. Komodo uses that
directory for managed Git checkouts, generated environment files, and stack
working state.

Create a `.env` file next to `stacks/entrypoint/docker-compose.yml` for local
manual testing of the entrypoint stack:

```env
TRAEFIK_HTTP_PORT=80
TRAEFIK_DASHBOARD_HOST=traefik.home.arpa
TRAEFIK_LOG_LEVEL=INFO

ENTRYPOINT_TITLE=Home Server
ENTRYPOINT_SUBTITLE=Raspberry Pi services
ENTRYPOINT_KOMODO_URL=
ENTRYPOINT_PLEX_URL=
ENTRYPOINT_GRAFANA_URL=
ENTRYPOINT_TRAEFIK_URL=
ENTRYPOINT_NGROK_URL=
ENTRYPOINT_TRANSMISSION_URL=

GRAFANA_PORT=3000
GRAFANA_TRAEFIK_HOST=grafana.home.arpa
KOMODO_PORT=9120
KOMODO_TRAEFIK_HOST=komodo.home.arpa
NGROK_INSPECT_PORT=4040
PLEX_PORT=32400
PLEX_TRAEFIK_HOST=plex.home.arpa
TRANSMISSION_WEB_PORT=9091
TRANSMISSION_TRAEFIK_HOST=transmission.home.arpa
```

Create a `.env` file next to `stacks/media/docker-compose.yml` for local manual
testing of the media stack:

```env
PLEX_PORT=32400
PLEX_TRAEFIK_HOST=plex.home.arpa
PLEX_CLAIM=
PLEX_CONFIG_PATH=/srv/server/config/plex
TRANSCODE_PATH=/srv/server/cache/plex-transcode
MEDIA_PATH=/srv/server/media

TRANSMISSION_LAN_IP=192.168.88.9
TRANSMISSION_LAN_MAC=02:54:52:00:00:01
TRANSMISSION_DNS=10.2.0.1
TRANSMISSION_PEER_PORT=51413
TRANSMISSION_TRAEFIK_HOST=transmission.home.arpa
TRANSMISSION_USERNAME=julius
TRANSMISSION_USER_PASSWORD_FILE=/srv/server/config/transmission/transmission_user_password.txt
TRANSMISSION_CONFIG_PATH=/srv/server/config/transmission
```

Create a `.env` file next to `stacks/observability/docker-compose.yml` for
local manual testing of the observability stack:

```env
GRAFANA_IMAGE_TAG=13.1.0
LOKI_IMAGE_TAG=3.7.0
ALLOY_IMAGE_TAG=v1.17.0

GRAFANA_PORT=3000
GRAFANA_TRAEFIK_HOST=grafana.home.arpa
GRAFANA_ROOT_URL=http://grafana.home.arpa/
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=
GRAFANA_PLUGINS_PREINSTALL_DISABLED=true
GRAFANA_PLUGINS_PREINSTALL_AUTO_UPDATE=false

LOKI_RETENTION_PERIOD=168h
LOKI_MAX_QUERY_LOOKBACK=168h

DOCKER_SOCKET_PATH=/var/run/docker.sock
```

Create a `.env` file next to `stacks/ngrok/docker-compose.yml` for local manual
testing of the public tunnel stack:

```env
NGROK_AUTHTOKEN=your-ngrok-authtoken
NGROK_INSPECT_PORT=4040
NGROK_DOCKER_NETWORK=portainer_network
```

Traefik listens on `TRAEFIK_HTTP_PORT`. The landing page links to services using
the current browser hostname and each service's exposed port, so it works before
local DNS is configured.

Traefik also supports hostname routes. Point the hostnames in
`TRAEFIK_DASHBOARD_HOST`, `KOMODO_TRAEFIK_HOST`, `GRAFANA_TRAEFIK_HOST`,
`PLEX_TRAEFIK_HOST`, and `TRANSMISSION_TRAEFIK_HOST` at the Raspberry Pi using
your router DNS, Pi-hole, AdGuard Home, or local hosts files when you want clean
local domains.

Set `KOMODO_HOST` to the public URL you use for Komodo. Before local DNS exists,
use the direct server address, such as `http://192.168.1.50:9120`. After DNS is
configured, the default Traefik hostname would be `http://komodo.home.arpa`.

Set `ENTRYPOINT_KOMODO_URL`, `ENTRYPOINT_PLEX_URL`, `ENTRYPOINT_GRAFANA_URL`,
`ENTRYPOINT_TRAEFIK_URL`, `ENTRYPOINT_NGROK_URL`, and
`ENTRYPOINT_TRANSMISSION_URL` only when you want fully custom URLs.

The ngrok card opens the server's local inspection UI on `NGROK_INSPECT_PORT`
(4040 by default). For manual deployments, set this port to the same value in
the entrypoint and ngrok stacks. Komodo uses the shared `NGROK_INSPECT_PORT`
variable for both stacks.

The observability stack stores Loki, Grafana, and Alloy data in Docker-managed
volumes. Loki keeps container logs for 168 hours by default. Increase
`LOKI_RETENTION_PERIOD` only after checking available disk space.

### Grafana dashboards and alerts

Grafana opens **Home Server Overview** by default. It shows five-minute log
counts, containers that are logging, recent errors, and alerts needing attention.
The charts follow the dashboard time range. Stack, service, and container filters
apply to log panels; the alert list always shows all stacks so filtering cannot
hide another service's problem. An existing personal home-dashboard preference
can override the server default; open `/d/home-server-overview` directly if needed.

**Docker Container Logs** keeps its existing URL (`/d/docker-container-logs`).
Use the stack → service → container filters, a severity preset, and literal,
case-sensitive search. Quotes and backslashes are supported; use Explore for
searches containing a backtick. Counts and the timeline follow those same filters.
Logs are newest first, wrapped, and limited to 500 lines; expand a line for its labels
or narrow the time range to find older entries.

Grafana evaluates these provisioned rules every minute, across all Docker logs:

| Rule | Condition | Pending time |
| --- | --- | --- |
| Docker container error burst | At least 10 error-like lines per container in the last 5 minutes | 2 minutes |
| Docker container fatal or panic | At least one fatal, panic, or critical line per container in the last 5 minutes | None |
| Docker log ingestion silent | No Docker logs at all in the last 15 minutes | 5 minutes |

The first two rules recognize common logfmt/JSON severity fields, bracketed or
plain severity markers, and MongoDB `"s":"E"` / `"s":"F"` JSON severity codes.
This is a text heuristic, not a universal application error parser. Adjust the queries if a
service uses a different format or routinely emits harmless error messages.
Containers with logs but no matching errors return zero. No matching streams is
normal for error rules; Loki query failures appear as evaluation errors instead
of being hidden. The silence rule can also fire on a genuinely quiet server.
These rules do not monitor CPU, memory, disk space, container uptime, or a failure
of Grafana/the Raspberry Pi itself.

Alerts stay in Grafana: each rule explicitly selects Grafana 13.1's built-in
`empty` contact point, which has no notification integrations. No email, webhook,
or other external destination is configured, and the existing notification policy
tree is preserved. Keep `empty` without integrations. If upgrading a Grafana data
volume from a version predating that default, create an empty contact point named
`empty` under **Alerting → Contact points** before deploying. To enable delivery
later, create a real contact point and replace `notification_settings.receiver`
in `stacks/observability/grafana/provisioning/alerting/docker-alerts.json`.

Rules link back to their overview panels. Open **Alerting → Alert rules** to
inspect healthy rules, pending/firing instances, and evaluation errors. Rule
thresholds and pending times are Git-managed in `docker-alerts.json`; dashboard
JSON files live under `stacks/observability/grafana/dashboards/`. Edit those files
instead of relying on UI edits that provisioning can overwrite.

After syncing and redeploying the `observability` Stack in Komodo, Grafana loads
the rules at startup. The Stack tracks provisioning files so later rule edits
restart Grafana too. For a manual deployment:

```sh
docker compose --env-file stacks/observability/.env -f stacks/observability/docker-compose.yml up -d
docker compose --env-file stacks/observability/.env -f stacks/observability/docker-compose.yml restart grafana
```

With Docker running, validate the dashboards and alerts in an isolated temporary
Grafana/Loki stack (no access to the host Docker socket or production volumes):

```sh
python3 stacks/observability/tests/smoke.py
```

The smoke test injects sample logs, checks dashboard and alert queries, confirms
the empty notification route, and waits for both immediate critical and delayed
error-burst alerts to fire. Allow about three minutes. It removes its test
containers, network, and volumes when it exits.

`TRANSMISSION_USER_PASSWORD_FILE` must point to a local file containing the
Transmission password. Docker Compose mounts it as a secret. Keep this file to
the password value only, without a trailing newline.

## Running

Start the Komodo bootstrap stack from the repository root:

```sh
docker compose up -d
```

Check Komodo container status:

```sh
docker compose ps
```

View Komodo logs:

```sh
docker compose logs -f
```

Start the entrypoint stack manually for local testing:

```sh
cd stacks/entrypoint
docker compose up -d
```

With the [router policy and Transmission networks](router/README.md) in place
and the entrypoint stack running, start media on the Linux server:

```sh
cd stacks/media
docker compose up -d
```

Start the observability stack manually for local testing:

```sh
cd stacks/observability
docker compose up -d
```

Start the ngrok stack manually for local testing:

```sh
cd stacks/ngrok
docker compose up -d
```

The ngrok inspection UI/API is published at `http://localhost:4040` by default.
The stack starts the endpoints declared in `stacks/ngrok/ngrok.yml`; by default
those are `webhooks`, an HTTPS endpoint that forwards directly to Komodo, and
`entrypoint`, an HTTP endpoint that forwards to Traefik.

For Komodo, sync the declarative Stack resources from `komodo/stacks.toml`.
It creates Git-based Stacks named `entrypoint`, `observability`, `media`, and
`ngrok` on the `home-server` server:

```text
Repo: github.com/jrudavicius/home-server
Branch: main
Entrypoint run directory: stacks/entrypoint
Observability run directory: stacks/observability
Media run directory: stacks/media
Ngrok run directory: stacks/ngrok
Compose file: docker-compose.yml
```

The `observability`, `media`, and `ngrok` Stacks declare
`after = ["entrypoint"]`, so Resource Sync deploys the reverse proxy and landing
page before deploying Grafana, Loki, Alloy, Plex, Transmission, or the public
ngrok endpoints.

Komodo clones over HTTPS, not SSH. If the repository is private, add a GitHub
token account in Komodo and select that account on the Stacks after syncing.
Do this after committing and pushing this repository, otherwise Komodo will
clone the old `main` branch and miss the stack files.

The optional Repo resource in `komodo/repos.toml` creates a visible Komodo
Repo named `home-server` for this Git repository. It is separate from the
Git-backed Stacks and is useful when you want the repository to appear under
Komodo's Repos page.

The Resource Sync in `komodo/syncs.toml` reads the `komodo/` directory directly
from `github.com/jrudavicius/home-server` on `main` and reconciles the declared
resources and non-secret variables. Deletion is disabled so resources not yet
represented in TOML, such as the connected server and local secrets, are left
alone.

To deploy from GitHub pushes, set `KOMODO_WEBHOOK_BASE_URL` to a public HTTPS
URL that can reach Komodo, then add GitHub push webhooks using these payload
URLs:

```text
https://<komodo-public-host>/listener/github/sync/home-server-resources/sync
https://<komodo-public-host>/listener/github/stack/entrypoint/deploy
https://<komodo-public-host>/listener/github/stack/observability/deploy
https://<komodo-public-host>/listener/github/stack/media/deploy
https://<komodo-public-host>/listener/github/stack/ngrok/deploy
```

Use content type `application/json` and set the GitHub webhook secret to the
same value as `KOMODO_WEBHOOK_SECRET`. The Stacks use
`webhook_force_deploy = true`, so their Stack webhooks deploy on every push.

Keep `stacks/entrypoint/.env`, `stacks/observability/.env`,
`stacks/media/.env`, and `stacks/ngrok/.env` out of Git. The non-secret media
and ngrok variables are declared in `komodo/variables.toml` and are synced from
Git:

```text
PLEX_CONFIG_PATH
TRANSCODE_PATH
MEDIA_PATH
TRANSMISSION_LAN_IP
TRANSMISSION_LAN_MAC
TRANSMISSION_DNS
TRANSMISSION_CONFIG_PATH
TRANSMISSION_USER_PASSWORD_FILE
NGROK_INSPECT_PORT
NGROK_DOCKER_NETWORK
```

Create `GRAFANA_ADMIN_PASSWORD` as a secret Komodo variable before deploying
the observability Stack.

Create the directories referenced by those variables before deploying media.
Install and test the [MikroTik Transmission-only VPN policy](router/README.md),
reserve Transmission's LAN identity, and create the external `transmission_lan`
macvlan network on the Pi. The entrypoint stack creates the internal
`transmission_ui` bridge, so it must be deployed before media.

Set the secret `NGROK_AUTHTOKEN` variable in Komodo before deploying ngrok.
`PLEX_CLAIM` is optional; leave it empty for an unclaimed server, or set a real
`claim-...` token before the first Plex setup. Komodo writes the resolved stack
environment to `.env` when deploying.

Transmission has a fixed LAN IP/MAC that MikroTik routes through its existing
Proton WireGuard tunnel. The router's firewall blocks other routed egress,
including WAN fallback when the tunnel fails. IPv6 is disabled in the container
and blocked by MAC on the router; DNS uses Proton's tunnel resolver.

Transmission also joins the internal `transmission_ui` bridge, where Traefik
connects to `torrent-client:9091`. Traefik publishes `TRANSMISSION_WEB_PORT`
(default 9091), preserving direct Pi URLs and hostname routes. Transmission
never joins the ordinary `portainer_network`. Plex, ngrok, Komodo and other
services use ordinary WAN routing. VPN keys stay on the router; Docker does not
need them.

Proton inbound port allocation and NAT-PMP renewal are not configured here.
Transmission can initiate outgoing connections. Do not forward its peer port
from the home WAN; see the router guide for details.

Stop the Komodo bootstrap stack:

```sh
docker compose down
```

## External access and webhooks

Use the existing ngrok stack for inbound webhooks and the entrypoint. See
[ngrok configuration](stacks/ngrok/README.md) for endpoint configuration and the
individual Resource Sync and Stack webhook URLs.

```text
webhooks HTTPS URL -> komodo-core:9120
entrypoint URL     -> home-server-proxy:80
```

Set `KOMODO_WEBHOOK_BASE_URL` to the public HTTPS webhook URL. ngrok uses the
normal Docker network and ordinary WAN routing. Periphery remains in Docker;
no host VPN installer or deployment hook is required.

## Notes

- The root Komodo bootstrap network is named `portainer_network`.
- The `entrypoint`, `observability`, and `media` Stacks attach to
  `portainer_network` as an external Docker network so Traefik can route across
  Compose projects.
- Komodo keys and MongoDB data are stored in Docker-managed volumes.
- Loki, Grafana, and Alloy data are stored in Docker-managed volumes.
- Transmission uses its dedicated macvlan LAN identity for Proton routing and
  an internal bridge for Traefik; there is no VPN container.
- Plex, Transmission, media, backup, and periphery paths are expected to be
  provided by the relevant stack `.env` file.
- Timezone is configured as `Europe/Vilnius`.
