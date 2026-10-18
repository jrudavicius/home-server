# Transmission-only Proton VPN on MikroTik

Transmission has its own LAN identity through Docker macvlan. MikroTik routes
only that identity through Proton. The Pi, Plex, ngrok, Komodo and other
containers use ordinary WAN routing.

## Current configuration

| Setting | Value |
| --- | --- |
| Pi | `192.168.88.250`, wired interface `eth0` |
| LAN gateway | `192.168.88.1` |
| Transmission | `192.168.88.9`, MAC `02:54:52:00:00:01` |
| Proton tunnel | `wg-proton-pi` (existing interface name) |
| Routing table | `proton-transmission` |
| Proton DNS | `10.2.0.1` |
| Web UI | `http://192.168.88.250:9091` or `http://transmission.home.arpa` |

Keep the IP, MAC and DNS values identical in RouterOS, Compose and Komodo.
The Transmission address is reserved on the router and outside the dynamic
DHCP pool. The hostname URL requires local DNS; port 9091 works without it.

The router policy must retain these protections:

- Source routing sends the exact LAN subnet to `main`, then all other traffic
  from Transmission to `proton-transmission` with `lookup-only-in-table`.
  That table's default route uses `wg-proton-pi`, with no WAN fallback.
- IP and MAC guards run before FastTrack and established-connection accepts.
  The `proton-tx-out` chain drops invalid packets, allows local LAN traffic and
  the expected source IP over WireGuard, then drops other routed egress.
- The `proton-tx-in` chain allows established/related VPN replies and drops
  unsolicited traffic. The global VPN ingress drop follows that reply guard.
- VPN masquerading applies only to Transmission. Routed TCP/UDP port 53 is
  redirected to Proton DNS, and router DNS fallback is blocked by MAC.
- Routed IPv6 and IPv6 router DNS are blocked by MAC. IPv6 is also disabled
  inside the container.

Transmission joins only `transmission_lan` and the internal `transmission_ui`
bridge. It must never join `portainer_network`. Traefik shares the internal
bridge and proxies HTTP to `media-torrent-client:9091`; it owns Pi port 9091.
Explicit container DNS sends Docker resolver queries to Proton.

Same-subnet LAN traffic remains local. A trusted LAN proxy or administrator
changing network identities can bypass this arrangement. Router UPnP and home
WAN peer-port forwarding must remain off for Transmission. Proton inbound port
allocation and renewal are not configured; outgoing torrent connections work.

## Provisioning the Docker networks

The router policy must be installed and tested before starting Transmission.
On a replacement wired Linux host, create its external macvlan network:

```sh
docker network create --driver macvlan \
  --subnet 192.168.88.0/24 --ip-range 192.168.88.9/32 \
  --gateway 192.168.88.1 --opt parent=eth0 transmission_lan
```

If the network already exists, inspect its driver, parent, subnet, gateway,
IPv6 setting and attached containers instead of replacing it. Only Transmission
should use it. Deploy `entrypoint` first to create the internal `transmission_ui`
bridge, then `media`. Compose 2.33.1+ is required for gateway priority.

## Verification

Run on the Pi after network or router changes:

```sh
docker exec media-torrent-client ip route
docker exec media-torrent-client curl -4 --noproxy '*' --fail --max-time 15 https://ip.me
curl -4 --noproxy '*' --fail --max-time 15 https://ip.me
docker exec media-torrent-client nslookup example.org
docker exec media-torrent-client curl -6 --noproxy '*' --fail --max-time 15 'https://[2606:4700:4700::1111]/cdn-cgi/trace'
```

Transmission's default gateway must be `192.168.88.1`, its public IPv4 must
belong to Proton, and the Pi must show its ordinary WAN address. DNS must work;
IPv6 must fail to connect. Check authenticated web/RPC access through Traefik.

For an outage check, pause torrents and arrange automatic tunnel restoration
before temporarily disabling only `wg-proton-pi`. Keep the firewall guards
enabled. Transmission must lose literal-IP connectivity and fresh DNS resolution,
while the Pi, other services and Transmission's web UI keep working. Restore
the tunnel and verify recovery before resuming torrents.

These checks passed on 2026-10-18, including a 45-second WireGuard outage and
ordinary WAN access from Plex, ngrok, Komodo, Traefik and Grafana. Router/Pi
reboot and physical backup-WAN failover have not been tested.

The repository's Compose network checks run with:

```sh
python3 -m unittest discover -s tests -v
```

## Recovery

Router configuration and keys are managed on the MikroTik. Preserve a private
router export and binary backup before changes. Existing recovery copies are
`pre-transmission-20261018` and `post-transmission-20261018` on the router, plus
`/home/manager/transmission-vpn-migration-20261018` on the Pi.

Stop Transmission before changing its routing or restoring older configuration.
The old `proton-pi:` rules remain disabled on the router for rollback; enabling
them changes routing for the entire Pi. Restore matching router, Compose and
environment backups together, accounting for which service owns port 9091.
Keep Transmission stopped until VPN isolation and the outage check pass.
