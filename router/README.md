# MikroTik Proton VPN for the Pi

The hAP ax3 runs the WireGuard client. The Pi and its ordinary Docker bridge
containers use the router as their gateway. Komodo remains containerized and
deploys the existing Git-based Stacks. No Pi-side VPN service is required.

## Policy

| Component | Configuration |
| --- | --- |
| LAN | `bridge`, `192.168.88.0/24`, router `192.168.88.1` |
| Pi | DHCP reservation `192.168.88.250` for its active Ethernet MAC |
| Tunnel | `wg-proton-pi`, IPv4 address and peer from a dedicated Proton config |
| Routing | Exact LAN exception, then `lookup-only-in-table` in `proton-pi` |
| IPv4 guard | Pi IP and protected MAC jumps before FastTrack and established accepts; permit LAN/VPN, drop other routed egress |
| VPN replies | Accept established/related replies to the Pi before FastTrack; drop unsolicited ingress |
| DNS | Redirect routed TCP/UDP port 53 from the Pi to Proton; block router DNS fallback by MAC |
| IPv6 | Drop routed IPv6 from every protected Pi MAC before FastTrack6; block router DNS fallback |
| WAN | Existing wired/phone failover carries the router's tunnel transport |

The policy applies to all Pi services, including Plex, Komodo, and ngrok.
Same-subnet LAN communication remains local. The router itself and other LAN
devices retain their ordinary WAN routing. No inbound Proton port mapping or
NAT-PMP renewal is configured; Transmission can initiate outgoing connections.

The protection assumes the Pi uses the reserved address and known MACs through
this router. An unprotected Wi-Fi/USB/cellular uplink, macvlan container with a
different identity, changed MAC, or trusted LAN proxy needs separate protection.
Disable unused Pi interfaces. Existing protection also covers the Pi's previous
interface MAC, but only the active reserved address receives the VPN route.
Router-local DNS names do not resolve through redirected Proton DNS; use host
entries on the Pi if needed. Other LAN clients can still use router DNS.

## New-router installation

The [example script](mikrotik-proton-pi.rsc.example) targets the reviewed
RouterOS 7.18.2 default LAN/firewall layout. It is a one-time installation
template, not an updater or a general router provisioning script. **Do not
import it into the already configured router.** Its preflight intentionally
rejects an existing or partial installation. The committed template has not
been imported into a separate RouterOS test instance; always run the target
router's dry-run after filling it in.

1. Export/back up the router locally and keep that backup private. Use another
   LAN computer for configuration; disconnect every Pi uplink during setup.
2. Identify the active Pi interface with `/ip dhcp-server lease print detail`
   and `/ip arp print detail`. A lease marked bound can outlive a disconnected
   interface. Confirm the MAC from the Pi as well. Reserve `.250` for that MAC;
   resolve any existing reservation conflict before import.
3. Generate a dedicated Proton WireGuard configuration. Copy the example script
   to a private working file named `mikrotik-proton-pi.rsc`. Fill its placeholders:

   | Script variable | Proton file field |
   | --- | --- |
   | `protonAddress` | `[Interface] Address`, IPv4 with prefix |
   | `protonDNS` | `[Interface] DNS`, IPv4 |
   | `protonEndpoint` | `[Peer] Endpoint`, IP before the colon |
   | `protonPort` | `[Peer] Endpoint`, port after the colon |
   | `protonServerKey` | `[Peer] PublicKey` |
   | `piMAC` | Active Pi interface MAC; not from the Proton file |

4. Upload the working script through the router's Files page. Run each command
   separately in the MikroTik Terminal. The filename is on the router, not a
   Mac path such as `/private/tmp/...`.

   ```routeros
   /import file-name=mikrotik-proton-pi.rsc verbose=yes dry-run
   ```

   ```routeros
   /import file-name=mikrotik-proton-pi.rsc
   ```

5. After successful import, open **WireGuard → wg-proton-pi** in WebFig. Replace
   the interface's generated Private Key with `[Interface] PrivateKey` from the
   new Proton file, apply, then enable the interface. This step is manual; the
   import does not install your private key. Do not paste it into Git or chat.
   A file literally containing `PrivateKey = *****` is redacted and cannot be
   used; download a fresh usable configuration from Proton.
6. Confirm the peer has a recent `last-handshake` and increasing RX/TX:

   ```routeros
   /interface wireguard peers print detail where interface=wg-proton-pi
   ```

   The peer's empty `private-key` field is unrelated to the interface's key.
7. Commit Safe Mode changes if used, then reboot the router while the Pi remains
   disconnected to clear earlier FastTrack/NAT state. Reconnect only the
   protected Pi interface, verify `.250`, and complete the tests below before
   starting Transmission. An import error can leave partial changes; inspect
   them before retrying rather than disabling the protection.

## Verification and recovery

Keep SSH on the LAN and Transmission stopped while testing a new policy. On the
Pi, verify the physical route uses `192.168.88.1` and source `192.168.88.250`:

```sh
ip route get 1.1.1.1
```

Check the public IPv4 from the host and from a temporary container. The latter
uses the installed Transmission image but starts only curl, with no data mounts:

```sh
curl -4 --noproxy '*' --fail --max-time 15 https://ip.me
```

```sh
docker run --rm --pull=never --network portainer_network --entrypoint curl "$(docker inspect --format '{{.Image}}' torrent-client)" -4 --noproxy '*' --fail --max-time 15 https://ip.me
```

Both must show the verified Proton exit. To test without relying on DNS, first
confirm these succeed with WireGuard enabled:

```sh
curl -4 --noproxy '*' --fail --max-time 15 https://1.1.1.1/cdn-cgi/trace
```

```sh
docker run --rm --pull=never --network portainer_network --entrypoint curl "$(docker inspect --format '{{.Image}}' torrent-client)" -4 --noproxy '*' --fail --max-time 15 https://1.1.1.1/cdn-cgi/trace
```

Disable **only** `wg-proton-pi` in WebFig. Both literal-IP requests must now fail
to connect, while LAN SSH stays reachable. Re-enable the interface and confirm
both recover. Never disable the guard or allow WAN fallback for this test.

IPv6 must fail from both host and bridge, even while WireGuard is enabled:

```sh
curl -6 --noproxy '*' --fail --max-time 15 'https://[2606:4700:4700::1111]/cdn-cgi/trace'
```

```sh
docker run --rm --pull=never --network portainer_network --entrypoint curl "$(docker inspect --format '{{.Image}}' torrent-client)" -6 --noproxy '*' --fail --max-time 15 'https://[2606:4700:4700::1111]/cdn-cgi/trace'
```

A TLS or HTTP error alone does not prove blocking: there must be no connection.
Repeat egress and blocking checks after reboot and on the backup WAN. On
2026-10-18 the live host/container Proton egress, container tunnel-down blocking
and recovery, IPv6 failure, and Transmission web/RPC checks passed. Full reboot
and backup-WAN acceptance tests after the final migration remain outstanding.

If SSH stops working, check the DHCP reservation, active MAC, and link first.
An incomplete ARP entry on another LAN computer means it has not resolved the
Pi's MAC; a WireGuard handshake does not establish that the Pi is reachable.
Use `/interface bridge host print` (including `/interface`) to inspect the link.
If the tunnel fails, leave the kill switch enabled and repair the peer/interface
configuration through another LAN device. Restore backups from the local
console if necessary. See the root README for the Gluetun migration/rollback.

## Sources

- [Proton's MikroTik WireGuard setup](https://protonvpn.com/support/wireguard-mikrotik-routers)
- [RouterOS policy routing](https://help.mikrotik.com/docs/spaces/ROS/pages/59965508/Policy%2BRouting)
- [RouterOS packet flow and FastTrack](https://help.mikrotik.com/docs/spaces/ROS/pages/328227/Packet%2BFlow%2Bin%2BRouterOS)
