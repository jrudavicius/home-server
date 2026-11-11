"""Portable routing input tests; live failure tests verify kernel enforcement."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("portable_network", ROOT / "host/portable/network.py")
network = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(network)


class PortableNetwork(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "host/portable/portable-network.example.json").read_text())

    def test_lan_moves_with_current_addresses_not_old_home(self):
        addresses = [{"ifname": "wlan0", "addr_info": [
            {"family": "inet", "scope": "global", "local": "192.168.0.156", "prefixlen": 24},
            {"family": "inet6", "scope": "link", "local": "fe80::1", "prefixlen": 64},
        ]}, {"ifname": "br-test", "addr_info": [
            {"family": "inet", "scope": "global", "local": "172.18.0.1", "prefixlen": 16},
        ]}]
        self.assertEqual(network.local_networks(addresses, ["eth0", "wlan0"]), ["192.168.0.0/24"])
        addresses[0]["addr_info"][0]["local"] = "192.168.88.250"
        self.assertEqual(network.local_networks(addresses, ["eth0", "wlan0"]), ["192.168.88.0/24"])

    def test_public_and_overbroad_dhcp_prefixes_do_not_bypass_vpn(self):
        for address, prefix in [("198.51.100.4", 24), ("192.168.0.4", 0), ("10.1.1.2", 7)]:
            with self.subTest(address=address, prefix=prefix):
                devices = [{"ifname": "eth0", "addr_info": [
                    {"family": "inet", "scope": "global", "local": address, "prefixlen": prefix},
                ]}]
                self.assertEqual(network.local_networks(devices, ["eth0"]), [])

    def test_overlapping_local_prefixes_are_collapsed(self):
        devices = [{"ifname": "eth0", "addr_info": [
            {"family": "inet", "scope": "global", "local": "192.168.0.1", "prefixlen": 16},
            {"family": "inet", "scope": "global", "local": "192.168.0.2", "prefixlen": 24},
        ]}]
        self.assertEqual(network.local_networks(devices, ["eth0"]), ["192.168.0.0/16"])

    def test_endpoint_uses_lowest_metric_physical_default(self):
        routes = [
            {"dst": "default", "dev": "wg-proton", "metric": 1},
            {"dst": "default", "dev": "wlan0", "gateway": "192.168.0.1", "metric": 600},
            {"dst": "default", "dev": "eth0", "gateway": "192.168.88.1", "metric": 100},
        ]
        self.assertEqual(network.uplink_route(routes, self.config["uplinks"])["dev"], "eth0")
        routes[2]["flags"] = ["linkdown"]
        self.assertEqual(network.uplink_route(routes, self.config["uplinks"])["dev"], "wlan0")
        self.assertIsNone(network.uplink_route(routes[:1], self.config["uplinks"]))

    def test_rejects_interfaces_that_could_inject_rules(self):
        for bad in ['eth0" accept', "br-*", "../eth0", "x" * 16]:
            with self.subTest(bad=bad):
                config = copy.deepcopy(self.config)
                config["uplinks"] = [bad]
                with self.assertRaises(ValueError):
                    network.validate(config)

    def test_rejects_tunnel_uplink_and_mark_collisions(self):
        for change in ("interface", "mark"):
            config = copy.deepcopy(self.config)
            config["management"][change] = config["proton"][change]
            with self.assertRaises(ValueError):
                network.validate(config)
        self.config["uplinks"] = ["wg-proton"]
        with self.assertRaises(ValueError):
            network.validate(self.config)

    def test_requires_numeric_ipv4_endpoints_and_exact_management_peers(self):
        for field, value in [("endpoint", "vpn.example.org"), ("endpoint", "::1"), ("port", 0), ("mark", 0)]:
            with self.subTest(field=field):
                config = copy.deepcopy(self.config)
                config["proton"][field] = value
                with self.assertRaises(ValueError):
                    network.validate(config)
        self.config["management"]["clients"] = ["0.0.0.0/0"]
        with self.assertRaises(ValueError):
            network.validate(self.config)


if __name__ == "__main__":
    unittest.main()
