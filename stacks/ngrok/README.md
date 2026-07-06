# ngrok Tunnel

Dockerized ngrok tunnel for external Komodo access and GitHub webhook delivery.

By default the tunnel forwards directly to Komodo at `komodo-core:9120`, so one
public HTTPS URL can open the Komodo UI and receive GitHub webhooks.

## Setup

Copy the example environment file and add your ngrok auth token:

```sh
cp .env.example .env
```

```env
NGROK_AUTHTOKEN=your-ngrok-authtoken
NGROK_INSPECT_PORT=4040
NGROK_DOCKER_NETWORK=portainer_network
NGROK_TUNNEL_TARGET=http://komodo-core:9120
```

Start the tunnel:

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

## Reserved ngrok domain

If you have a reserved ngrok domain, set it in `.env`:

```env
NGROK_DOMAIN=your-domain.ngrok.app
```

Then start with the override file:

```sh
docker compose -f docker-compose.yml -f docker-compose.domain.yml up -d
```

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
https://your-public-ngrok-url/listener/github/stack/media/deploy
https://your-public-ngrok-url/listener/github/stack/ngrok/deploy
```

Use `application/json` as the content type and use the value of
`KOMODO_WEBHOOK_SECRET` from the root Server `.env` as the webhook secret.

## Traefik entrypoint tunnel

To expose the Traefik entrypoint instead of Komodo directly, set:

```env
NGROK_TUNNEL_TARGET=http://home-server-proxy:80
```

That opens the landing page at the ngrok URL and still receives webhooks because
Traefik routes `/listener/...` to Komodo. Host-based local routes such as
`komodo.home.arpa` and `plex.home.arpa` still need local DNS or explicit public
URLs.

## Security note

The default tunnel exposes Komodo publicly while the container is running. Keep
Komodo credentials strong, keep the webhook secret private, and stop the tunnel
when it is not needed.
