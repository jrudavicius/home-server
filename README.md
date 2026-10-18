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
- Running Transmission with internet access protected by the MikroTik's Proton
  WireGuard tunnel and kill switch for the Pi.

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
- Docker Compose plugin.
- A verified MikroTik VPN policy for the Pi at `192.168.88.250` before starting
  Transmission. This stack relies on the router for VPN routing and blocking
  direct internet access; it does not provide a container VPN or kill switch.
  See [router installation and verification](router/README.md).
- On macOS, Docker Desktop.
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
ENTRYPOINT_TRANSMISSION_URL=

GRAFANA_PORT=3000
GRAFANA_TRAEFIK_HOST=grafana.home.arpa
KOMODO_PORT=9120
KOMODO_TRAEFIK_HOST=komodo.home.arpa
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

TRANSMISSION_WEB_PORT=9091
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
`ENTRYPOINT_TRAEFIK_URL`, and `ENTRYPOINT_TRANSMISSION_URL` only when you want
fully custom URLs.

The observability stack stores Loki, Grafana, and Alloy data in Docker-managed
volumes. Loki keeps container logs for 168 hours by default. Increase
`LOKI_RETENTION_PERIOD` only after checking available disk space.

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

Start the media stack manually for local testing:

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
TRANSMISSION_CONFIG_PATH
TRANSMISSION_USER_PASSWORD_FILE
NGROK_INSPECT_PORT
NGROK_DOCKER_NETWORK
```

Create `GRAFANA_ADMIN_PASSWORD` as a secret Komodo variable before deploying
the observability Stack.

Create the directories referenced by those variables on a new host before
deploying the media Stack. Configure and test that host's router VPN policy
before starting Transmission. The Proton private key belongs on the MikroTik;
the media Stack does not mount a WireGuard configuration.
Set the secret `NGROK_AUTHTOKEN` variable in Komodo before deploying the ngrok
Stack. `PLEX_CLAIM` is optional; leave it empty for an unclaimed Plex server, or
set it to a real `claim-...` token in Komodo before the first Plex setup. Komodo
writes the resolved Stack environment to `.env` when deploying.

Transmission uses the shared `portainer_network` Docker bridge. Its web port
is published by `torrent-client`, and Traefik connects to `torrent-client:9091`.
Docker DNS forwards external lookups using the host's DNS configuration.
Traefik reads the configured hostname variables through its file provider.

The MikroTik policy routes internet traffic from `192.168.88.250` through
`wg-proton-pi`, redirects routed DNS queries to Proton, blocks routed IPv6 from
the Pi's protected MAC addresses, and prevents IPv4 fallback to the normal WAN.
The Pi's active interface must retain its DHCP reservation and MAC protection.
Local access on `192.168.88.0/24` remains available. Internet traffic from Plex,
Komodo, ngrok, and the other Pi services also uses Proton, so direct remote
access through the home's public IP needs a separate design.

Before starting Transmission, verify the public IP from both the Pi and a
temporary container on `portainer_network`. With the WireGuard interface
disabled, both must lose IPv4 internet access, including a test that uses a
previously resolved destination IP so DNS failure alone cannot pass the test.
IPv6 internet requests must fail as well. Re-enable WireGuard and verify that
IPv4 access returns. Repeat after a router reboot and when using the backup WAN.

`TRANSMISSION_PEER_PORT` sets the application's listening port. The current
router setup does not implement Proton inbound port forwarding or NAT-PMP lease
renewal. Do not forward this port from the normal WAN. Outbound peer connections
work without an inbound mapping.

### Migrating the media Stack from Gluetun

Keep Transmission stopped while verifying the router policy. Check the active
Stack's Compose file and environment before deploying; Komodo manages its own
checkout, which may differ from a manual checkout on the host. Back up the
existing configuration, and make the Git source used by Komodo match this
configuration so a later redeploy does not restore Gluetun.

Once the router checks pass, stop the old `media-vpn` container to release the
web port. Recreate only the `transmission` service with the updated media
Compose file and the existing Stack environment. The `/config`, `/media`,
`/watch`, and password-secret mounts are unchanged. Deploy the updated entrypoint
configuration so Traefik uses the new backend. Verify container DNS, public IP,
and the web UI before removing the stopped `media-vpn` container. A rollback
requires restoring the old Compose and Traefik files and recreating Transmission
in the Gluetun network; restarting the old container alone does not change its
network mode.

Stop the Komodo bootstrap stack:

```sh
docker compose down
```

## External access and webhooks

The Pi's internet traffic goes through Proton. Use the existing ngrok stack for
inbound webhooks and the entrypoint; direct forwarding from the home WAN is not
part of this setup. See [ngrok configuration](stacks/ngrok/README.md) for endpoint
configuration and the individual Resource Sync and Stack webhook URLs.

```text
webhooks HTTPS URL -> komodo-core:9120
entrypoint URL     -> home-server-proxy:80
```

Set `KOMODO_WEBHOOK_BASE_URL` to the public HTTPS webhook URL. The router must
have a working VPN for ngrok to connect. Local SSH, Komodo, and Transmission
remain reachable when the VPN is down. No host VPN installer, systemd Periphery
migration, or host VPN deployment hook is required; Periphery remains in Docker.

## Notes

- The root Komodo bootstrap network is named `portainer_network`.
- The `entrypoint`, `observability`, and `media` Stacks attach to
  `portainer_network` as an external Docker network so Traefik can route across
  Compose projects.
- Komodo keys and MongoDB data are stored in Docker-managed volumes.
- Loki, Grafana, and Alloy data are stored in Docker-managed volumes.
- Transmission uses the Docker bridge and relies on the MikroTik's VPN policy
  for the Pi. Moving this stack to another host requires equivalent protection.
- Plex, Transmission, media, backup, and periphery paths are expected to be
  provided by the relevant stack `.env` file.
- Timezone is configured as `Europe/Vilnius`.
