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

## External Access From This MacBook

The root compose file publishes Komodo on `HOST_BIND_ADDRESS`, which should be
`0.0.0.0` when it must be reachable from outside the MacBook.

For the current network:

- Public IP: `84.32.117.122`
- MacBook LAN IP: `192.168.0.130`

For direct public-IP access, use these settings in the root `.env`:

```env
HOST_BIND_ADDRESS=0.0.0.0
KOMODO_HOST=http://84.32.117.122:9120
KOMODO_WEBHOOK_BASE_URL=http://84.32.117.122:9120
```

`https://84.32.117.122/` will not work with this compose file alone. That URL
means HTTPS on TCP `443`, but the stack currently publishes the services on
their own HTTP ports:

- Komodo: `http://84.32.117.122:9120`
- Plex: `http://84.32.117.122:32400/web`
- Transmission UI: `http://84.32.117.122:9091`

To make `https://84.32.117.122/` or a normal `https://...` URL work, add a
reverse proxy such as Caddy, Traefik, or Nginx, publish TCP `80` and `443`, and
forward those ports from the router to the MacBook. For browser-trusted HTTPS,
use a DNS name pointed at `84.32.117.122`; IP-only HTTPS usually requires an
internal or self-signed certificate and will show a browser warning.

### Komodo Webhook URLs

The current working ngrok examples use these listener paths:

- `/listener/github/sync/home-server-resources/sync`
- `/listener/github/stack/media/deploy`

With `KOMODO_WEBHOOK_BASE_URL=http://84.32.117.122:9120`, the GitHub webhook
payload URLs are:

```text
http://84.32.117.122:9120/listener/github/sync/home-server-resources/sync
http://84.32.117.122:9120/listener/github/stack/media/deploy
```

If the `entrypoint` stack is also deployed by webhook, use:

```text
http://84.32.117.122:9120/listener/github/stack/entrypoint/deploy
```

These URLs require the router to forward TCP `9120` to `192.168.0.130:9120`.
Using `http://84.32.117.122/listener/...` without `:9120` would hit the port 80
proxy instead; that only works if the proxy routes `/listener` paths to
`komodo-core`.

### Ngrok Port 80 Fallback

When direct public-IP forwarding is not working, use the ngrok tunnel instead.
The current tunnel is:

```text
https://apprehend-crock-backfire.ngrok-free.dev
```

It forwards to the port 80 proxy:

```text
https://apprehend-crock-backfire.ngrok-free.dev/ -> home-server-proxy:80
```

The proxy must route `/listener` paths to Komodo before the catch-all home page
route:

```yaml
komodo:
  rule: "Host(`komodo.home.arpa`) || PathPrefix(`/listener`)"
  entryPoints:
    - web
  priority: 30
  service: komodo
```

With `KOMODO_WEBHOOK_BASE_URL=https://apprehend-crock-backfire.ngrok-free.dev`,
the GitHub webhook payload URLs are:

```text
https://apprehend-crock-backfire.ngrok-free.dev/listener/github/sync/home-server-resources/sync
https://apprehend-crock-backfire.ngrok-free.dev/listener/github/stack/media/deploy
https://apprehend-crock-backfire.ngrok-free.dev/listener/github/stack/entrypoint/deploy
```

The local ngrok inspector is available on:

```text
http://127.0.0.1:4040
```

If GitHub says "failed to connect to host" for one of these URLs and Komodo has
no matching webhook log entry, GitHub did not reach the MacBook. Check the
router before changing Komodo:

- The router's WAN or Internet IP must be `84.32.117.122`.
- TCP `9120` must forward to `192.168.0.130:9120`.
- The forwarding rule must apply to the active WAN interface.
- `192.168.0.130` should be reserved for this MacBook in DHCP so it does not
  change.
- If the router WAN IP is private, such as `10.x.x.x`, `172.16-31.x.x`,
  `192.168.x.x`, or `100.64-127.x.x`, there is another NAT layer upstream and
  direct inbound webhooks will not work without changing that upstream router,
  requesting a public/static IP from the ISP, or using a tunnel such as ngrok.

Then reserve `192.168.0.130` for this MacBook in the router DHCP settings and
forward only the ports you actually need:

| Service | External access URL | Router forward |
| --- | --- | --- |
| Komodo | `http://84.32.117.122:9120` | TCP `9120` to `192.168.0.130:9120` |
| Plex | `http://84.32.117.122:32400/web` | TCP `32400` to `192.168.0.130:32400` |
| Transmission UI | `http://84.32.117.122:9091` | TCP `9091` to `192.168.0.130:9091` |
| Transmission peers | n/a | TCP/UDP `51413` to `192.168.0.130:51413` |

Avoid forwarding the Transmission UI unless it has a strong password and you
really need internet access to it. For admin tools like Komodo and Transmission,
a VPN or HTTPS reverse proxy is safer than direct public HTTP.

### macOS Firewall Checklist

Because this runs on a MacBook, there can be more than one firewall-like layer
between the router and Docker Desktop:

- macOS Application Firewall: System Settings > Network > Firewall. If enabled,
  open Options, keep "Block all incoming connections" off, and allow Docker
  Desktop if macOS asks about incoming connections.
- Local Network privacy: System Settings > Privacy & Security > Local Network.
  If Docker Desktop or the terminal app used to run Compose appears there, allow
  it.
- Packet Filter (`pf`): if a custom `/etc/pf.conf`, VPN client, security agent,
  or MDM profile is installed, make sure it does not block inbound TCP `9120`,
  TCP `32400`, TCP `9091`, or TCP/UDP `51413`.
- Third-party firewalls and VPNs: tools such as LuLu, Little Snitch, corporate
  endpoint security, or VPN "kill switch" features can block inbound traffic
  before Docker sees it.

Useful read-only checks on the MacBook:

```sh
/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
/usr/libexec/ApplicationFirewall/socketfilterfw --getblockall
/usr/libexec/ApplicationFirewall/socketfilterfw --getstealthmode
sudo pfctl -s info
sudo pfctl -sr
```

Useful reachability checks after the stack is running:

```sh
nc -vz 127.0.0.1 9120
nc -vz 192.168.0.130 9120
```

Run the second command from another device on the same network if possible. If
that works but `84.32.117.122:9120` does not work from mobile data or another
outside network, the problem is usually router forwarding, ISP CGNAT, or an
upstream firewall rather than Docker.

If the services work on the MacBook but not from outside, check that the router's
WAN address is actually `84.32.117.122`, macOS Firewall allows Docker Desktop
incoming connections, and the test is from a device outside the home network.

Apple's current firewall and Local Network settings documentation is here:

- [Block connections to your Mac with a firewall](https://support.apple.com/guide/mac-help/block-connections-to-your-mac-with-a-firewall-mh34041/mac)
- [Control access to your local network on Mac](https://support.apple.com/guide/mac-help/control-access-to-your-local-network-on-mac-mchla4f49138/mac)

## Notes

- The root Komodo bootstrap network is named `portainer_network`.
- The `entrypoint` and `media` Stacks attach to `portainer_network` as an
  external Docker network so Traefik can route across Compose projects.
- Komodo keys and MongoDB data are stored in Docker-managed volumes.
- Plex, Transmission, media, backup, and periphery paths are expected to be
  provided by the relevant stack `.env` file.
- Timezone is configured as `Europe/Vilnius`.
