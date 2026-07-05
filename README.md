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
- Hosting Plex Media Server through the `media` stack.
- Running Transmission for torrent management through the `media` stack.

## Services

| Service | Container | Purpose |
| --- | --- | --- |
| `komodo-mongo` | `komodo-database` | MongoDB database used by Komodo. |
| `komodo-core` | `komodo-core` | Main Komodo control plane and web UI. |
| `komodo-periphery` | `komodo-agent` | Local Komodo agent connected to Docker on the Raspberry Pi. |
| `traefik` | `home-server-proxy` | Reverse proxy, defined in `stacks/entrypoint/docker-compose.yml`. |
| `entrypoint` | `home-server-entrypoint` | Landing page, defined in `stacks/entrypoint/docker-compose.yml`. |
| `plex` | `media-server` | Plex Media Server, defined in `stacks/media/docker-compose.yml`. |
| `transmission` | `torrent-client` | Transmission torrent client, defined in `stacks/media/docker-compose.yml`. |

## Requirements

- Raspberry Pi running a 64-bit Linux distribution.
- Docker Engine.
- Docker Compose plugin.
- Persistent directories for configuration, media, backups, and transcode data.
- A `.env` file containing the required environment variables.
- A Komodo periphery work directory outside this repository, for example
  `/srv/komodo/periphery`.

## Configuration

Create a `.env` file next to the root `docker-compose.yml` for the Komodo
bootstrap stack:

```env
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
ENTRYPOINT_TRAEFIK_URL=
ENTRYPOINT_TRANSMISSION_URL=

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
PLEX_PORT=
PLEX_TRAEFIK_HOST=
PLEX_CLAIM=
PLEX_CONFIG_PATH=
TRANSCODE_PATH=
MEDIA_PATH=

TRANSMISSION_WEB_PORT=9091
TRANSMISSION_PEER_PORT=51413
TRANSMISSION_TRAEFIK_HOST=
TRANSMISSION_USERNAME=
TRANSMISSION_USER_PASSWORD_FILE=
TRANSMISSION_CONFIG_PATH=
```

Traefik listens on `TRAEFIK_HTTP_PORT`. The landing page links to services using
the current browser hostname and each service's exposed port, so it works before
local DNS is configured.

Traefik also supports hostname routes. Point the hostnames in
`TRAEFIK_DASHBOARD_HOST`, `KOMODO_TRAEFIK_HOST`, `PLEX_TRAEFIK_HOST`, and
`TRANSMISSION_TRAEFIK_HOST` at the Raspberry Pi using your router DNS, Pi-hole,
AdGuard Home, or local hosts files when you want clean local domains.

Set `KOMODO_HOST` to the public URL you use for Komodo. Before local DNS exists,
use the direct server address, such as `http://192.168.1.50:9120`. After DNS is
configured, the default Traefik hostname would be `http://komodo.home.arpa`.

Set `ENTRYPOINT_KOMODO_URL`, `ENTRYPOINT_PLEX_URL`, `ENTRYPOINT_TRAEFIK_URL`,
and `ENTRYPOINT_TRANSMISSION_URL` only when you want fully custom URLs.

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

For Komodo, sync the declarative Stack resources from `komodo/stacks.toml`.
It creates Git-based Stacks named `entrypoint` and `media` on the
`raspberry-pi` server:

```text
Repo: github.com/jrudavicius/home-server
Branch: main
Entrypoint run directory: stacks/entrypoint
Media run directory: stacks/media
Compose file: docker-compose.yml
```

The `media` Stack declares `after = ["entrypoint"]`, so Resource Sync deploys
the reverse proxy and landing page before deploying Plex and Transmission.

Komodo clones over HTTPS, not SSH. If the repository is private, add a GitHub
token account in Komodo and select that account on the Stacks after syncing.
Do this after committing and pushing this repository, otherwise Komodo will
clone the old `main` branch and miss the stack files.

The optional Repo resource in `komodo/repos.toml` creates a visible Komodo
Repo named `home-server` for this Git repository. It is separate from the
Git-backed Stacks and is useful when you want the repository to appear under
Komodo's Repos page.

The Resource Sync in `komodo/syncs.toml` makes Komodo read the `komodo/`
directory from the `home-server` Repo and reconcile the declared resources.
Deletion is disabled so resources not yet represented in TOML, such as the
connected server, are left alone.

To deploy from GitHub pushes, set `KOMODO_WEBHOOK_BASE_URL` to a public HTTPS
URL that can reach Komodo, then add GitHub push webhooks using these payload
URLs:

```text
https://<komodo-public-host>/listener/github/sync/home-server-resources/sync
https://<komodo-public-host>/listener/github/stack/entrypoint/deploy
https://<komodo-public-host>/listener/github/stack/media/deploy
```

Use content type `application/json` and set the GitHub webhook secret to the
same value as `KOMODO_WEBHOOK_SECRET`. Both Stacks have
`webhook_force_deploy = true`, so their Stack webhooks deploy on every push.

Keep `stacks/entrypoint/.env` and `stacks/media/.env` out of Git. The synced
Stack environments reference Komodo variables for host-specific values:

```text
PLEX_CLAIM
PLEX_CONFIG_PATH
TRANSCODE_PATH
MEDIA_PATH
TRANSMISSION_CONFIG_PATH
TRANSMISSION_USER_PASSWORD_FILE
```

Create those variables in Komodo with real local paths/secrets before deploying
on a new host. Komodo writes the resolved environment to `.env` when deploying.

Stop the Komodo bootstrap stack:

```sh
docker compose down
```

## Notes

- The root Komodo bootstrap network is named `portainer_network`.
- The `entrypoint` and `media` Stacks attach to `portainer_network` as an
  external Docker network so Traefik can route across Compose projects.
- Komodo keys and MongoDB data are stored in Docker-managed volumes.
- Plex, Transmission, media, backup, and periphery paths are expected to be
  provided by the relevant stack `.env` file.
- Timezone is configured as `Europe/Vilnius`.
