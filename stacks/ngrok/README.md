# ngrok Endpoints

Dockerized ngrok agent for external Home Server access and GitHub webhook
delivery.

The stack uses one ngrok container with endpoints declared in `ngrok.yml`. The
default config starts two public endpoints:

```text
webhooks  -> http://komodo-core:9120
entrypoint -> http://home-server-proxy:80
```

The `webhooks` endpoint is an HTTPS endpoint for Komodo listener URLs used by
GitHub webhooks. The `entrypoint` endpoint is an HTTP endpoint that opens the
Traefik landing page and routed services. Splitting the schemes keeps the two
endpoints distinct on an ngrok account that only assigns one free hostname.

## Setup

Copy the example environment file and add your ngrok auth token:

```sh
cp .env.example .env
```

```env
NGROK_AUTHTOKEN=your-ngrok-authtoken
NGROK_INSPECT_PORT=4040
NGROK_DOCKER_NETWORK=portainer_network
```

Start the endpoints:

```sh
docker compose up -d
```

Check the public forwarding URLs:

```sh
docker compose logs -f ngrok
```

The local ngrok inspection UI/API is available at:

```text
http://localhost:4040
http://localhost:4040/api/tunnels
```

## Endpoint configuration

Edit `ngrok.yml` to change the public endpoints. Each endpoint needs a unique
`name` and an `upstream.url` that is reachable on the Docker network:

```yaml
endpoints:
  - name: webhooks
    url: https://
    upstream:
      url: http://komodo-core:9120
  - name: entrypoint
    url: http://
    upstream:
      url: http://home-server-proxy:80
```

By default, `webhooks` uses an HTTPS public URL and `entrypoint` uses an HTTP
public URL. To use stable reserved or custom domains, or to make both endpoints
HTTPS, use `ngrok.multi-endpoint.example.yml` as the starting point:

```yaml
endpoints:
  - name: webhooks
    url: https://your-webhooks-domain.ngrok.app
    upstream:
      url: http://komodo-core:9120
  - name: entrypoint
    url: https://your-entrypoint-domain.ngrok.app
    upstream:
      url: http://home-server-proxy:80
```

After startup, verify in the logs or inspector that `webhooks` and `entrypoint`
have two different public URLs.

## Komodo webhook base URL

After ngrok is running, copy the `webhooks` public HTTPS URL into the root
Server `.env`:

```env
KOMODO_WEBHOOK_BASE_URL=https://your-webhooks-ngrok-url
```

Then restart Komodo from the repository root:

```sh
docker compose up -d
```

Use these webhook payload URLs in GitHub:

```text
https://your-webhooks-ngrok-url/listener/github/sync/home-server-resources/sync
https://your-webhooks-ngrok-url/listener/github/stack/entrypoint/deploy
https://your-webhooks-ngrok-url/listener/github/stack/observability/deploy
https://your-webhooks-ngrok-url/listener/github/stack/media/deploy
https://your-webhooks-ngrok-url/listener/github/stack/ngrok/deploy
```

Use `application/json` as the content type and use the value of
`KOMODO_WEBHOOK_SECRET` from the root Server `.env` as the webhook secret.

## Security note

The `entrypoint` endpoint exposes the Traefik landing page publicly over HTTP by
default. The `webhooks` endpoint forwards directly to Komodo, so keep Komodo
credentials strong, keep the webhook secret private, and stop the endpoint or the
ngrok stack when it is not needed. Use explicit reserved or custom HTTPS domains
before exposing sensitive routed services through `entrypoint`.
