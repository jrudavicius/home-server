#!/usr/bin/env python3
"""Exercise the guard in isolated Linux namespaces; never changes host routes."""

import os
from pathlib import Path
import subprocess

import network


def run(*args, ok=True, **kwargs):
    return subprocess.run(args, check=ok, capture_output=True, text=True, **kwargs)


def main():
    if os.geteuid() != 0:
        raise SystemExit("Run as root on Linux; all test networking stays in temporary namespaces")
    prefix = f"hs-vpn-{os.getpid()}"
    pi, outside, app = (prefix + suffix for suffix in ("-pi", "-wan", "-app"))
    created = []
    servers = []
    checks = 0

    def ns(name, *args, **kwargs):
        return run("ip", "netns", "exec", name, *args, **kwargs)

    def ping(name, destination, expect=True):
        nonlocal checks
        result = ns(name, "ping", "-n", "-c", "1", "-W", "1", destination, ok=False)
        if (result.returncode == 0) != expect:
            raise AssertionError(f"{name}: ping {destination}, expected success={expect}")
        checks += 1

    def pair(left, left_if, left_ip, right, right_if, right_ip, suffix):
        first, second = f"hs{os.getpid()}{suffix}a", f"hs{os.getpid()}{suffix}b"
        run("ip", "link", "add", first, "type", "veth", "peer", "name", second)
        run("ip", "link", "set", first, "netns", left)
        run("ip", "link", "set", second, "netns", right)
        for name, old, new, address in ((left, first, left_if, left_ip), (right, second, right_if, right_ip)):
            ns(name, "ip", "link", "set", old, "name", new)
            ns(name, "ip", "address", "add", address, "dev", new)
            ns(name, "ip", "link", "set", new, "up")

    def echo(address, port):
        code = """import socket,sys
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.bind((sys.argv[1],int(sys.argv[2])))
print('ready',flush=True)
while True:
 data,peer=s.recvfrom(2048)
 s.sendto(data,peer)
"""
        proc = subprocess.Popen(
            ["ip", "netns", "exec", outside, "python3", "-u", "-c", code, address, str(port)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        servers.append(proc)
        if proc.stdout.readline().strip() != "ready":
            raise RuntimeError("Test UDP listener failed")

    def udp(name, address, port, mark=0, expect=True):
        nonlocal checks
        code = """import socket,sys
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.settimeout(0.7)
if int(sys.argv[3]): s.setsockopt(socket.SOL_SOCKET,socket.SO_MARK,int(sys.argv[3]))
s.sendto(b'guard-test',(sys.argv[1],int(sys.argv[2])))
try:
 data,peer=s.recvfrom(1024)
 sys.exit(0 if data==b'guard-test' else 2)
except TimeoutError: sys.exit(1)
"""
        result = ns(name, "python3", "-c", code, address, str(port), str(mark), ok=False)
        if (result.returncode == 0) != expect:
            raise AssertionError(f"{name}: UDP {address}:{port}, mark={mark}, expected success={expect}")
        checks += 1

    try:
        for name in (pi, outside, app):
            run("ip", "netns", "add", name)
            created.append(name)
            ns(name, "ip", "link", "set", "lo", "up")
        pair(pi, "eth0", "192.168.50.2/24", outside, "wan0", "192.168.50.1/24", "w")
        pair(pi, "br-test", "172.30.0.1/24", app, "eth0", "172.30.0.2/24", "a")
        pair(pi, "wg-proton", "10.2.0.2/24", outside, "vpn0", "10.2.0.1/24", "p")
        pair(pi, "wg-netcup", "10.77.77.2/24", outside, "mgmt0", "10.77.77.3/24", "m")
        for address in ("203.0.113.9/32", "192.0.2.10/32", "198.51.100.10/32"):
            ns(outside, "ip", "address", "add", address, "dev", "lo")
        ns(pi, "ip", "route", "add", "default", "via", "192.168.50.1")
        ns(app, "ip", "route", "add", "default", "via", "172.30.0.1")
        ns(pi, "sysctl", "-qw", "net.ipv4.ip_forward=1")
        ns(outside, "ip", "route", "add", "172.30.0.0/24", "via", "192.168.50.2")
        ns(pi, "ip", "-6", "address", "add", "fd00:50::2/64", "dev", "eth0", "nodad")
        ns(outside, "ip", "-6", "address", "add", "fd00:50::1/64", "dev", "wan0", "nodad")
        ns(outside, "ip", "-6", "address", "add", "2001:db8::9/128", "dev", "lo", "nodad")
        ns(pi, "ip", "-6", "route", "add", "default", "via", "fd00:50::1")
        for address, port in (("192.168.50.1", 53), ("192.0.2.10", 51820), ("198.51.100.10", 51820)):
            echo(address, port)
        ping(pi, "203.0.113.9")
        ping(app, "203.0.113.9")
        ping(pi, "2001:db8::9")
        udp(pi, "192.168.50.1", 53)

        import json
        config = json.loads((Path(__file__).parent / "portable-network.example.json").read_text())
        policy = network.render(config, ["192.168.50.0/24"])
        ns(pi, "/usr/sbin/nft", "-f", "-", input=policy)
        ping(pi, "203.0.113.9", False)
        ping(app, "203.0.113.9", False)
        ping(pi, "2001:db8::9", False)
        udp(pi, "192.168.50.1", 53, expect=False)
        udp(app, "192.168.50.1", 53, expect=False)
        ping(outside, "192.168.50.2")
        ping(outside, "10.77.77.2")
        udp(pi, "192.0.2.10", 51820, mark=51821)
        udp(pi, "192.0.2.10", 51820, expect=False)
        udp(pi, "198.51.100.10", 51820, mark=51822)
        udp(pi, "198.51.100.10", 51820, mark=51821, expect=False)

        ns(pi, "ip", "route", "add", "203.0.113.9/32", "via", "10.2.0.1")
        ns(outside, "ip", "route", "replace", "172.30.0.0/24", "via", "10.2.0.2")
        ping(pi, "203.0.113.9")
        ping(app, "203.0.113.9")
        ns(pi, "ip", "route", "del", "203.0.113.9/32")
        ns(pi, "ip", "link", "set", "wg-proton", "down")
        ns(outside, "ip", "route", "replace", "172.30.0.0/24", "via", "192.168.50.2")
        ping(pi, "203.0.113.9", False)
        ping(app, "203.0.113.9", False)
        ping(outside, "10.77.77.2")
        print(f"Passed {checks} isolated kernel checks: host/container egress, DNS, IPv6, marked transport, LAN and management")
    finally:
        for proc in servers:
            proc.terminate()
            proc.wait(timeout=5)
        for name in reversed(created):
            run("ip", "netns", "delete", name, ok=False)


if __name__ == "__main__":
    main()
