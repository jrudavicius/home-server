# Public Access

Dockerized ngrok agent for external Home Server access and GitHub webhook
delivery.

The `public-access` stack uses the `tunnel` service (`public-access-tunnel`
container), powered by ngrok, with endpoints declared in `ngrok.yml`.
The default config starts two public endpoints:

```text
webhooks  -> http://management-control-plane:9120
entrypoint -> http://entrypoint-reverse-proxy:80
```

The `webhooks` endpoint is an HTTPS endpoint for Komodo listener URLs used by
GitHub webhooks. The `entrypoint` endpoint is an HTTP endpoint that opens the
Traefik landing page and routed services. Splitting the schemes keeps the two
endpoints distinct on an ngrok account that only assigns one free hostname.

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

Komodo deploys the Git-based stack from its own checkout and writes the Stack
environment to `.env` before deploying. It does not read the `.env` in your local
Server checkout.

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

Edit `ngrok.yml` to change the public endpoints. Each endpoint needs a unique
`name` and an `upstream.url` that is reachable on the Docker network:

```yaml
endpoints:
  - name: webhooks
    url: https://
    upstream:
      url: http://management-control-plane:9120
  - name: entrypoint
    url: http://
    upstream:
      url: http://entrypoint-reverse-proxy:80
```

By default, `webhooks` uses an HTTPS public URL and `entrypoint` uses an HTTP
public URL. To use stable reserved or custom domains, or to make both endpoints
HTTPS, use `ngrok.multi-endpoint.example.yml` as the starting point:

```yaml
endpoints:
  - name: webhooks
    url: https://your-webhooks-domain.ngrok.app
    upstream:
      url: http://management-control-plane:9120
  - name: entrypoint
    url: https://your-entrypoint-domain.ngrok.app
    upstream:
      url: http://entrypoint-reverse-proxy:80
```

After startup, verify in the logs or inspector that `webhooks` and `entrypoint`
have two different public URLs.

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

Use these webhook payload URLs in GitHub:

```text
https://your-webhooks-ngrok-url/listener/github/sync/home-server-resources/sync
https://your-webhooks-ngrok-url/listener/github/stack/entrypoint/deploy
https://your-webhooks-ngrok-url/listener/github/stack/observability/deploy
https://your-webhooks-ngrok-url/listener/github/stack/media/deploy
https://your-webhooks-ngrok-url/listener/github/stack/public-access/deploy
```

Use `application/json` as the content type and use the value of
`KOMODO_WEBHOOK_SECRET` from `/srv/komodo/bootstrap.env` as the webhook secret.

## Security note

The `entrypoint` endpoint exposes the Traefik landing page publicly over HTTP by
default. The `webhooks` endpoint forwards directly to Komodo, so keep Komodo
credentials strong, keep the webhook secret private, and stop the endpoint or the
`public-access` stack when it is not needed. Use explicit reserved or custom
HTTPS domains before exposing sensitive routed services through `entrypoint`.
