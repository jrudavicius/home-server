# Portable Pi networking

The Pi uses DHCP at either home. `wg-netcup` gives it the stable private address
`10.77.77.2`; personal devices connect to the Netcup public endpoint and then use
that private address. The public endpoint belongs to the gateway, not to the
Pi's current router. No incoming port forwarding is needed at either home.

Ordinary Pi and Docker internet traffic uses a separate `wg-proton` tunnel.
The host firewall blocks direct physical-interface fallback, including DNS and
IPv6. Management transport has its own marked UDP exception and endpoint route,
so Pi-side Proton failure does not disconnect private administration.

## Files and responsibilities

| Source | Installed location | Purpose |
| --- | --- | --- |
| `prepare.py` | Run from a private staging directory | Reads a saved Proton config and creates inactive root-only NetworkManager profiles; generates the management key on the Pi |
| `network.py` | `/usr/local/sbin/home-server-network` | Atomically refreshes only the owned nftables table and two endpoint routes |
| `portable-network.example.json` | `/etc/home-server/portable-network.json`, with real endpoints | Non-secret endpoint/interface/mark parameters; do not put private keys here |
| `home-server-network.service` | `/etc/systemd/system/` | Loads the guard before NetworkManager and Docker |
| `guard-dependency.conf` | `90-home-server-network.conf` under both `NetworkManager.service.d` and `docker.service.d` | Makes both services require the guard |
| `90-home-server-network` | `/etc/NetworkManager/dispatcher.d/`, root-owned mode 0700 | Refreshes routes and LAN exceptions after uplink changes |
| `test_network.py` | Run next to `network.py` on Linux | Exercises the real firewall in temporary network namespaces |

The helper owns only `inet home_server_portable`. It never flushes Docker's
tables. Endpoint `/32` routes use protocol `242` and the lowest-metric active
physical default route. The dispatcher reads current state, so a queued event
cannot restore an old home subnet. DHCP changes do not require editing the VPN
profiles. `eth0` and `wlan0` are the supported physical interfaces; add any other
uplink to the private JSON before using it.

Local access is allowed only to the currently connected RFC1918 subnet(s).
Normal DNS on the physical uplinks is blocked even within those subnets.
NetworkManager gives Proton's DNS a negative priority so uplink DNS is excluded.
Services that need external names explicitly use `10.2.0.1` in Compose.
Docker's embedded resolver otherwise retains the router DNS from container
creation; changing the host resolver does not update existing containers.
Apply the DNS setting to Core and Periphery before expecting Git fetches to
work, preserving their current images and environment during the migration.
Docker bridges are protected by the forwarding chain; macvlan and other traffic
that bypasses host forwarding are unsupported. This policy assumes trusted
root access and Docker administrators.

## Safe installation order

Preserve the matched live baseline first; use the
[migration and rollback record](../../docs/portable-pi-migration.md). These are
staged operations, not an unattended one-command installer. Keep a working local
SSH session and arrange a timed rollback before activating the guard or routes.

1. Install `wireguard-tools`, `nftables`, and Python 3. Use the existing
   NetworkManager service; do not introduce another network manager. Check
   `eth0` and the home Wi-Fi profiles use DHCP and autoconnect.
2. Run `sudo python3 host/portable/test_network.py` on the Pi. The test creates
   temporary namespaces, fake tunnel interfaces, and UDP listeners, then removes
   them. Its firewall and route changes stay inside those namespaces.
3. Prepare profiles, using the gateway's actual public IP and public key:

   ```sh
   sudo python3 host/portable/prepare.py \
     --management-endpoint NETCUP_PUBLIC_IPV4 \
     --management-public-key NETCUP_WIREGUARD_PUBLIC_KEY \
     --proton-config /private/path/to/proton.conf
   ```

   The input must be an IPv4 WireGuard configuration with one peer. Unexpected
   directives cause a failure for review. Profiles start with autoconnect off;
   the script refuses to overwrite existing keys. Private keyfiles are saved as
   `/etc/NetworkManager/system-connections/home-server-{netcup,proton}.nmconnection`.
4. Add the printed Pi public key on Netcup with `AllowedIPs = 10.77.77.2/32`.
   Leave its endpoint unset so it can roam. Preserve the existing Mac peer at
   `10.77.77.3/32`. Enable gateway IPv4 forwarding and allow only `wg0` to `wg0`
   traffic from `.3` to `.2`, plus established replies from `.2` to `.3`.
   Keep every other forwarding path blocked. Preserve the gateway's public SSH
   recovery access and current firewall before editing it.
5. Activate `home-server-netcup`, verify its handshake and private SSH, then
   add `10.77.77.2/32` to both the Mac profile and active peer routes. Confirm
   service access from the Mac before retiring any prior access path.
6. Stop Transmission. Install the guard, dispatcher, unit and dependency files
   listed above. Keep the default `nftables.service` disabled if its configuration
   flushes the whole ruleset. Reload systemd, validate the unit, start
   `home-server-network.service`, then activate `home-server-proton` immediately.
   The guard stays present when its service stops; removing it is a deliberate
   rollback operation.
7. Verify Proton DNS and a public HTTPS request from the host and a disposable
   container. A WireGuard handshake alone is insufficient. Test forced physical
   egress, DNS and IPv6 denial, and repeat while Proton is down with an automatic
   restoration timer. Private Netcup SSH must remain usable throughout.
8. Once the guard and tunnel pass, create the protected Transmission bridge:

   ```sh
   docker network create --driver bridge --ipv6=false transmission_vpn
   ```

   Pin the media deployment to the reviewed portable revision before deploying
   the changed Compose. Preserve its environment, password and volumes. Keep the
   existing internal `transmission_ui` bridge. Remove the old empty
   `transmission_lan` macvlan only after the new deployment is verified.
9. Set both VPN profiles to autoconnect and enable the guard unit. Reboot and
   recheck private SSH, services, DNS, egress, and the kill switch. Test a real
   change of uplink separately; namespace tests do not prove Wi-Fi credentials
   or the other router's policy.

## Access and operation

With the Mac Netcup VPN connected:

| Service | Address |
| --- | --- |
| SSH | `manager@10.77.77.2` |
| Landing page | `http://10.77.77.2/` |
| Komodo | `http://10.77.77.2:9120` |
| Transmission | `http://10.77.77.2:9091` |
| Grafana | `http://10.77.77.2:3000` |
| Plex | `http://10.77.77.2:32400/web` |

These HTTP connections travel inside WireGuard when using the VPN address.
Existing `*.home.arpa` names depend on the current home's DNS; the VPN itself
does not configure those names. Additional personal devices need unique keys,
addresses, gateway forwarding rules, and management allowlist entries.

Useful checks, which do not print private keys:

```sh
sudo wg show
nmcli -f NAME,TYPE,DEVICE connection show --active
sudo systemctl status home-server-network.service
sudo nft list table inet home_server_portable
ip -4 rule
ip -4 route show table 51821
ip -4 route show proto 242
cat /etc/resolv.conf
```

The current ngrok configuration exposes only the exact coordinated GitHub
deployment POST path through Traefik's internal port 9121. The former public
application endpoint is retained in the pre-portability source tag for rollback.
On the original MikroTik network, its whole-home Proton policy still
controls the underlying transport. Surviving that router's own Proton outage
requires a narrow Pi-to-Netcup UDP exception, backed up and tested separately.

## Rollback

Stop Transmission and pause deployment triggers first. Restore only the matched
files and settings from the preservation checkpoint; keep current media and
application volumes. Remove the new systemd dependency drop-ins and dispatcher
before stopping the guard unit, then reload systemd. Disable the Proton profile,
remove only `inet home_server_portable` and its two recorded endpoint routes,
and restore the previous network policy. Keep Netcup management until local
recovery is verified.

Restore the old macvlan Compose only on the original MikroTik network, with its
router protection and saved network identity in place. Never use
`docker compose down -v` to undo networking. The detailed rollback record covers
gateway and Mac restoration, deployment pinning, and encrypted archives.

References: [WireGuard keepalives](https://www.wireguard.com/quickstart/),
[NetworkManager WireGuard settings](https://networkmanager.dev/docs/api/latest/settings-wireguard.html),
[NetworkManager dispatcher](https://networkmanager.dev/docs/api/latest/NetworkManager-dispatcher.html),
[DNS priorities](https://networkmanager.dev/docs/api/latest/settings-ipv4.html),
[Proton WireGuard profiles](https://protonvpn.com/support/wireguard-configurations).
