"""Exercise Komodo's backup procedure and restore using the smoke test's fixtures."""

import gzip
import json
import time


# Runs inside the probe's Python 3.13, with fixture credentials supplied on stdin.
LOGIN_SCRIPT = '''
import json, sys, time, tomllib, urllib.error, urllib.request
data = json.load(sys.stdin)
def request(path, payload, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = token
    req = urllib.request.Request("http://control-plane:9120/" + path,
                                 json.dumps(payload).encode(), headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(path + ": " + error.read().decode()) from error
login = request("auth/login/LoginLocalUser", data["login"])
assert login["type"] == "Jwt", "Fixture login did not return a JWT"
token = login["data"]["jwt"]
'''


def login_data(credentials):
    return {'login': {'username': credentials['KOMODO_INIT_ADMIN_USERNAME'],
                      'password': credentials['KOMODO_INIT_ADMIN_PASSWORD']}}


def check_restored_login(run, credentials):
    run('exec', '-T', 'app-probe', 'python', '-c', LOGIN_SCRIPT,
        input=json.dumps(login_data(credentials)))


def check_backups(run, root, folder, credentials):
    # Use the probe's TOML and HTTP libraries; no host dependencies or ports.
    api_script = LOGIN_SCRIPT + '''
procedure = next(item for item in tomllib.loads(data["toml"])["procedure"]
                 if item["name"] == "Backup Core Database")
request("write/UpdateProcedure", {"id": procedure["name"], "config": procedure["config"]}, token)
items = request("read/ListProcedures", {}, token)
item = next(item for item in items if item["name"] == procedure["name"])
assert not item["info"].get("schedule_error"), item
assert item["info"]["next_scheduled_run"] > time.time() * 1000, item
update = request("execute/RunProcedure", {"procedure": procedure["name"]}, token)
for attempt in range(120):
    update = request("read/GetUpdate", {"id": update["_id"]["$oid"]}, token)
    if update["status"] == "Complete":
        assert update["success"], update
        break
    time.sleep(1)
else:
    raise AssertionError("Backup procedure did not finish")
print("Scheduled procedure parsed successfully and completed a database backup.")
'''
    data = login_data(credentials)
    data['toml'] = (root / 'komodo/procedures.toml').read_text()
    result = run('exec', '-T', 'app-probe', 'python', '-c', api_script, input=json.dumps(data))
    print(result.stdout.strip(), flush=True)

    def mongo(script):
        return run('exec', '-T', 'database', 'mongosh', '--quiet', '--eval', '''
const admin = db.getSiblingDB('admin');
if (admin.auth(process.env.MONGO_INITDB_ROOT_USERNAME,
               process.env.MONGO_INITDB_ROOT_PASSWORD).ok !== 1) { quit(1); }
''' + script).stdout.strip()

    # ObjectIds exercise the format consumed by Komodo's restore utility.
    mongo('''
db.getSiblingDB('komodo').BackupSmoke.insertOne({
  marker: 'restore-round-trip', value: 'special $ : / @ characters', generation: 1
});
''')
    # The fixture has retention=2. Take two more snapshots in distinct seconds
    # to exercise actual pruning, including the snapshot made by the Procedure.
    for _ in range(2):
        time.sleep(1.1)
        run('exec', '-T', 'control-plane', 'km', 'database', 'backup', '--yes')
    exported = folder / 'exported-backups'
    run('cp', 'control-plane:/backups/.', str(exported))
    snapshots = sorted(path for path in exported.iterdir() if path.is_dir())
    assert len(snapshots) == 2, snapshots
    snapshot = snapshots[-1]
    expected = {}
    for path in snapshot.glob('*.gz'):
        with gzip.open(path, 'rt') as archive:
            expected[path.stem] = [json.loads(line) for line in archive if line.strip()]
    assert expected['User'], 'Backup contains no users'
    assert expected['Procedure'], 'Backup contains no procedures'
    assert expected['BackupSmoke'][0]['marker'] == 'restore-round-trip'
    print('Retention keeps two snapshots; compressed documents are readable.', flush=True)

    # Restore while the actual Core is stopped, using a one-off container with
    # the documented target credentials. A fresh name avoids merging old data.
    target = 'komodo_restore_smoke'
    assert json.loads(mongo('JSON.stringify(db.getSiblingDB(' + json.dumps(target) +
                            ').getCollectionNames())')) == []
    run('stop', 'host-agent', 'control-plane')
    run('up', '-d', '--wait', 'database')
    run('run', '--rm', '--no-deps', '-T', 'secret-bootstrap')
    restored = run('run', '--rm', '--no-deps', '-T', '--entrypoint', 'sh',
                  '-e', 'RESTORE_FOLDER=' + snapshot.name,
                  '-e', 'KOMODO_CLI_DATABASE_TARGET_DB_NAME=' + target,
                  'control-plane', '-ec', '''
export KOMODO_CLI_DATABASE_TARGET_ADDRESS="$KOMODO_DATABASE_ADDRESS"
export KOMODO_CLI_DATABASE_TARGET_USERNAME="$KOMODO_DATABASE_USERNAME"
export KOMODO_CLI_DATABASE_TARGET_PASSWORD="$KOMODO_DATABASE_PASSWORD"
exec km database restore --restore-folder "$RESTORE_FOLDER" --yes
''')
    # v2.3.3 can log per-collection failures yet exit successfully. Verify data,
    # not only the process exit code, before considering recovery successful.
    assert 'ERROR' not in restored.stdout + restored.stderr, restored.stdout + restored.stderr
    counts = json.loads(mongo('''
const restored = db.getSiblingDB('komodo_restore_smoke');
JSON.stringify(Object.fromEntries(restored.getCollectionNames().map(
  name => [name, restored.getCollection(name).countDocuments({})]
)))
'''))
    for collection, documents in expected.items():
        assert counts.get(collection, 0) == len(documents), (collection, counts)
    record = json.loads(mongo('''
JSON.stringify(db.getSiblingDB('komodo_restore_smoke').BackupSmoke.findOne(
  {marker: 'restore-round-trip'}, {_id: 0}
))
'''))
    assert record == {'marker': 'restore-round-trip',
                      'value': 'special $ : / @ characters', 'generation': 1}, record
    print('Restore into a fresh database preserves every collection count and fixture payload.', flush=True)
    return target
