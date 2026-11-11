# Portable Pi: preservation, migration, and rollback

Recorded on 2026-11-11. The owner chose private access through the existing Netcup
WireGuard gateway, with the Pi connecting from either home, and required the
current setup to be documented and preserved before replacement.

**Status: portable networking deployed and reboot-tested.** Fresh Pi, application-volume, and native
Komodo backups were completed before changes; an encrypted off-Pi copy was
decrypted and checksum-verified. Private SSH and Komodo now work through the
Netcup gateway. A new Pi-specific Proton profile passes DNS and HTTPS checks;
the host and a representative container share its VPN exit IP. The host guard
and both tunnels are configured for startup. The Mac route is active; direct
private SSH and Komodo access passed. Transmission now uses the protected bridge;
its existing login and storage mounts were verified. The former public application
endpoint and empty macvlan were retired after successful outage and reboot tests.
The only public route is the signed coordinated GitHub deployment webhook.
The MikroTik is unchanged;
a fresh router backup is required before any future router edit.

## Preserved baseline

The tracked configuration is pinned by Git tag
[`pre-portable-pi-2026-11-11`](https://github.com/jrudavicius/home-server/tree/pre-portable-pi-2026-11-11),
which resolves to commit `080038dbc53faa44b4422e1a65a7295fe3f05e83`.
The tag was pushed and its remote commit verified. This is the inspected local
and published source revision. The root Pi checkout is actually at `0d5e981`,
with local `.gitignore` changes and untracked infrastructure-check code. Media,
entrypoint, and observability checkouts are at `080038d`; public-access is at
`0d5e981`. Complete checkouts and local changes were captured in the Pi archive.
The root checkout has not been replaced.

| Component | Baseline | Evidence and preservation status |
| --- | --- | --- |
| Source | Root Komodo Compose, four application stacks, resource definitions, pinned images, router documentation | Git tag, source tarball, and self-contained Git bundle saved; bundle verified |
| Pi | Previously documented `192.168.88.250`; now on another home's Wi-Fi with DHCP and NetworkManager | Live host configuration, all of `/etc`, network state, and deployed revisions captured |
| MikroTik | LAN `192.168.88.0/24`, gateway `192.168.88.1`, whole-home Proton policy and kill switch | Repository evidence only; fresh sensitive export, encrypted binary backup, and off-router copies pending |
| Transmission | LAN IP `192.168.88.9`, MAC `02:54:52:00:00:01`, external `transmission_lan` macvlan and internal `transmission_ui` bridge | Live Docker configuration, application state, secrets and Compose preserved; stopped before cutover |
| Public access | ngrok HTTPS webhook endpoint and HTTP Traefik endpoint | Source and private runtime configuration preserved |
| Netcup | Debian 13, `wg0` at `10.77.77.1/24`, UDP 51820, Mac peer `10.77.77.3/32`, IPv4 forwarding off, forwarding firewall drops all | Read live; private configuration archive created, checksum verified, and encrypted off-server copy decrypted successfully |
| Mac | WireGuard address `10.77.77.3/32`, routes only `10.77.77.1/32`, keepalive 25 seconds | Live VPS handshake observed; client configuration and keys archived, encrypted, and decrypted successfully |

Private endpoint details, exact archive paths, checksums, and key locations are
recorded in the private Notion rollback record and recovery directory manifest.
They are not committed to this public repository. The Netcup archive includes
WireGuard keys/configuration, SSH configuration and host keys, authorized keys,
firewall, sysctl, network, systemd and automatic-update configuration, earlier
gateway backups, and runtime/package inventories. It is not a VPS disk image.

Encrypted Netcup and Mac copies are on the owner's Mac, outside this worktree.
They can be decrypted with the separate recovery identity; decryption and
plaintext checksums were verified. The existing SSH key is an additional
recipient, but its passphrase-protected decryption was not verified unattended.
Keep a recoverable copy of an identity separately from the ciphertext. Transfer
to the preferred Proton Drive has not been performed; no Proton Drive connection
was available in this session.

The fresh Pi archive contains 6,511 members and 272,319,223 bytes. It includes
all Docker volume data copied while applications were stopped, the supported
Komodo database snapshot, SSH access files, private environments, application
configuration, and deployment inventories. Bulk media, transcode caches and
Docker image layers are excluded. This is not a full bootable disk image.
An independently running OS upgrade completed after the snapshot; rolling back
networking does not downgrade those packages. Exact paths and checksums are in
the private Notion record and local recovery manifests.

## Existing behavior to retain

The [router policy](../router/README.md) sends the whole LAN and router-originated
traffic through Proton, blocks direct ISP fallback, and preserves local LAN
access. Transmission has additional IP/MAC, DNS, and IPv6 guards. Its gateway and
DNS depend on the current MikroTik; copying Compose alone cannot restore them on
an arbitrary router.

The current router's whole-home protections also cover devices other than the
Pi. Keep those protections when making the Pi independent. The existing
`proton-home-rollback` router script intentionally restores direct ISP access for
other devices. **It is not the rollback procedure for this migration.**

Other identities and access paths that must be recorded include local
`*.home.arpa` DNS, the actual ngrok endpoints and GitHub webhook URL, Komodo
credentials/keys, Docker network identities, and storage mount paths.

## Baseline capture procedure

Use local access to the MikroTik network and a console recovery path for the Pi.
Keep archive directories private (directory mode 0700, files 0600) and outside
`/srv/komodo/backups`: Komodo prunes immediate subdirectories there.

1. **Record the live deployment.** Capture the Pi OS/kernel, hostname, addresses,
   routes/rules, active network manager, DNS, IPv4/IPv6 firewall, Docker versions,
   containers/image digests, network inspection, volume/bind-mount inventory,
   systemd overrides, and each deployed checkout's commit and local changes.
   Treat rendered Compose, environment files, and Docker inspection output as
   secret material. Record how the Pi currently gets its LAN address; the
   repository does not establish whether it is host-static or DHCP-reserved.
2. **Preserve Pi files and application configuration.** Save
   `/srv/komodo/bootstrap.env`, deployed stack environments and secrets, host
   network/firewall/DNS configuration, all existing WireGuard configuration,
   systemd overrides, and the `komodo-keys` volume. Capture the actual locations
   rather than assuming the documented defaults. Preserve Plex and Transmission
   configuration, including Transmission's password and resume/torrent state.
   Stop the relevant application briefly when its configuration requires a
   consistent filesystem snapshot. Record existing media/data storage and keep
   it in place; a network rollback must not erase application volumes or media.
3. **Back up Komodo through its supported interface.** Follow
   [Komodo backup and recovery](komodo-backups.md). Confirm the backup execution
   succeeded, then copy its complete snapshot and root `Stats.gz` outside the
   retention tree. A database snapshot omits external secrets, keys, and
   application volumes. Use the documented isolated restore procedure if a
   database restore becomes necessary; do not upsert an old snapshot into the
   live database merely to undo networking.
4. **Preserve the MikroTik.** Record model, serial, RouterOS/firmware versions,
   interface mapping, DHCP/DNS, routes/rules, firewall/NAT, IPv6, VPNs, scripts,
   schedulers, and disabled rollback entries. Create a full sensitive export to
   a private file and an encrypted binary backup with a separately retained
   password. Download both off the router, encrypt the sensitive export, and
   verify sizes/checksums. Preserve existing historical backup pairs as well.
   Text export omits some state, including system user passwords, installed
   certificates, and SSH keys, so it is not a substitute for the binary backup.
   Export any additional certificate/application state needed for recovery.
5. **Verify recovery material.** Decrypt the off-device copies and inspect their
   archive inventories. Record each required item as present or missing, the
   exact deployed commit, and all exclusions. A successful archive/decryption
   check is not a live restore test. Do not restore the router just to test a
   backup during preparation. Resume paused applications in their baseline
   state and record the baseline access, DNS, and Proton egress results.

Router references: [configuration export](https://manual.mikrotik.com/docs/getting-started/configuration-management/)
and [encrypted backup and restore](https://manual.mikrotik.com/docs/getting-started/configuration-management/backup/).

## Target layout and staged migration

Use the existing gateway and Mac identity. Reserve `10.77.77.2/32` for the Pi
after checking for conflicts. The Pi establishes an outbound WireGuard tunnel to
the Netcup public IP; the hub learns the Pi's current endpoint. The Pi must not
have a fixed home-public-IP endpoint configured on the hub. Keepalives maintain
the router's NAT mapping. See [WireGuard roaming](https://www.wireguard.com/)
and [persistent keepalives](https://www.wireguard.com/quickstart/).

1. **Add private management first.** After the baseline is complete, generate
   the Pi key on the Pi and add its public key to the hub. Use a distinct Pi
   interface such as `wg-netcup`; preserve the existing Mac peer. Allow only
   the required forwarding between the Mac address and Pi address on the hub,
   and enable IPv4 forwarding persistently. Extend the Mac's split routes to
   include the Pi address. Record exact added files, rules, and prior values.
   Keep the existing LAN/ngrok access available during validation. Netcup's
   provider firewall must permit the WireGuard UDP traffic in both directions;
   inspect its current policy before changing it.
2. **Move Pi egress protection onto the Pi.** Preserve Proton protection for
   normal Pi and container internet traffic, with a host-enforced kill switch
   and DNS/IPv6 policy. The Netcup management transport needs a narrowly scoped
   direct-uplink exception, so it can recover independently of Pi-side Proton.
   Update uplink routes when DHCP/interface state changes. If the MikroTik still
   sends all underlying traffic through Proton, independence from that router's
   Proton outage also requires a narrow router exception for the Pi-to-Netcup
   UDP endpoint; document and back up that exception separately.
3. **Remove the subnet dependency from Transmission.** Stop it before changing
   routing. Replace the LAN macvlan dependency with networking covered by the
   Pi's VPN enforcement, preserve its volumes/password, and keep the UI behind
   the private management path. Validate the no-VPN failure behavior before
   resuming transfers. A host firewall must not be assumed to protect macvlan
   traffic that bypasses its forwarding path.
4. **Make uplink configuration portable.** Use the destination router's DHCP
   information, with Wi-Fi profiles if needed. Keep management names tied to
   the stable VPN address. Preserve the old home profile for rollback. Avoid
   assuming the same interface, subnet, DNS server, or gateway at both homes.
5. **Retire superseded access only after validation.** Existing ngrok webhook
   delivery is a separate dependency: ordinary GitHub webhooks cannot reach a
   private-only VPN address. Preserve its configuration and provide a deliberate
   replacement before disabling that endpoint. Do not remove the MikroTik's
   protections for unrelated home devices.

The [portable host implementation](../host/portable/README.md) now uses the
Pi's existing NetworkManager service. Its firewall passed 20 isolated kernel
checks for host/container egress, DNS, IPv6, marked transports, and management
access during simulated tunnel failure. The full unit suite passed 28 tests.
A live Proton-disconnect test also blocked host and
representative container internet/DNS fallback while a fresh Netcup SSH session
and Komodo request succeeded. An automatic timer reactivated Proton after 35
seconds. The replacement Proton profile subsequently passed real host/container
DNS and HTTPS checks. The restricted webhook listener passed an isolated
Traefik/nginx test: only the exact deployment POST path reaches the backend;
administrative paths, other methods and traversal requests are rejected.
The final live test used the actual Transmission container: direct internet and
physical DNS were blocked during Proton failure, fresh Netcup SSH and Komodo
remained available, and Proton/Transmission recovered automatically. After reboot
to kernel `6.18.60+rpt-rpi-2712`, both tunnels, the guard and all application
containers returned with no failed systemd units. Landing page, Komodo, Grafana
and Plex pages were reachable from the Mac; Transmission required authentication
and its authenticated RPC succeeded. A real move between homes, Plex media
playback, full archive restoration and independent off-Mac storage remain untested.

Core and Periphery needed explicit Proton DNS because Docker retained the old
router resolver. Only those services were recreated from the existing root
checkout, preserving their current images/environment; its earlier local work
was retained. Application services use the corresponding explicit DNS settings
in Compose. Docker's daemon-wide configuration was not changed.

The old GitHub hook settings and macvlan definition were saved privately. The
five obsolete direct hooks are consolidated into the existing coordinated
Procedure route. Rollback must restore webhook settings together with matching
source and network configuration, rather than re-enabling stale deployment hooks
against the new source. GitHub does not return webhook secret values; use the
preserved Komodo webhook secret when recreating a matched hook.

Historical `codex/host-wide-vpn` and
`codex/harden-host-wide-vpn` branches are unmerged alternatives, not a known-good
rollback. Their installer applies lockdown early and is incompatible with the
current macvlan/deployment layout; do not run it unchanged.

## Acceptance checks before retiring the old path

- Reach the Pi's SSH and required dashboards from the Mac over WireGuard while
  keeping the existing route usable for recovery. Verify other public clients
  cannot use private forwarding.
- Reboot the Pi and restart the management tunnel; confirm automatic recovery.
- Test a genuinely different uplink/subnet and, if applicable, Wi-Fi. The Pi VPN
  address and service names must remain unchanged after reconnection.
- Verify ordinary Pi and representative container egress uses Proton. Test
  literal-IP traffic, DNS, and IPv6 while Proton is deliberately unavailable;
  protected traffic must fail and management must remain reachable through its
  documented exception. Arrange automatic restoration before this test.
- Confirm authenticated Transmission access/state, Plex playback, Komodo
  connectivity and backups, logging, and any retained public webhook delivery.
- Verify the router's other LAN clients retain their current Proton protection.

The earlier 2026-10-18 router outage test did not verify all of these; its limits
are recorded in [router verification](../router/README.md#verification).

## Rollback order

Take a fresh snapshot of the post-migration state before reverting, so new
application state and later changes remain recoverable. Use a maintenance window
with local Pi/router access and working public SSH or console access to Netcup.

1. Pause GitHub deployment triggers and Komodo scheduled/active deployment
   operations, then stop Transmission. Pin the deployed Repo/Resource Sync to
   the saved revision or otherwise prevent current `main` from immediately
   redeploying the new network. Keep identities and persistent data intact.
2. Reconnect the Pi to the original MikroTik network. Restore its saved host
   network, DNS, firewall, routing and service-startup configuration. Disable
   only the new VPN units and remove only migration-created files/rules recorded
   in the change manifest. Verify the original local management path before
   dropping the portable management tunnel.
3. Restore the matched baseline Compose files, private environments and Docker
   networks. Recreate `transmission_lan` only if absent, using the saved subnet,
   gateway, wired parent, IP and MAC. Preserve all application volumes and data;
   do not use `docker compose down -v`. Deploy entrypoint before media so the
   internal UI network and Traefik port 9091 ownership match the baseline.
4. If router changes were limited to the management exception, remove those
   recorded additions while retaining the original whole-home policy. If a full
   restore is necessary, use the saved binary backup on the same MikroTik with
   the recorded RouterOS version and local WinBox/console access. A binary
   restore can reboot the router and affect its whole LAN. Do not blindly import
   a full text export on top of an existing configuration.
5. Restore the Netcup configuration snapshot if the new Pi peer/forwarding is to
   be removed. Use public SSH or the Netcup console because VPN access may drop.
   Restore the saved `wg0` and nftables configuration; validate nftables before
   applying it. Remove only the added persistent-forwarding configuration and
   return IPv4 forwarding to the recorded baseline value (`0`). Preserve later
   unrelated changes through a reviewed diff. SSH hardening need not be reverted
   to undo Pi connectivity.
6. Restore the saved Mac `netcup.conf` if routes were changed. Bring the active
   tunnel down before replacing its config, then bring it up with the saved
   file. This baseline routes only the gateway address. Keep the matching
   WireGuard private key; changing identities would require changing the hub.
7. Verify the old LAN addresses/DNS, service login, Proton egress, DNS/IPv6 and
   kill-switch behavior, ngrok endpoints/webhooks, and backup schedule. Resume
   Transmission only after its protection is confirmed. Resume deployment
   triggers only when their source revision cannot undo the rollback.

## Recover source independently of the live checkout

To inspect the preserved revision without changing the working deployment:

```sh
git clone --branch pre-portable-pi-2026-11-11 \
  https://github.com/jrudavicius/home-server.git home-server-baseline
git -C home-server-baseline rev-parse HEAD
```

The result must be `080038dbc53faa44b4422e1a65a7295fe3f05e83`. If GitHub is
unavailable, clone the saved `repository-080038d.bundle` and select the same tag.
The bundle is self-contained. Neither source copy contains runtime private
environments, credentials, application data, or the live router configuration.

For encrypted files, verify `SHA256SUMS` in the private recovery directory, then
decrypt into a new private staging directory using `age --decrypt --identity`.
Use the identity and exact artifact filenames recorded in `manifest.json`.
Inspect staged files before applying any of them to a live system. Archive
verification and successful decryption have been tested. Live restoration has
not been tested; consult the status above for portable-network acceptance.
