"""Configure the scoped database issuer and the agent identity in this demo."""
import base64
import fcntl
import getpass
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.umask(0o077)
ENV = dict(line.split("=", 1) for line in Path(".env").read_text().splitlines() if line)
BASE = "https://127.0.0.1:" + os.environ.get("BAO_PORT", ENV["BAO_PORT"]) + "/v1/"
TLS = ssl.create_default_context(cafile="local/ca.crt")
ROLE_PATH = "auth/approle/role/monitor/"
IDENTITY = Path("local/approle")


def request(token, path, data=None, *, method=None, missing_ok=False):
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    req = urllib.request.Request(BASE + path, body, headers, method=method)
    try:
        with urllib.request.urlopen(req, context=TLS, timeout=15) as res:
            return json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as exc:
        if missing_ok and exc.code == 404:
            return None
        # Endpoints can echo request fields in errors. Keep sensitive data off the terminal.
        raise SystemExit(f"OpenBao returned HTTP {exc.code} at {path}. Check unseal status, operator permissions, and the database connection.") from None


def admin_sql(sql):
    subprocess.run(
        ["docker", "compose", "exec", "-T", "--user", "postgres", "monitor-db",
         "psql", "-Xq", "-v", "ON_ERROR_STOP=1", "-d", "telemetry"],
        input=sql, text=True, check=True, stdout=subprocess.DEVNULL,
    )


def save_private(path, value):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        tmp.write((value + "\n").encode())
        if path.parent == IDENTITY and os.geteuid() == 0:
            os.fchown(tmp.fileno(), int(ENV["RUN_UID"]), int(ENV["RUN_GID"]))
    os.replace(tmp.name, path)


def replace_secret_id(token):
    active = IDENTITY / "secret-id"
    retiring = Path("local/retiring-secret-id")
    previous = active.read_text().strip() if active.exists() else None
    if previous and not retiring.exists():
        save_private(retiring, previous)
    old_id = retiring.read_text().strip() if retiring.exists() else None
    if previous == old_id:
        new_id = request(token, ROLE_PATH + "secret-id", {})["data"]["secret_id"]
        save_private(active, new_id)
    if old_id:
        request(token, ROLE_PATH + "secret-id/destroy", {"secret_id": old_id}, missing_ok=True)
        retiring.unlink()


def main():
    if sys.argv[1:] not in ([], ["--replace-secret-id"]):
        raise SystemExit("Usage: python3 provision.py [--replace-secret-id]")
    token = getpass.getpass("OpenBao operator token (hidden): ") if sys.stdin.isatty() else sys.stdin.readline().strip()
    if not token:
        raise SystemExit("An OpenBao operator token is required.")
    if "--replace-secret-id" in sys.argv:
        if not (IDENTITY / "role-id").exists():
            raise SystemExit("Run the initial provisioning first.")
        replace_secret_id(token)
        print("Replaced the agent's bootstrap SecretID.")
        return
    mounts = request(token, "sys/mounts")["data"]
    if "database/" not in mounts:
        request(token, "sys/mounts/database", {"type": "database"})
    if "approle/" not in request(token, "sys/auth")["data"]:
        request(token, "sys/auth/approle", {"type": "approle"})

    admin_sql(Path("database.sql").read_text())
    policy = 'length = 32\nrule "charset" { charset = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" }'
    request(token, "sys/policies/password/monitor-db", {"policy": base64.b64encode(policy.encode()).decode()})
    if request(token, "database/config/telemetry", missing_ok=True) is None:
        issuer_password = secrets.token_hex(32)
        admin_sql(f"ALTER ROLE bao_issuer PASSWORD '{issuer_password}';")
        request(token, "database/config/telemetry", {
            "plugin_name": "postgresql-database-plugin",
            "connection_url": "postgresql://{{username}}:{{password}}@monitor-db:5432/telemetry?sslmode=verify-full&sslrootcert=/tls/current/ca.crt",
            "allowed_roles": ["monitor"], "username": "bao_issuer",
            "password": issuer_password, "password_policy": "monitor-db",
        })
    request(token, "database/roles/monitor", {
        "db_name": "telemetry", "default_ttl": "90s", "max_ttl": "90s",
        "creation_statements": [
            """CREATE ROLE "{{name}}" LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'""",
            """GRANT monitor_reader TO "{{name}}" """,
        ],
        "renew_statements": ["""ALTER ROLE "{{name}}" VALID UNTIL '{{expiration}}'"""],
        "revocation_statements": [
            """ALTER ROLE "{{name}}" NOLOGIN""",
            """SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = '{{name}}'""",
            """DROP ROLE IF EXISTS "{{name}}" """,
        ],
    })
    request(token, "sys/policies/acl/monitor", {
        "policy": 'path "database/creds/monitor" { capabilities = ["read"] }',
    })
    request(token, "auth/approle/role/monitor", {
        "token_policies": ["monitor"], "token_ttl": "20m", "token_max_ttl": "1h",
        "secret_id_ttl": "7d", "secret_id_num_uses": 0, "token_type": "service",
    })
    save_private(IDENTITY / "role-id", request(token, ROLE_PATH + "role-id")["data"]["role_id"])
    if not (IDENTITY / "secret-id").exists() or Path("local/retiring-secret-id").exists():
        replace_secret_id(token)
    print("Configured the monitor role and identity. The monitor can read one table.")


if __name__ == "__main__":
    with Path("local/operator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        main()
