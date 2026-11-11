# Public Access

This ngrok stack is retained for rollback and stays stopped in the current
deployment. GitHub delivery now uses the
[gateway HTTPS receiver](../../host/netcup-webhook/README.md). Routine
deployments do not include this Stack. Its configuration, token and exact image
are retained; the instructions below apply when deliberately restoring ngrok.

The `public-access` stack uses the `tunnel` service (`public-access-tunnel`
container), powered by ngrok, with endpoints declared in `ngrok.yml`.
The agent image is pinned by exact version and digest in `docker-compose.yml`;
follow [Image versions and updates](../../README.md#image-versions-and-updates)
to upgrade it.
The default config starts one HTTPS endpoint:

```text
webhooks -> http://entrypoint-reverse-proxy:9121 -> Komodo GitHub listeners
```

Traefik's internal port 9121 accepts only POST requests to
`/listener/github/procedure/home-server-deploy/main`; every other path or method receives 404. That port is not
published on the Pi. Komodo still validates each webhook signature. The old
public landing-page endpoint is preserved in the pre-portability Git tag and
is no longer started. Use `http://10.77.77.2/` over the VPN for applications.
Deploy `entrypoint` before this stack so the restricted listener exists.

For an existing deployment, follow the
[naming migration](../../README.md#migrating-existing-deployments) before
deploying the renamed stack.

## Setup

For manual deployment, copy the example environment file and add your ngrok
auth token only in the private `.env` copy:

```sh
umask 077
cp -n .env.example .env
chmod 600 .env
```

```env
NGROK_AUTHTOKEN=
NGROK_INSPECT_PORT=4040
NGROK_DOCKER_NETWORK=portainer_network
```

Fill `NGROK_AUTHTOKEN` with your token from the ngrok dashboard before starting.
The `.env` file is ignored by Git; leave `.env.example` empty. For the full
credential inventory, see [Credential setup](../../README.md#credential-setup).

Start the endpoints:

```sh
docker compose up -d
```

Check the public forwarding URLs:

```sh
docker compose logs -f tunnel
```

The local ngrok inspection UI/API is available at:

```text
http://localhost:4040
http://localhost:4040/api/tunnels
```

## Komodo deployment

Komodo sources this Stack through the linked `home-server` Repo declared in
`komodo/repos.toml` and writes the Stack environment to its deployment `.env`
before deploying. Sync the Repo together with `komodo/stacks.toml`. Komodo does
not read the `.env` in your local Server checkout.

Set `NGROK_AUTHTOKEN` to your ngrok auth token in the Pi's private
`/srv/komodo/bootstrap.env`, then run this from the repository root:

```sh
docker compose --env-file /srv/komodo/bootstrap.env up -d
```

The bootstrap service loads it into Komodo as a Core secret automatically.
The Stack environment in `komodo/stacks.toml` already references it as:

```env
NGROK_AUTHTOKEN=[[NGROK_AUTHTOKEN]]
```

Deploy the `public-access` Stack after the root stack has updated. If the old value is
still used, remove any editable `NGROK_AUTHTOKEN` variable previously created
in Komodo's UI; it overrides the Core secret. See the main
[migration instructions](../../README.md#existing-installations).

Editing the generated `.env` in Komodo's checkout is temporary: the next
deployment rewrites it. Update `/srv/komodo/bootstrap.env` and rerun the root
command above before redeploying `public-access`.

## Endpoint configuration

The webhook endpoint uses an automatically assigned HTTPS URL. To use a
reserved domain, set its `url` in `ngrok.yml`; retain the restricted upstream:

```yaml
endpoints:
  - name: webhooks
    url: https://your-webhooks-domain.ngrok.app
    upstream:
      url: http://entrypoint-reverse-proxy:9121
```

`ngrok.multi-endpoint.example.yml` is a historical alternative that deliberately
exposes applications publicly. It is not used by the portable private setup.

After startup, verify the inspector lists only `webhooks`. Public requests to
`/`, `/auth`, `/read`, `/write`, `/execute`, and `/dashboard/` must return 404;
unsigned GitHub webhook requests must be rejected by Komodo. Keep the old
GitHub URL if it is unchanged, and verify delivery before retiring old routes.

## Komodo webhook base URL

After ngrok is running, copy the `webhooks` public HTTPS URL into
`/srv/komodo/bootstrap.env` on the server:

```env
KOMODO_WEBHOOK_BASE_URL=https://your-webhooks-ngrok-url
```

Then restart Komodo from the repository root:

```sh
docker compose --env-file /srv/komodo/bootstrap.env up -d
```

Follow the [coordinated deployment setup](../../README.md#coordinated-deployments)
to sync `komodo/procedures.toml`, run `home-server-deploy` once, and replace the
old individual webhooks. Configure exactly one GitHub webhook for **Push events**:

```text
https://your-webhooks-ngrok-url/listener/github/procedure/home-server-deploy/main
```

Use `application/json` as the content type and use the value of
`KOMODO_WEBHOOK_SECRET` from `/srv/komodo/bootstrap.env` as the webhook secret.
The `/main` suffix selects pushes to `main`. The Procedure syncs configuration
first, then checks and deploys entrypoint, observability and media sequentially.
Start this rollback Stack manually; routine deployments leave it untouched.
A failed stage stops the remaining stages.
Direct Resource Sync, Repo, and Stack webhook execution is disabled.

## Security note

The ngrok URL is only for signed GitHub webhook delivery. Administrative
interfaces and application pages are available through the private VPN or
local LAN. Keep `KOMODO_WEBHOOK_SECRET` private and do not point the tunnel
directly at Komodo or the ordinary Traefik web listener.
