# Raspberry Pi Server Entry Point

This project is the deployment entry point for a Raspberry Pi based server.
The root `docker-compose.yml` bootstraps Komodo. Application stacks live under
`stacks/` so Komodo can manage them after the server is connected.

## Purpose

The Raspberry Pi is used as a lightweight home/server entry point for:

- Managing the stack with Komodo.
- Running a local Komodo periphery agent.
- Hosting Plex Media Server through the `media` stack.
- Running Transmission for torrent management through the `media` stack.

## Services

| Service | Container | Purpose |
| --- | --- | --- |
| `komodo-mongo` | `komodo-database` | MongoDB database used by Komodo. |
| `komodo-core` | `komodo-core` | Main Komodo control plane and web UI. |
| `komodo-periphery` | `komodo-agent` | Local Komodo agent connected to Docker on the Raspberry Pi. |
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

Create a second `.env` file next to `stacks/media/docker-compose.yml` for the
media stack:

```env
PLEX_PORT=
PLEX_CLAIM=
PLEX_CONFIG_PATH=
TRANSCODE_PATH=
MEDIA_PATH=

TRANSMISSION_WEB_PORT=9091
TRANSMISSION_PEER_PORT=51413
TRANSMISSION_USERNAME=
TRANSMISSION_USER_PASSWORD_FILE=
TRANSMISSION_CONFIG_PATH=
```

`TRANSMISSION_USER_PASSWORD_FILE` must point to a local file containing the
Transmission password. Docker Compose mounts it as a secret.

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

Start the media stack manually for local testing:

```sh
cd stacks/media
docker compose up -d
```

For Komodo, sync the declarative Stack resource from `komodo/stacks.toml`.
It creates a Git-based Stack named `media` on the `raspberry-pi` server using:

```text
Repo: github.com/jrudavicius/home-server
Branch: main
Run directory: stacks/media
Compose file: docker-compose.yml
```

Komodo clones over HTTPS, not SSH. If the repository is private, add a GitHub
token account in Komodo and select that account on the Stack after syncing.
Do this after committing and pushing this repository, otherwise Komodo will
clone the old `main` branch and miss the stack files.

The optional Repo resource in `komodo/repos.toml` creates a visible Komodo
Repo named `home-server` for this Git repository. It is separate from the
Git-backed `media` Stack and is useful when you want the repository to appear
under Komodo's Repos page.

Keep `stacks/media/.env` out of Git. After the Stack is synced, open the Stack
environment in Komodo and paste the values from `stacks/media/.env.example`
with real local paths/secrets. Komodo will write that environment to `.env`
when deploying.

Stop the Komodo bootstrap stack:

```sh
docker compose down
```

## Notes

- The root Komodo bootstrap network is named `portainer_network`.
- Komodo keys and MongoDB data are stored in Docker-managed volumes.
- Plex, Transmission, media, backup, and periphery paths are expected to be
  provided by the relevant stack `.env` file.
- Timezone is configured as `Europe/Vilnius`.
