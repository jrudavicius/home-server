#!/usr/bin/env python3
"""Prepare inactive NetworkManager profiles; keys stay on the Pi."""

import argparse
import base64
import configparser
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import uuid


def key(value):
    if len(base64.b64decode(value, validate=True)) != 32:
        raise ValueError("WireGuard keys must contain 32 bytes")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--management-endpoint", required=True)
    parser.add_argument("--management-public-key", required=True)
    parser.add_argument("--proton-config", type=Path, required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Run as root on the Pi")
    endpoint = str(ipaddress.IPv4Address(args.management_endpoint))
    hub_key = key(args.management_public_key)
    proton = configparser.ConfigParser(interpolation=None, strict=True)
    proton.read(args.proton_config)
    if set(proton.sections()) != {"Interface", "Peer"}:
        raise ValueError("Expected one Proton interface and one peer")
    if set(proton["Interface"]) != {"privatekey", "address", "dns"}:
        raise ValueError("Review unrecognized Proton interface directives")
    if set(proton["Peer"]) != {"publickey", "allowedips", "endpoint"}:
        raise ValueError("Review unrecognized Proton peer directives")
    private_key = key(proton["Interface"]["PrivateKey"])
    proton_key = key(proton["Peer"]["PublicKey"])
    address = str(ipaddress.IPv4Interface(proton["Interface"]["Address"]))
    dns = str(ipaddress.IPv4Address(proton["Interface"]["DNS"]))
    proton_endpoint, proton_port = proton["Peer"]["Endpoint"].rsplit(":", 1)
    proton_endpoint = str(ipaddress.IPv4Address(proton_endpoint))
    proton_port = int(proton_port)
    if not 1 <= proton_port <= 65535 or proton["Peer"]["AllowedIPs"] != "0.0.0.0/0":
        raise ValueError("Expected an IPv4 full-tunnel Proton profile")
    folder = Path("/etc/NetworkManager/system-connections")
    paths = [folder / f"home-server-{name}.nmconnection" for name in ("netcup", "proton")]
    config_path = Path("/etc/home-server/portable-network.json")
    if any(path.exists() for path in paths + [config_path]):
        raise SystemExit("Portable profiles already exist; inspect them instead of replacing keys")
    management_private = subprocess.check_output(["wg", "genkey"], text=True).strip()
    management_public = subprocess.check_output(
        ["wg", "pubkey"], input=management_private, text=True,
    ).strip()

    def profile(name, private, public, endpoint, ips, address, mark, full):
        return f"""[connection]
id=home-server-{name}
uuid={uuid.uuid4()}
type=wireguard
interface-name=wg-{name}
autoconnect=false
autoconnect-retries=0

[wireguard]
private-key={private}
fwmark={mark}
mtu=1380
peer-routes=true
ip4-auto-default-route={1 if full else 0}

[wireguard-peer.{public}]
endpoint={endpoint}
persistent-keepalive=25
allowed-ips={ips};

[ipv4]
method=manual
address1={address}
never-default={'false' if full else 'true'}
""" + (f"dns={dns};\ndns-priority=-100\ndns-search=~.;\n" if full else "") + """
[ipv6]
method=disabled
"""

    contents = [
        profile("netcup", management_private, hub_key, endpoint + ":51820",
                "10.77.77.1/32;10.77.77.3/32", "10.77.77.2/32", 51822, False),
        profile("proton", private_key, proton_key, f"{proton_endpoint}:{proton_port}",
                "0.0.0.0/0", address, 51821, True),
    ]
    os.umask(0o077)
    config_path.parent.mkdir(mode=0o700, exist_ok=True)
    for path, content in zip(paths, contents):
        path.write_text(content)
    config_path.write_text(json.dumps({
        "uplinks": ["eth0", "wlan0"],
        "proton": {"interface": "wg-proton", "endpoint": proton_endpoint,
                   "port": proton_port, "mark": 51821},
        "management": {"interface": "wg-netcup", "endpoint": endpoint,
                       "port": 51820, "mark": 51822,
                       "clients": ["10.77.77.1", "10.77.77.3"]},
    }, indent=2) + "\n")
    subprocess.run(["nmcli", "connection", "load", *map(str, paths)], check=True)
    print("Inactive profiles prepared. Pi public key:", management_public)


if __name__ == "__main__":
    main()
