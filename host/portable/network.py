#!/usr/bin/env python3
"""Keep the Pi's VPN guard and endpoint routes independent of its home subnet."""

import argparse
import fcntl
import ipaddress
import json
from pathlib import Path
import re
import subprocess


TABLE = "home_server_portable"
ROUTE_PROTOCOL = "242"
CONFIG = Path("/etc/home-server/portable-network.json")
PRIVATE_LANS = tuple(ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
))


def interface(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", value):
        raise ValueError("Invalid interface name")
    return value


def validate(config):
    uplinks = config["uplinks"]
    if not uplinks or len(set(uplinks)) != len(uplinks):
        raise ValueError("Distinct physical uplinks are required")
    for name in uplinks:
        interface(name)
    tunnel_names = []
    marks = []
    for name in ("proton", "management"):
        tunnel = config[name]
        tunnel_names.append(interface(tunnel["interface"]))
        ipaddress.IPv4Address(tunnel["endpoint"])
        if type(tunnel["port"]) is not int or not 1 <= tunnel["port"] <= 65535:
            raise ValueError("Invalid endpoint port")
        if type(tunnel["mark"]) is not int or not 1 <= tunnel["mark"] <= 0xFFFFFFFF:
            raise ValueError("A nonzero transport mark is required")
        marks.append(tunnel["mark"])
    if len(set(tunnel_names)) != 2 or set(uplinks) & set(tunnel_names):
        raise ValueError("Physical and tunnel interfaces must be distinct")
    if len(set(marks)) != 2:
        raise ValueError("Tunnel marks must be distinct")
    clients = config["management"]["clients"]
    if not clients:
        raise ValueError("At least one management peer is required")
    for client in clients:
        ipaddress.IPv4Address(client)
    return config


def local_networks(addresses, uplinks):
    """Only current on-link private LANs receive local-access exceptions."""
    result = set()
    for device in addresses:
        if device["ifname"] not in uplinks:
            continue
        for address in device.get("addr_info", []):
            if address.get("family") != "inet" or address.get("scope") != "global":
                continue
            net = ipaddress.ip_network(
                f'{address["local"]}/{address["prefixlen"]}', strict=False,
            )
            if any(net.subnet_of(private) for private in PRIVATE_LANS):
                result.add(net)
    return [str(n) for n in ipaddress.collapse_addresses(sorted(result))]


def uplink_route(routes, uplinks):
    candidates = [r for r in routes if r.get("dst") == "default"
                  and r.get("dev") in uplinks and "linkdown" not in r.get("flags", [])
                  and r.get("type", "unicast") == "unicast"]
    if not candidates:
        return None
    route = min(candidates, key=lambda r: (r.get("metric", 0), r["dev"]))
    if route.get("gateway"):
        ipaddress.IPv4Address(route["gateway"])
    return route


def render(config, lans):
    validate(config)
    for lan in lans:
        ipaddress.IPv4Network(lan)
    uplinks = ", ".join(json.dumps(n) for n in config["uplinks"])
    clients = ", ".join(config["management"]["clients"])
    lan_elements = "elements = { " + ", ".join(lans) + " };" if lans else ""
    proton = json.dumps(config["proton"]["interface"])
    management = json.dumps(config["management"]["interface"])
    transports = []
    for name in ("proton", "management"):
        t = config[name]
        transports.append(
            f'        oifname @uplinks ip daddr {t["endpoint"]} '
            f'meta mark {t["mark"]} udp dport {t["port"]} accept'
        )
    forwards = []
    for bridge in ('"docker0"', '"br-*"'):
        forwards += [
            f"        iifname {bridge} oifname {proton} accept",
            f"        iifname {proton} oifname {bridge} ct state established,related accept",
            f"        iifname {management} ip saddr @management4 oifname {bridge} accept",
            f"        iifname {bridge} oifname {management} ip daddr @management4 ct state established,related accept",
            f"        iifname @uplinks ip saddr @lan4 oifname {bridge} accept",
            f"        iifname {bridge} oifname @uplinks ip daddr @lan4 ct state established,related accept",
        ]
        for other in ('"docker0"', '"br-*"'):
            forwards.append(f"        iifname {bridge} oifname {other} accept")
    return f'''table inet {TABLE} {{
    set uplinks {{ type ifname; elements = {{ {uplinks} }}; }}
    set lan4 {{ type ipv4_addr; flags interval; {lan_elements} }}
    set management4 {{ type ipv4_addr; elements = {{ {clients} }}; }}
    chain output {{
        type filter hook output priority -10; policy drop;
        oifname "lo" accept
        oifname {proton} accept
        oifname {management} ip daddr @management4 accept
        oifname "docker0" accept
        oifname "br-*" accept
{chr(10).join(transports)}
        oifname @uplinks udp sport 68 udp dport 67 accept
        oifname @uplinks meta l4proto {{ tcp, udp }} th dport 53 counter drop
        oifname @uplinks ip daddr @lan4 accept
        counter drop
    }}
    chain forward {{
        type filter hook forward priority -10; policy drop;
        oifname @uplinks meta l4proto {{ tcp, udp }} th dport 53 counter drop
{chr(10).join(forwards)}
        counter drop
    }}
}}
'''


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs)


def refresh(config):
    addresses = json.loads(run(["ip", "-j", "address", "show"]).stdout)
    routes = json.loads(run(["ip", "-j", "-4", "route", "show", "table", "main", "default"]).stdout)
    policy = render(config, local_networks(addresses, config["uplinks"]))
    exists = subprocess.run(
        ["/usr/sbin/nft", "list", "table", "inet", TABLE], capture_output=True,
    ).returncode == 0
    # Delete and create occur in one atomic nftables transaction, never a flush.
    if exists:
        policy = f"delete table inet {TABLE}\n" + policy
    run(["/usr/sbin/nft", "--check", "-f", "-"], input=policy)
    run(["/usr/sbin/nft", "-f", "-"], input=policy)
    route = uplink_route(routes, config["uplinks"])
    if route:
        for name in ("proton", "management"):
            args = ["ip", "-4", "route", "replace", config[name]["endpoint"] + "/32"]
            if route.get("gateway"):
                args += ["via", route["gateway"]]
            args += ["dev", route["dev"], "proto", ROUTE_PROTOCOL, "table", "main"]
            run(args)
    print("VPN guard active; endpoint routes " + ("updated" if route else "waiting for an uplink"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("refresh", "render"))
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()
    config = validate(json.loads(args.config.read_text()))
    if args.action == "render":
        print(render(config, []), end="")
        return
    with open("/run/lock/home-server-network.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        refresh(config)


if __name__ == "__main__":
    main()
