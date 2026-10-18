# Whole-home Proton VPN on MikroTik

MikroTik routes every device on the home LAN through Proton, including the Pi,
Plex, ngrok, Komodo and other containers. Internet access stops if the tunnel
fails; neither uplink provides direct ISP fallback. Local LAN access remains
available. This policy was activated and outage-tested on 2026-10-18; see
[Verification](#verification) below for results and test limits.

Transmission retains its dedicated Docker macvlan identity and additional
IP/MAC firewall guards. No Docker network or deployment changes were required
for the whole-home migration.

## Current configuration

| Setting | Value |
| --- | --- |
| Pi | `192.168.88.250`, wired interface `eth0` |
| LAN gateway | `192.168.88.1` |
| Home LAN | `bridge`, `192.168.88.0/24` |
| WAN interfaces | `ether1` primary; `wifi2` iPhone backup |
| Transmission | `192.168.88.9`, MAC `02:54:52:00:00:01` |
| Proton tunnel | `wg-proton-pi` (existing interface name) |
| Home routing table | `proton-home` |
| Transmission routing table | `proton-transmission` |
| Proton DNS | `10.2.0.1` |
| Web UI | `http://192.168.88.250:9091` or `http://transmission.home.arpa` |

Keep the IP, MAC and DNS values identical in RouterOS, Compose and Komodo.
The Transmission address is reserved on the router and outside the dynamic
DHCP pool. The hostname URL requires local DNS; port 9091 works without it.

## Whole-home routing and kill switch

The additions are tagged `proton-home:` on the router. Keep these protections
together:

- Routing rules keep the exact LAN subnet in `main`, then send traffic entering
  `bridge` to `proton-home` with `lookup-only-in-table`. Its only default route
  uses `wg-proton-pi`; it has no WAN fallback.
- The LAN forwarding guard runs before established-connection accepts and
  FastTrack. `proton-home-out` drops invalid packets, permits local LAN traffic
  and the expected LAN source subnet through WireGuard, then drops other egress.
- Established/related VPN replies to the LAN are accepted before the existing
  global VPN ingress drop. Transmission's more specific guards remain first.
- Masquerading on `wg-proton-pi` covers LAN and router-originated traffic.
  FastTrack is disabled. Existing LAN internet connections were cleared at
  cutover so old direct paths and NAT mappings could not persist.
- Router output is marked for `proton-home`; an explicit routing-mark rule
  also uses `lookup-only-in-table`. The output guard permits local traffic,
  VPN-only marked traffic and the tunnel itself. Only WireGuard transport,
  WAN DHCP and the existing primary-link ICMP health checks bypass the tunnel.
  These exceptions apply to the router, never to forwarded LAN clients.
- Router DNS uses only `10.2.0.1`, with an explicit tunnel host route. Both WAN
  DHCP clients have `use-peer-dns=no`. Hardcoded external resolvers on clients
  also follow VPN-only routing, including encrypted DNS.
- IPv6 forwarding from the LAN to non-LAN interfaces and router IPv6 output
  to WAN are blocked. This tunnel currently provides IPv4 internet only;
  same-link local IPv6 communication remains available.

In RouterOS, output filtering precedes routing adjustment. The output guard's
accept for `routing-mark=proton-home` therefore relies on the explicit
`lookup-only-in-table` rule to prevent fallback. Do not remove that rule while
leaving the marked-output accept. See MikroTik's
[packet flow](https://help.mikrotik.com/docs/spaces/ROS/pages/328227/Packet+Flow+in+RouterOS)
and [policy routing](https://help.mikrotik.com/docs/spaces/ROS/pages/59965508/Policy+Routing)
documentation.

The current Proton endpoint is `130.195.243.2:51820`. If it changes, update both
the `WireGuard underlay` mangle exception and the `allow tunnel transport`
filter exception together with the peer. New LANs/VLANs require explicit
routing and firewall coverage before use. Devices using their own cellular
connection are outside this router's control.

## Transmission-specific protections

The earlier policy remains in addition to the whole-home policy:

- Source routing sends the exact LAN subnet to `main`, then all other traffic
  from Transmission to `proton-transmission` with `lookup-only-in-table`.
  That table's default route uses `wg-proton-pi`, with no WAN fallback.
- IP and MAC guards run before FastTrack and established-connection accepts.
  The `proton-tx-out` chain drops invalid packets, allows local LAN traffic and
  the expected source IP over WireGuard, then drops other routed egress.
- The `proton-tx-in` chain allows established/related VPN replies and drops
  unsolicited traffic. The global VPN ingress drop follows the Transmission
  and whole-home reply guards.
- Transmission retains its specific VPN masquerading rule. Routed TCP/UDP
  port 53 is redirected to Proton DNS, and router DNS fallback is blocked by MAC.
- Routed IPv6 and IPv6 router DNS are blocked by MAC. IPv6 is also disabled
  inside the container.

Transmission joins only `transmission_lan` and the internal `transmission_ui`
bridge. It must never join `portainer_network`. Traefik shares the internal
bridge and proxies HTTP to `media-torrent-client:9091`; it owns Pi port 9091.
Explicit container DNS sends Docker resolver queries to Proton.

Same-subnet LAN traffic remains local. Administrators must preserve both
policies when changing network identities or adding other internet gateways.
Router UPnP and home WAN peer-port forwarding must remain off for Transmission.
Proton inbound port allocation and renewal are not configured; outgoing torrent
connections work.

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

Transmission's default gateway must be `192.168.88.1`. Both Transmission and
the Pi must show a Proton public IPv4 address. Repeat the public-IP and DNS
checks from a Wi-Fi client and representative containers. DNS must work;
IPv6 internet must fail to connect. Check authenticated web/RPC access through
Traefik.

For an outage check, pause torrents and arrange automatic tunnel restoration
before temporarily disabling only `wg-proton-pi`. Keep the firewall guards
enabled. Every LAN client must lose literal-IP internet connectivity and fresh
external DNS resolution. Local access to the router, Pi, Plex and Transmission
must keep working. Restore the tunnel and verify Proton connectivity before
resuming torrents.

On 2026-10-18, a Wi-Fi client and the router used Proton exit `130.195.243.30`.
During a 31-second tunnel outage, client IPv4 and fresh DNS via the router or
external UDP/TCP resolvers failed, while local server/Plex HTTP and the
Transmission authentication page remained reachable. The router's own
internet ping also failed with no route. Connectivity recovered through
Proton after automatic tunnel restoration. IPv6 internet attempts failed
before, during and after the outage; no usable global IPv6 connection was
present to exercise the new IPv6 firewall rules end to end.

This migration did not repeat tests inside the Pi/containers, authenticated
Transmission RPC, Plex playback or public ngrok endpoints. Router/Pi reboot and
physical uplink failover remain untested. The active uplink was `wifi2`; the
primary `ether1` DHCP client was searching.

The repository's Compose network checks run with:

```sh
python3 -m unittest discover -s tests -v
```

## Recovery

Router configuration and keys are managed on the MikroTik. Preserve a private
router export and binary backup before changes. The current migration saved
these `.rsc` and `.backup` pairs on the router:

- `pre-home-vpn-20261018-1637`: previous Transmission-only policy.
- `post-home-vpn-20261018-1649`: verified whole-home policy.

Binary backups contain secrets and must stay private. The temporary
`proton-home-rollback-timer` and `proton-home-test-restore` schedulers are
disabled. There is no scheduled rollback or ISP fallback.

For an intentional return to the prior Transmission-only policy, use a local
WinBox session and run `/system script run proton-home-rollback`. This removes
the additions tagged `proton-home:`, restores WAN-provided router DNS and
FastTrack, and preserves Transmission's guards. It **restores direct ISP
access for other devices**. Reconnect affected internet sessions afterward;
inspect and clear stale connection entries if required. Use the private
pre-migration backup if targeted recovery cannot complete.

Older recovery copies are `pre-transmission-20261018` and
`post-transmission-20261018` on the router, plus
`/home/manager/transmission-vpn-migration-20261018` on the Pi.

Stop Transmission before changing its routing or restoring older configuration.
The old `proton-pi:` rules remain disabled on the router for rollback; enabling
them changes routing for the entire Pi. Restore matching router, Compose and
environment backups together, accounting for which service owns port 9091.
Keep Transmission stopped until VPN isolation and the outage check pass.
