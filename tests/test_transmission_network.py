"""Deployment invariants; these do not replace the live router acceptance tests."""

import json
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


def compose_config(stack):
    directory = ROOT / "stacks" / stack
    # Do not let an operator's shell override the committed example settings.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("TRANSMISSION_", "PLEX_", "MEDIA_", "TRANSCODE_"))}
    result = subprocess.run(
        ["docker", "compose", "--env-file", str(directory / ".env.example"),
         "-f", str(directory / "docker-compose.yml"), "config", "--format", "json"],
        check=True, capture_output=True, text=True, env=env,
    )
    return json.loads(result.stdout)


class TransmissionNetworking(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media = compose_config("media")
        cls.entrypoint = compose_config("entrypoint")
        cls.tx = cls.media["services"]["torrent-client"]
        cls.proxy = cls.entrypoint["services"]["reverse-proxy"]

    def test_no_vpn_container_or_shared_namespace(self):
        self.assertEqual(set(self.media["services"]), {"streaming-server", "torrent-client"})
        self.assertNotIn("network_mode", self.tx)
        self.assertFalse(self.tx.get("depends_on"))
        self.assertNotIn("wireguard_config", self.media.get("secrets", {}))

    def test_transmission_has_only_protected_egress_and_internal_ui(self):
        self.assertEqual(set(self.tx["networks"]), {"transmission_lan", "transmission_ui"})
        lan = self.tx["networks"]["transmission_lan"]
        self.assertEqual(lan["ipv4_address"], "192.168.88.9")
        self.assertEqual(lan["mac_address"], "02:54:52:00:00:01")
        self.assertGreater(lan["gw_priority"], self.tx["networks"]["transmission_ui"].get("gw_priority", 0))
        self.assertFalse(self.tx.get("ports"))

    def test_networks_must_exist_before_transmission_starts(self):
        for name in ("transmission_lan", "transmission_ui"):
            network = self.media["networks"][name]
            self.assertTrue(network["external"])
            self.assertEqual(network["name"], name)

    def test_ui_network_cannot_supply_internet_gateway(self):
        ui = self.entrypoint["networks"]["transmission_ui"]
        self.assertEqual(ui["name"], self.media["networks"]["transmission_ui"]["name"])
        self.assertTrue(ui["internal"])
        self.assertFalse(ui["enable_ipv6"])
        self.assertEqual(set(self.proxy["networks"]), {"default", "transmission_ui"})

    def test_dns_and_ipv6_cannot_use_host_defaults(self):
        self.assertEqual(self.tx["dns"], ["10.2.0.1"])
        for scope in ("all", "default"):
            self.assertEqual(self.tx["sysctls"][f"net.ipv6.conf.{scope}.disable_ipv6"], "1")

    def test_web_port_owned_only_by_traefik(self):
        owners = []
        for config in (self.media, self.entrypoint):
            for service, settings in config["services"].items():
                for port in settings.get("ports", []):
                    if str(port.get("published")) == "9091":
                        owners.append(service)
        self.assertEqual(owners, ["reverse-proxy"])
        self.assertIn("--entrypoints.torrent-client.address=:9091", self.proxy["command"])
        routes = (ROOT / "stacks/entrypoint/traefik/dynamic.yml").read_text()
        self.assertIn('url: "http://media-torrent-client:9091"', routes)
        self.assertIn("torrent-client-direct:", routes)
        self.assertNotIn("media-vpn", routes)

    def test_plex_remains_on_ordinary_network(self):
        plex = self.media["services"]["streaming-server"]
        self.assertEqual(set(plex["networks"]), {"default"})
        self.assertEqual(self.media["networks"]["default"]["name"], "portainer_network")

    def test_missing_identity_fails_configuration(self):
        directory = ROOT / "stacks/media"
        env = os.environ.copy()
        env["TRANSMISSION_LAN_IP"] = ""
        result = subprocess.run(
            ["docker", "compose", "--env-file", str(directory / ".env.example"),
             "-f", str(directory / "docker-compose.yml"), "config", "--quiet"],
            capture_output=True, text=True, env=env,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("TRANSMISSION_LAN_IP", result.stderr)


if __name__ == "__main__":
    unittest.main()
