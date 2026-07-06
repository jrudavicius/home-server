# ngrok Endpoints

Dockerized ngrok agent for external Home Server access and GitHub webhook
delivery.

The stack uses one ngrok container with endpoints declared in `ngrok.yml`. The
default config starts a single public endpoint:

```text
entrypoint -> http://home-server-proxy:80
```

The `entrypoint` endpoint opens the Traefik landing page and receives webhooks
because Traefik routes `/listener/...` to Komodo.

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

Start the endpoint:

```sh
docker compose up -d
```

Check the public forwarding URL:

```sh
docker compose logs -f ngrok
```

The local ngrok inspection UI/API is available at:

```text
http://localhost:4040
http://localhost:4040/api/tunnels
```

## Endpoint configuration

Edit `ngrok.yml` to change the public endpoint. Each endpoint needs a unique
`name` and an `upstream.url` that is reachable on the Docker network:

```yaml
endpoints:
  - name: entrypoint
    upstream:
      url: http://home-server-proxy:80
```

## Multiple public endpoints

The free ngrok account used for this stack started two HTTP endpoint definitions
on the same `ngrok-free.dev` URL. That is not useful for splitting traffic
between services, so the default config keeps one endpoint and lets Traefik route
paths internally.

If your ngrok account supports distinct reserved or custom domains, use
`ngrok.multi-endpoint.example.yml` as the starting point. Each public endpoint
needs its own `url`:

```yaml
endpoints:
  - name: entrypoint
    url: https://your-entrypoint-domain.ngrok.app
    upstream:
      url: http://home-server-proxy:80
  - name: komodo
    url: https://your-komodo-domain.ngrok.app
    upstream:
      url: http://komodo-core:9120
```

On the free plan, keep the account limits in mind: at the time this was checked,
ngrok allowed up to 3 online endpoints and 3 concurrent agents, but custom or
reserved domains required a paid plan.

## Komodo webhook base URL

After ngrok is running, copy the public HTTPS URL into the root Server `.env`:

```env
KOMODO_WEBHOOK_BASE_URL=https://your-public-ngrok-url
```

Then restart Komodo from the repository root:

```sh
docker compose up -d
```

Use these webhook payload URLs in GitHub:

```text
https://your-public-ngrok-url/listener/github/sync/home-server-resources/sync
https://your-public-ngrok-url/listener/github/stack/entrypoint/deploy
https://your-public-ngrok-url/listener/github/stack/observability/deploy
https://your-public-ngrok-url/listener/github/stack/media/deploy
https://your-public-ngrok-url/listener/github/stack/ngrok/deploy
```

Use `application/json` as the content type and use the value of
`KOMODO_WEBHOOK_SECRET` from the root Server `.env` as the webhook secret.

## Security note

The `entrypoint` endpoint exposes the Traefik landing page and `/listener`
webhook paths publicly while the container is running. Keep Komodo credentials
strong, keep the webhook secret private, and stop the endpoint or the ngrok stack
when it is not needed.
