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
- Routing the home LAN and server through Proton on MikroTik, with internet blocked if the VPN disconnects.

## Services

Service names describe their role, and every container uses `<stack>-<service>`.
The Compose project name matches the stack name, including `management` for the
root bootstrap stack.

| Stack | Service | Container | Implementation / purpose |
| --- | --- | --- | --- |
| `management` | `secret-bootstrap` | `management-secret-bootstrap` | Prepares private application secrets before Komodo starts. |
| `management` | `database` | `management-database` | MongoDB database used by Komodo. |
| `management` | `control-plane` | `management-control-plane` | Komodo control plane and web UI. |
| `management` | `host-agent` | `management-host-agent` | Komodo agent managing Docker and host resources. |
| `entrypoint` | `reverse-proxy` | `entrypoint-reverse-proxy` | Traefik reverse proxy. |
| `entrypoint` | `landing-page` | `entrypoint-landing-page` | Home server landing page served by nginx. |
| `observability` | `log-dashboard` | `observability-log-dashboard` | Grafana log search and dashboards. |
| `observability` | `log-store` | `observability-log-store` | Loki log storage and query API. |
| `observability` | `log-collector` | `observability-log-collector` | Alloy Docker log collector. |
| `media` | `streaming-server` | `media-streaming-server` | Plex Media Server. |
| `media` | `torrent-client` | `media-torrent-client` | Transmission torrent client. |
| `public-access` | `tunnel` | `public-access-tunnel` | ngrok public access and webhook forwarding. |

Use service names for Compose commands, dependencies, and addresses within a
stack. Use the full container name for addresses between stacks on the shared
Docker network. Tool-specific image names, configuration paths, environment
variables, and public hostnames keep their existing names.

## Requirements

- Raspberry Pi running a 64-bit Linux distribution.
- Docker Engine.
- Docker Compose 2.33.1 or newer.
- A wired Linux host for Transmission macvlan networking; Docker Desktop on macOS can validate configuration but cannot run this network.
- The [MikroTik whole-home VPN policy](router/README.md), including Transmission's dedicated protections, installed and tested before deploying media.
- Persistent directories for configuration, media, backups, and transcode data.
- A private bootstrap environment file, for example `/srv/komodo/bootstrap.env`.
- Komodo variables and server-side secret files described below.
- A Komodo periphery work directory outside this repository, for example
  `/srv/komodo/periphery`.

## Configuration

### Credential setup

Committed files contain empty credential fields or variable references only.
Store actual usernames, passwords, tokens, and private keys in the locations
below. Do not fill them into `bootstrap.env.example`, stack `.env.example`
files, or `komodo/variables.toml`.

#### Komodo bootstrap credentials

Keep the root stack's environment outside the Git checkout at
`/srv/komodo/bootstrap.env`. Komodo needs these credentials before its variable
system is available. On a fresh installation, run the following from the
repository root, then edit the private copy. Do not overwrite an existing
bootstrap file with the example.

```sh
sudo mkdir -p /srv/komodo
test -e /srv/komodo/bootstrap.env || sudo install -o "$(id -u)" -g "$(id -g)" -m 600 bootstrap.env.example /srv/komodo/bootstrap.env
```

Fill all six of these fields in `/srv/komodo/bootstrap.env`:

| Variable | Value to set |
| --- | --- |
| `KOMODO_DATABASE_USERNAME` | MongoDB account used by Komodo. |
| `KOMODO_DATABASE_PASSWORD` | Password for that MongoDB account. |
| `KOMODO_INIT_ADMIN_USERNAME` | Initial Komodo administrator username. |
| `KOMODO_INIT_ADMIN_PASSWORD` | Initial Komodo administrator password. |
| `KOMODO_WEBHOOK_SECRET` | A separate random secret; also enter it in GitHub's webhook Secret field. |
| `KOMODO_JWT_SECRET` | A separate random secret for signing authentication tokens. |

For new installations, generate independent passwords and secrets with your
password manager. Keep a recovery copy there. In environment files, quote
values containing special characters according to the
[Compose environment-file rules](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/#env-file-syntax).

The example supplies the non-secret ports and paths. Keep
`MANAGEMENT_VOLUME_PREFIX` equal to the existing Docker volume prefix (`server`
by default) so Komodo keeps its database and keys. Adjust `KOMODO_HOST` to
your server URL; leave `KOMODO_WEBHOOK_BASE_URL` empty until ngrok is running.
Keep `KOMODO_FIRST_SERVER_NAME=home-server` to match the managed Stack resources.
Use `--env-file /srv/komodo/bootstrap.env` for every root Compose command, as
shown under [Running](#running).

Do not point `PERIPHERY_ROOT_DIRECTORY` at this repository. Komodo uses that
directory for managed Git checkouts, generated environment files, and stack
working state.

#### Managed application credentials

Set these four values in the same private `/srv/komodo/bootstrap.env` file
before starting the root stack. Every value must be nonempty and single-line.

| Bootstrap variable | Value to set | Used by |
| --- | --- | --- |
| `GRAFANA_ADMIN_USER` | Grafana administrator username. | `observability` |
| `GRAFANA_ADMIN_PASSWORD` | Grafana administrator password. | `observability` |
| `TRANSMISSION_USERNAME` | Transmission web UI username. | `media` |
| `NGROK_AUTHTOKEN` | Your authentication token from the ngrok dashboard. | `public-access` |

Optional `KOMODO_DISCORD_WEBHOOK_URL` and `GRAFANA_DISCORD_WEBHOOK_URL` values can
stay empty. See [operational alerts](docs/operations.md) for opt-in delivery.

On `docker compose --env-file /srv/komodo/bootstrap.env up -d`, the
`secret-bootstrap` service validates the values and writes a private JSON
configuration into the `komodo-bootstrap-config` Docker volume. The directory
has mode `700` and the file has mode `600`. Komodo mounts it read-only and waits
for preparation to succeed before starting. No API key or manual variable
creation is needed. The initializer has no network access and logs no values.

These are native **Core secrets**, visible by name under **Settings → Variables**;
their values cannot be read through Komodo's API. `komodo/stacks.toml` references
them using `[[VARIABLE_NAME]]`, and `komodo/variables.toml` deliberately omits
them. Keep these references unquoted: the initializer supplies the quoting and
escaping needed for Compose environment files. See
[Variables and Secrets](https://komo.do/docs/configuration/variables).
The optional native Komodo Alerter URL is stored directly as a Core secret,
without Stack environment-file quoting.

Komodo writes the resolved Stack environment to a deployment `.env` file. The
values remain on the server, so restrict access to the periphery working
directory and its backups. Editing that generated `.env` is temporary: set
credentials in `/srv/komodo/bootstrap.env` instead. After changing a value,
rerun the root `up -d` command, then redeploy the affected application Stack.
The generated configuration contains credentials too, so protect the Docker
volume and its backups. See
[Komodo Compose deployment](https://komo.do/docs/deploy/compose).

#### Server-side secret files

Create the Transmission password file on the Docker host before deploying
`media`. Its path is non-secret and is declared in `komodo/variables.toml`.

| Path variable | Default server path | File contents |
| --- | --- | --- |
| `TRANSMISSION_USER_PASSWORD_FILE` | `/srv/server/config/transmission/transmission_user_password.txt` | Only the Transmission password, without a trailing newline. |

Keep this file outside the checkout. Restrict it to the deployment account
and the container user/root that reads it; use mode `600` where that ownership
allows it. Compose mounts it as a secret. The Transmission password belongs
in its file, not in a Komodo password variable. WireGuard credentials stay on
the MikroTik router; the media stack does not need a VPN key file.

`PLEX_CLAIM` is optional. For first-time setup, set it in
`/srv/komodo/bootstrap.env`, rerun the root `up -d` command, and deploy `media`.
After claiming Plex, clear it and repeat those commands. The initializer
always provides this Core secret, including when empty; the Stack reference
stays `PLEX_CLAIM=[[PLEX_CLAIM]]`. For manual deployments, use the private
media `.env` file instead.

#### Existing installations

Preserve your current credentials during this migration. If the root stack
already uses a `.env`, copy its full contents to `/srv/komodo/bootstrap.env`,
make that file readable only by the deployment account (`chmod 600`), and
switch root Compose commands to the explicit `--env-file` path.

Add the four application values above using your existing usernames, Grafana
password, and ngrok token. Add `PLEX_CLAIM=` unless you need a current claim
token. Preserve existing non-secret settings and `MANAGEMENT_VOLUME_PREFIX`.
Run the root `up -d` command to prepare and load the Core secrets before syncing
the updated application Stacks.

If editable variables with the same names already exist in Komodo's UI, they
override Core secrets. After the root stack starts successfully, remove those
duplicate UI variables so the bootstrap file becomes the source of truth,
then sync and redeploy the affected Stacks. Resource Sync has deletion disabled
and will not remove these duplicates for you. Keep the server-side Transmission
password file in place.

Moving settings does not rotate credentials or rename existing accounts.
MongoDB, Komodo, and Grafana administrator initialization settings do not update
existing accounts; use each application's account-management flow for later
password changes and keep the private bootstrap file consistent.

#### Manual application deployments

For manual testing, copy each stack's `.env.example` to `.env` in that stack's
directory and fill the same credentials there. Set file permissions before
adding values:

```sh
umask 077
cp -n .env.example .env
chmod 600 .env
```

The `-n` option preserves an existing file. A local `.env` is used by manual
Compose commands; Komodo uses the Core secrets loaded by the root stack. Git
ignores runtime `.env` variants, `*.env` files, local `secrets/` and `.secrets/`
directories, and the default Transmission password filename. The committed
`bootstrap.env.example` and stack `.env.example` templates remain available
with empty credential fields.

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
TRANSMISSION_USERNAME=
TRANSMISSION_USER_PASSWORD_FILE=/srv/server/config/transmission/transmission_user_password.txt
TRANSMISSION_CONFIG_PATH=/srv/server/config/transmission
```

Create a `.env` file next to `stacks/observability/docker-compose.yml` for
local manual testing of the observability stack:

```env
GRAFANA_PORT=3000
GRAFANA_TRAEFIK_HOST=grafana.home.arpa
GRAFANA_ROOT_URL=http://grafana.home.arpa/
GRAFANA_ADMIN_USER=
GRAFANA_ADMIN_PASSWORD=
GRAFANA_PLUGINS_PREINSTALL_DISABLED=true
GRAFANA_PLUGINS_PREINSTALL_AUTO_UPDATE=false

LOKI_RETENTION_PERIOD=168h
LOKI_MAX_QUERY_LOOKBACK=168h

DOCKER_SOCKET_PATH=/var/run/docker.sock
```

Create a `.env` file next to `stacks/public-access/docker-compose.yml` for local
manual testing of the public tunnel stack:

```env
NGROK_AUTHTOKEN=
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

The Tunnel card opens the server's local inspection UI on `NGROK_INSPECT_PORT`
(4040 by default). For manual deployments, set this port to the same value in
the `entrypoint` and `public-access` stacks. Komodo uses the shared
`NGROK_INSPECT_PORT` variable for both stacks.

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

By default, alerts stay in Grafana: `GRAFANA_ALERT_RECEIVER=empty` selects Grafana
13.1's built-in contact point without notification integrations. Keep `empty`
without integrations. If upgrading a Grafana data
volume from a version predating that default, create an empty contact point named
`empty` under **Alerting → Contact points** before deploying. The optional
`docker-compose.discord.yml` overlay provisions Discord delivery while preserving
the existing notification policy tree. Follow [operational alerts](docs/operations.md)
to enable it using a private webhook URL.

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
docker compose --env-file stacks/observability/.env -f stacks/observability/docker-compose.yml restart log-dashboard
```

With Docker running, validate the dashboards and alerts in an isolated temporary
Grafana/Loki stack (no access to the host Docker socket or production volumes):

```sh
python3 stacks/observability/tests/smoke.py
```

The smoke test injects sample logs, checks dashboard and alert queries, confirms
the empty notification route, and waits for both immediate critical and delayed
error-burst alerts to fire. Allow about three minutes. It removes its test
containers, network, and volumes when it exits. It reads the image pins directly
from the observability Compose file, so it exercises the deployed versions.
Add `--discord` to verify optional delivery against a local fake Discord receiver.

## Operational alerts and CI

[Operational alerts and validation](docs/operations.md) covers Komodo host-health
and deployment-failure alerts, optional Discord delivery for both Komodo and
Grafana, the external availability check, and CI setup. Disk alerts warn at 80%
and become critical at 90%. External delivery and scheduled availability checks
remain disabled until configured. CI validates configuration and runs the unit
and isolated Docker smoke tests on pull requests and pushes to `main`.

## Image versions and updates

All twelve service images use an exact release tag plus a registry digest in
their Compose files (`image: repository:version@sha256:...`). The digest fixes
the image contents even if the publisher moves a tag. The pins use manifest
lists/image indexes with Linux ARM64 support, so Docker selects the Raspberry
Pi image while retaining support for other published architectures. Registry
references and ARM64 availability were verified on 2026-10-18.

Komodo Core and Periphery are both pinned to **2.3.3**. Update their two image
references together in the root `docker-compose.yml`. Other management images
are pinned there too; application image pins live in each Stack's Compose file.
See [Komodo releases](https://github.com/moghtech/komodo/releases) and
[Docker image digests](https://docs.docker.com/dhi/explore/security-concepts/digests/).

Image selection is Git-managed. The old `KOMODO_IMAGE_TAG`, `GRAFANA_IMAGE_TAG`,
`LOKI_IMAGE_TAG`, and `ALLOY_IMAGE_TAG` environment settings are no longer used.
Remove those entries from existing private environment files; keep their
credentials and other settings. Changing a tag variable or running `pull` alone
does not upgrade a pinned image. `auto_pull = true` remains useful for fetching
the exact image selected by the committed digest.

To update deliberately:

1. Choose the next supported release and review its migration notes. For Core
   and Periphery, choose the same release for both. Inspect each candidate:

   ```sh
   docker buildx imagetools inspect ghcr.io/moghtech/komodo-core:2.3.3
   docker buildx imagetools inspect ghcr.io/moghtech/komodo-periphery:2.3.3
   ```

   Replace the example version with the candidate. Confirm `linux/arm64` is
   present and use the **top-level Digest** for the image index, not an individual
   architecture's child digest.
2. Edit the relevant `image:` references, updating both tag and digest. Validate
   Compose using the deployment's environment file and `config --quiet`. Run
   the observability smoke test when updating Grafana or Loki, and the
   [management smoke test](#management-readiness-and-network-isolation) when
   updating MongoDB, Core, or Periphery. Confirm a usable backup before upgrades
   that can change persistent data.
3. Commit the reviewed pins. Application Compose changes are deployed through
   `home-server-deploy` after they reach `main`. For the management stack, run
   these commands from a host terminal in the updated repository checkout:

   ```sh
   docker compose --env-file /srv/komodo/bootstrap.env pull
   docker compose --env-file /srv/komodo/bootstrap.env up -d
   docker compose --env-file /srv/komodo/bootstrap.env ps
   ```

4. Verify Komodo login, the `home-server` connection, and the affected service.
   To roll back, restore the previous image references from Git and redeploy.
   If the upgrade migrated stored data, follow the application's supported
   restore procedure using the pre-upgrade backup; reverting an image alone
   may not support downgrading that data.

## Management readiness and network isolation

MongoDB joins only the internal `management_backend` network and publishes no
host port. Core joins both that backend and `portainer_network`; the host agent
and application stacks use `portainer_network`. Application containers can reach
Core as before, but cannot connect directly to MongoDB. Core uses the shared
network as its default gateway for outbound connections.

Core starts only after MongoDB passes an authenticated `ping` health check and
`secret-bootstrap` completes. The check connects to `database:27017`, avoiding
MongoDB's temporary loopback-only initialization server. Credentials are read
inside `mongosh` from its environment, so special characters do not need URI or
shell escaping in the health check. A later unhealthy status is diagnostic;
Compose does not automatically restart MongoDB or Core in response to it.

For an existing deployment already using the `management` project, apply this
change from a host terminal in the updated repository checkout:

```sh
docker compose --env-file /srv/komodo/bootstrap.env up -d
docker compose --env-file /srv/komodo/bootstrap.env ps
```

Expect a brief Komodo outage while Compose recreates MongoDB and Core with their
new network memberships. Existing named volumes and credentials are reused;
keep `MANAGEMENT_VOLUME_PREFIX` unchanged. Verify that `database` is healthy,
then check Komodo login and the `home-server` connection. Deployments still using
the old service/project names must first follow the migration section below.

With Docker running, exercise readiness and isolation using disposable state:

```sh
python3 tests/smoke_management.py
```

The test holds MongoDB initialization open to verify Core waits, checks valid
and invalid credentials, verifies Core is reachable from the application
network while MongoDB is blocked by both name and IP, and restarts MongoDB with
its existing test volume. It also verifies host-health configuration and native
alert delivery to a local receiver, then exercises the backup Procedure,
retention, and recovery into a fresh database. It uses fixture credentials, temporary
networks and volumes, no host Docker socket or production data, and removes its
containers, networks, and volumes on exit.

## Komodo backups

`komodo/procedures.toml` manages **Backup Core Database**, scheduled daily at
**01:00 Europe/Vilnius**. Core stores snapshots in `KOMODO_BACKUPS_PATH` and
retains the most recent **14 snapshots**, configurable with
`KOMODO_CLI_MAX_BACKUPS` in the private bootstrap file. The Procedure reports
failures and has its webhook disabled.

Follow [Komodo backups and recovery](docs/komodo-backups.md) to apply the schedule,
verify the first backup, preserve keys and secrets off-host, and restore into a
fresh database before switching Core. An off-host copy still needs your chosen
encrypted backup destination; the configured snapshots are local to the Pi.

## Migrating existing deployments

Renaming Compose services creates new containers. The root project also changes
from its directory-derived name (normally `server`) to `management`, and the
`ngrok` project becomes `public-access`. Plan a short outage and perform this
migration from a host terminal, because the control plane, agent, and public
tunnel will be stopped.

1. Pause automatic GitHub/Komodo deployments during the migration. Before
   updating the checkout, record the old root project name and volume mounts:

   ```sh
   docker inspect komodo-database --format '{{ index .Config.Labels "com.docker.compose.project" }}'
   docker inspect komodo-database komodo-core --format '{{.Name}}{{range .Mounts}}{{if eq .Type "volume"}} {{.Name}}:{{.Destination}}{{end}}{{end}}'
   ```

   Set `MANAGEMENT_VOLUME_PREFIX` in `/srv/komodo/bootstrap.env` to that old project name
   (`server` by default). The root Compose file explicitly reuses
   `<prefix>_komodo-mongo-data`, `<prefix>_komodo-mongo-config`, and
   `<prefix>_komodo-keys`. Verify those match the recorded volumes and take your
   usual database backup before proceeding.
2. While the old Compose files are still checked out, run
   `docker compose down --remove-orphans` in each existing stack's working
   directory, using its existing environment and project name. Stop `ngrok`,
   `media`, `observability`, and `entrypoint`, then the root bootstrap stack.
   For Komodo-managed stacks, use their deployed checkout and generated `.env`.
   Do not add `--volumes` or `-v`; the persistent volumes must be retained.
3. Update the checkout. For manual deployments, move the old
   `stacks/ngrok/.env` to `stacks/public-access/.env`. Remove any old
   `COMPOSE_PROJECT_NAME` override or update it to the corresponding stack name.
   Complete [Credential setup](#credential-setup) and confirm
   `MANAGEMENT_VOLUME_PREFIX` still matches the old root volumes, then run
   `docker compose --env-file /srv/komodo/bootstrap.env up -d` from the
   repository root to start `management`.
4. In Komodo, rename the existing `ngrok` Stack resource to `public-access`
   before syncing `komodo/stacks.toml`. Sync updates its project name, run
   directory, and config-file service references. Resource Sync has deletion
   disabled, so simply syncing without renaming would leave the old `ngrok`
   resource alongside the new one. Deploy `entrypoint` before `observability`,
   `media`, and `public-access`. For manual deployments, start those stacks
   from their updated directories in the same order.
5. Follow [Coordinated deployments](#coordinated-deployments) to replace the
   individual webhooks with the `home-server-deploy` Procedure webhook. Verify
   the renamed containers and service URLs, then resume automatic deployments.
   Update any external scripts that use the old container names. Historical logs retain their old
   container/service labels; new logs use the names in the table above.

## Running

Start the Komodo `management` bootstrap stack from the repository root:

```sh
docker compose --env-file /srv/komodo/bootstrap.env up -d
```

Check Komodo container status:

```sh
docker compose --env-file /srv/komodo/bootstrap.env ps
```

View Komodo logs:

```sh
docker compose --env-file /srv/komodo/bootstrap.env logs -f
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

Start the `public-access` stack manually for local testing:

```sh
cd stacks/public-access
docker compose up -d
```

The ngrok inspection UI/API is published at `http://localhost:4040` by default.
The stack starts the endpoints declared in `stacks/public-access/ngrok.yml`.
By default those are `webhooks`, an HTTPS endpoint that forwards to Komodo, and
`entrypoint`, an HTTP endpoint that forwards to Traefik.

For Komodo, sync the full `komodo/` directory, including `repos.toml`,
`stacks.toml`, `procedures.toml`, `servers.toml`, and `alerters.toml`.
First run root `up -d` from the updated Pi checkout so the new optional Core
secrets exist, even when empty. The sync creates the `home-server` Repo, Stacks
named `entrypoint`, `observability`, `media`, and `public-access` on the
`home-server` server, the `home-server-deploy` Procedure, and the scheduled
`Backup Core Database` Procedure. It also reconciles health settings on the
existing `home-server` Server and creates the disabled `home-server-discord` Alerter.
Every Stack uses `linked_repo = "home-server"` to source its Compose files
through that Repo:

```text
Linked Repo: home-server
Git repository (configured on the Repo): github.com/jrudavicius/home-server
Branch (configured on the Repo): main
Entrypoint run directory: stacks/entrypoint
Observability run directory: stacks/observability
Media run directory: stacks/media
Public access run directory: stacks/public-access
Compose file: docker-compose.yml
```

Resource Sync updates definitions only (`deploy = false` on every Stack).
The `home-server-deploy` Procedure owns deployment ordering: it syncs the
definitions, then checks and deploys `entrypoint`, `observability`, `media`, and
`public-access`, one at a time. This creates the `transmission_ui` network before
media needs it and keeps the public tunnel available until the final stage.

The Repo resource in `komodo/repos.toml` is required for Stack deployments.
Manage the repository, branch, and Git account on `home-server` under
**Repos**; the Stacks inherit those Git settings. Their run directories,
Compose project names and environments remain configured per Stack; deployment
ordering is configured in `komodo/procedures.toml`.

Komodo clones over HTTPS. If the repository is private, add a GitHub token
account in Komodo and select it on the `home-server` Repo and the
`home-server-resources` Resource Sync. Configure the Repo account before
deploying its linked Stacks. Commit and push these files before syncing so
Komodo can read the updated configuration from `main`.

For existing installations, sync `komodo/repos.toml` together with
`komodo/stacks.toml` to switch all four Stacks to the linked Repo, then verify
their source shows `home-server`. If importing the Stack definitions separately,
create or sync the Repo first.

The Resource Sync in `komodo/syncs.toml` reads the `komodo/` directory directly
from `github.com/jrudavicius/home-server` on `main` and reconciles the declared
resources and non-secret variables. Deletion is disabled so resources not yet
represented in TOML, such as other servers and local secrets, are left
alone.

### Coordinated deployments

Use the `home-server-deploy` Procedure for routine deployments, including
manual runs from Komodo's **Procedures** page. Its stages run sequentially and
stop if any execution fails, so a failed sync or entrypoint deployment prevents
later Stacks from being deployed. Each Stack stage uses `DeployStackIfChanged`,
which refreshes the tracked files before checking for changes. A new Stack is
deployed on its first run.

The tracked files include each Stack's Compose and service configuration files,
plus `komodo/stacks.toml`, `komodo/variables.toml`, and `komodo/repos.toml`.
Those shared TOML files require a redeploy because Komodo's file comparison
does not detect changes to Stack environment settings or global variables by
themselves. Consequently, editing any of those shared files deploys all four
Stacks in order; an ordinary service-file edit affects only its Stack, and a
README-only edit does not deploy anything. Existing service restart requirements
still apply to tracked service configuration files.

For first setup or migration from the individual webhooks:

1. Disable the old Resource Sync, Stack, and any Repo push webhooks in GitHub
   before pushing this configuration to `main`, and let active deployments finish.
2. In Komodo, disable **Webhooks** on `home-server-resources` itself before
   manually syncing. For a fresh installation, create the Resource Sync using
   `komodo/syncs.toml`, with webhooks disabled. Komodo cannot update a busy
   resource, including the Sync that is currently running.
3. Refresh and manually run `home-server-resources` for the full `komodo/`
   directory. Confirm that `home-server-deploy` exists and that the Repo and all
   four Stacks have webhooks disabled. This sync does not deploy the Stacks.
4. Run `home-server-deploy` once from Komodo and verify all five stages succeed.
   This also starts `public-access` on a fresh installation. Complete credential
   setup and create the required media directories/networks before this run.
5. Set `KOMODO_WEBHOOK_BASE_URL` to the public HTTPS endpoint, then configure
   exactly one GitHub webhook for **Push events** with this payload URL:

```text
https://<komodo-public-host>/listener/github/procedure/home-server-deploy/main
```

Use content type `application/json` and set the GitHub webhook secret to the
same value as `KOMODO_WEBHOOK_SECRET`. The `/main` suffix filters pushes to
`main`. Delete the old individual webhooks after validating the new one.
Direct Repo, Resource Sync, and Stack webhook execution is disabled in TOML;
the Procedure can still execute those resources internally.

Komodo prevents overlapping runs of the same Procedure; it does not queue a
second run. If another push arrives during deployment, run the Procedure again
after it finishes to reconcile the latest `main`. Retry a failed run from the
Procedure after fixing its cause. If changing `komodo/procedures.toml`, manually
sync while the Procedure is idle before running it, because it cannot update
its own definition while executing. Changes to `komodo/syncs.toml` likewise need
to be applied to the Sync's own configuration while it is idle.

After changing private Core secrets, restart the root stack and manually deploy
the affected application Stack, as described in [Credential setup](#credential-setup).
File change detection does not see secrets changed outside Git. Manually deploy
an unchanged Stack when recovering stopped services. For image upgrades, update
the committed tag and digest as described in [Image versions and updates](#image-versions-and-updates).

Keep `stacks/entrypoint/.env`, `stacks/observability/.env`,
`stacks/media/.env`, and `stacks/public-access/.env` out of Git. The non-secret
media and ngrok variables are declared in `komodo/variables.toml` and are synced
from Git:

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

Complete [Credential setup](#credential-setup) before running the deployment
Procedure: the Stacks require Core secrets loaded from the private bootstrap file.

Create the directories referenced by those variables before deploying media.
Install and test the [MikroTik whole-home VPN policy](router/README.md),
reserve Transmission's LAN identity, and create the external `transmission_lan`
macvlan network on the Pi. The entrypoint stack creates the internal
`transmission_ui` bridge, so it must be deployed before media.

The optional `PLEX_CLAIM` setup is also described under Credential setup.

Transmission has a fixed LAN IP/MAC that MikroTik routes through its existing
Proton WireGuard tunnel. The router's firewall blocks other routed egress,
including WAN fallback when the tunnel fails. IPv6 is disabled in the container
and blocked by MAC on the router; DNS uses Proton's tunnel resolver.

Transmission also joins the internal `transmission_ui` bridge, where Traefik
connects to `media-torrent-client:9091`. Traefik publishes `TRANSMISSION_WEB_PORT`
(default 9091), preserving direct Pi URLs and hostname routes. Transmission
never joins the ordinary `portainer_network`. The Pi, Plex, ngrok, Komodo, other
services and home devices also use Proton through the router. If the tunnel
fails, internet access stops for the whole LAN while local access stays
available. VPN keys stay on the router; Docker does not need them.

Proton inbound port allocation and NAT-PMP renewal are not configured here.
Transmission can initiate outgoing connections. Do not forward its peer port
from the home WAN; see the router guide for details.

Stop the Komodo `management` bootstrap stack:

```sh
docker compose --env-file /srv/komodo/bootstrap.env down
```

## External access and webhooks

Use the `public-access` stack for inbound webhooks and the entrypoint. See
[public access configuration](stacks/public-access/README.md) for endpoint
configuration and the single deployment Procedure webhook URL.

```text
webhooks HTTPS URL -> management-control-plane:9120
entrypoint URL     -> entrypoint-reverse-proxy:80
```

Set `KOMODO_WEBHOOK_BASE_URL` to the public HTTPS webhook URL. ngrok uses the
normal Docker network and the router's whole-home Proton policy. Its public
endpoints depend on the VPN being connected. Periphery remains in Docker;
no host VPN installer or deployment hook is required.

## Notes

- The root Komodo stack creates the shared `portainer_network` and the internal
  `management_backend` network used only by MongoDB and Core.
- The `entrypoint`, `observability`, `media`, and `public-access` Stacks attach to
  `portainer_network` as an external Docker network so Traefik can route across
  Compose projects.
- Komodo keys and MongoDB data are stored in Docker-managed volumes.
- Loki, Grafana, and Alloy data are stored in Docker-managed volumes.
- Transmission uses its dedicated macvlan LAN identity for Proton routing and
  an internal bridge for Traefik; there is no VPN container.
- Bootstrap settings come from `/srv/komodo/bootstrap.env`; managed application
  settings come from Komodo. Manual application deployments use stack `.env`
  files.
- Timezone is configured as `Europe/Vilnius`.
