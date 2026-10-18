"""Verify native alert configuration and delivery using disposable Core state."""

import json

from management_backup_checks import LOGIN_SCRIPT, login_data


def check_alerts(run, root, credentials):
    script = LOGIN_SCRIPT + '''
server = tomllib.loads(data["servers"])["server"][0]
before = request("read/GetServer", {"server": server["name"]}, token)
request("write/UpdateServer", {"id": server["name"], "config": server["config"]}, token)
after = request("read/GetServer", {"server": server["name"]}, token)
assert before["info"]["public_key"] == after["info"]["public_key"]
assert before["config"]["address"] == after["config"]["address"]
assert all(after["config"][key] == value for key, value in server["config"].items())
print("Server health thresholds applied while preserving connection settings and key metadata.")

alerter = tomllib.loads(data["alerters"])["alerter"][0]
assert not alerter["config"]["enabled"], "Production delivery must remain opt-in"
request("write/CreateAlerter", {"name": alerter["name"], "config": alerter["config"]}, token)
request("write/UpdateAlerter", {"id": alerter["name"], "config": {"enabled": True}}, token)
try:
    update = request("execute/TestAlerter", {"alerter": alerter["name"]}, token)
    for attempt in range(60):
        update = request("read/GetUpdate", {"id": update["_id"]["$oid"]}, token)
        if update["status"] == "Complete":
            assert update["success"], update
            break
        time.sleep(1)
    else:
        raise AssertionError("Alerter test did not finish")
    from pathlib import Path
    payloads = Path("/tmp/notifications.jsonl").read_text()
    assert alerter["name"] in payloads, payloads
    print("Komodo resolved the private webhook secret and delivered to the local Discord receiver.")
finally:
    request("write/UpdateAlerter", {"id": alerter["name"], "config": {"enabled": False}}, token)
'''
    data = login_data(credentials)
    data.update(servers=(root / 'komodo/servers.toml').read_text(),
                alerters=(root / 'komodo/alerters.toml').read_text())
    result = run('exec', '-T', 'app-probe', 'python', '-c', script, input=json.dumps(data))
    print(result.stdout.strip(), flush=True)
