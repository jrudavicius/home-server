# Raspberry Pi Server Entry Point

This project is the deployment entry point for a Raspberry Pi based server.
The repository is intentionally small: `docker-compose.yml` defines the
containers that should run on the device.

## Purpose

The Raspberry Pi is used as a lightweight home/server entry point for:

- Managing the stack with Komodo.
- Running a local Komodo periphery agent.
- Hosting Plex Media Server.
- Running Transmission for torrent management.

## Services

| Service | Container | Purpose |
| --- | --- | --- |
| `komodo-mongo` | `komodo-database` | MongoDB database used by Komodo. |
| `komodo-core` | `komodo-core` | Main Komodo control plane and web UI. |
| `komodo-periphery` | `komodo-agent` | Local Komodo agent connected to Docker on the Raspberry Pi. |
| `plex` | `media-server` | Plex Media Server. |
| `transmission` | `torrent-client` | Transmission torrent client. |

## Requirements

- Raspberry Pi running a 64-bit Linux distribution.
- Docker Engine.
- Docker Compose plugin.
- Persistent directories for configuration, media, backups, and transcode data.
- A `.env` file containing the required environment variables.

## Configuration

Create a `.env` file next to `docker-compose.yml` and define the following
values:

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

PERIPHERY_ROOT_DIRECTORY=
DOCKER_SOCKET_PATH=/var/run/docker.sock

PLEX_PORT=
PLEX_CLAIM=
PLEX_CONFIG_PATH=
TRANSCODE_PATH=
MEDIA_PATH=

TRANSMISSION_USERNAME=
TRANSMISSION_USER_PASSWORD_FILE=
TRANSMISSION_CONFIG_PATH=
```

`TRANSMISSION_USER_PASSWORD_FILE` must point to a local file containing the
Transmission password. Docker Compose mounts it as a secret.

## Running

Start the stack:

```sh
docker compose up -d
```

Check container status:

```sh
docker compose ps
```

View logs:

```sh
docker compose logs -f
```

Stop the stack:

```sh
docker compose down
```

## Notes

- The default Docker network is named `portainer_network`.
- Komodo keys and MongoDB data are stored in Docker-managed volumes.
- Plex, Transmission, media, backup, and periphery paths are expected to be
  provided by the `.env` file.
- Timezone is configured as `Europe/Vilnius`.
