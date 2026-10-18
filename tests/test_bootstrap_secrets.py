import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/render_komodo_secrets.py"
spec = importlib.util.spec_from_file_location("bootstrap", SCRIPT)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class BootstrapSecretsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.output = self.folder / "private/core.config.json"
        self.values = {name: "test-only-" + name.lower() for name in bootstrap.REQUIRED}

    def run_bootstrap(self, values):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, values, clear=True), patch.object(
            sys, "argv", [str(SCRIPT), "--output", str(self.output)]
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = bootstrap.main()
        return code, stdout.getvalue(), stderr.getvalue()

    def test_rerun_replaces_values_privately_without_logging_them(self):
        for value in ("first-test-password", "replacement-test-password"):
            self.values["GRAFANA_ADMIN_PASSWORD"] = value
            code, stdout, stderr = self.run_bootstrap(self.values)
            self.assertEqual(code, 0, stderr)
            self.assertNotIn(value, stdout + stderr)
            config = json.loads(self.output.read_text())
            self.assertEqual(json.loads(config["secrets"]["GRAFANA_ADMIN_PASSWORD"]), value)
            self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(self.output.parent.stat().st_mode), 0o700)
            self.assertEqual(list(self.output.parent.iterdir()), [self.output])

    def test_missing_or_blank_values_preserve_previous_config(self):
        self.assertEqual(self.run_bootstrap(self.values)[0], 0)
        previous = self.output.read_bytes()
        for name in bootstrap.REQUIRED:
            for invalid in (None, "", "   "):
                with self.subTest(name=name, invalid=invalid):
                    values = self.values.copy()
                    if invalid is None:
                        values.pop(name)
                    else:
                        values[name] = invalid
                    code, stdout, stderr = self.run_bootstrap(values)
                    self.assertEqual(code, 1)
                    self.assertIn(name, stderr)
                    for value in self.values.values():
                        self.assertNotIn(value, stdout + stderr)
                    self.assertEqual(self.output.read_bytes(), previous)

    def test_rejects_multiline_credentials_without_creating_output(self):
        for name in bootstrap.REQUIRED + bootstrap.OPTIONAL:
            with self.subTest(name=name):
                values = dict(self.values, **{name: "private-value\nINJECTED=yes"})
                code, stdout, stderr = self.run_bootstrap(values)
                self.assertEqual(code, 1)
                self.assertIn(name, stderr)
                self.assertNotIn("private-value", stdout + stderr)
                self.assertFalse(self.output.exists())

    def test_only_application_secrets_are_exported_and_plex_can_be_empty(self):
        values = dict(self.values, KOMODO_DATABASE_PASSWORD="do-not-export")
        config = bootstrap.core_config(values)
        self.assertEqual(set(config), {"secrets"})
        self.assertEqual(set(config["secrets"]), set(bootstrap.REQUIRED + bootstrap.OPTIONAL))
        self.assertEqual(config["secrets"]["PLEX_CLAIM"], '""')
        self.assertNotIn("do-not-export", json.dumps(config))

    def test_failed_atomic_replace_preserves_previous_config_and_cleans_up(self):
        bootstrap.write_config(bootstrap.core_config(self.values), self.output)
        previous = self.output.read_bytes()
        with patch.object(bootstrap.os, "replace", side_effect=OSError("write failed")):
            code, _, stderr = self.run_bootstrap(self.values)
        self.assertEqual(code, 1)
        self.assertIn("volume permissions", stderr)
        self.assertEqual(self.output.read_bytes(), previous)
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI is required")
    def test_special_characters_survive_compose_bootstrap_and_stack_env(self):
        # These are fixtures only. No daemon or containers are needed.
        values = dict(
            self.values,
            GRAFANA_ADMIN_USER="space # quote' double\" slash\\ ž🔑",
            GRAFANA_ADMIN_PASSWORD="literal${UNSET}$$\\'\"#=ends\\",
            PLEX_CLAIM="claim-test-only",
        )
        compose = self.folder / "compose.yml"
        compose.write_text("services:\n  check:\n    image: busybox\n")
        env_file = self.folder / "check.env"
        process_env = {name: value for name, value in os.environ.items()
                       if name not in values and not name.startswith("COMPOSE_")}

        def resolve(contents):
            env_file.write_text(contents, encoding="utf-8")
            result = subprocess.run(
                ["docker", "compose", "--project-name", "bootstrap-tests",
                 "--env-file", str(env_file), "-f", str(compose),
                 "config", "--environment"],
                env=process_env, text=True, capture_output=True, check=True,
            )
            return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)

        # First parse the Pi's bootstrap file using Compose's dotenv syntax.
        source = "\n".join(name + "=" + json.dumps(value, ensure_ascii=False).replace("$", "$$")
                           for name, value in values.items())
        resolved = resolve(source)
        self.assertEqual({name: resolved[name] for name in values}, values)

        # Komodo preserves the generated quotes when substituting [[NAME]].
        config = bootstrap.core_config(resolved)
        interpolated = "\n".join(name + "=" + value
                                 for name, value in config["secrets"].items())
        # Its key/value parser removes inline comments even inside quotes.
        written = "\n".join(line.split(" #", 1)[0].strip()
                            for line in interpolated.splitlines())
        process_env["KOMODO_BOOTSTRAP_EMPTY"] = "must-not-appear-in-the-password"
        deployed = resolve(written)
        self.assertEqual({name: deployed[name] for name in values}, values)


if __name__ == "__main__":
    unittest.main()
