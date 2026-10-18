# Komodo backups and recovery

The Git-managed **Backup Core Database** Procedure runs every day at **01:00
Europe/Vilnius**, using Komodo's native `BackupCoreDatabase` execution. It reuses
the name of Komodo's default Procedure so Resource Sync updates that resource.
It has no webhook, suppresses routine schedule alerts, and enables failure
alerts. Check its last successful run in Komodo; external notifications require
a configured Alerter. Core must be running at the scheduled time.

Core writes snapshots to `/backups`, mounted from `KOMODO_BACKUPS_PATH` (default
`/srv/komodo/backups`). `KOMODO_CLI_MAX_BACKUPS` explicitly defaults to **14
snapshots**, including manual backups. This is a count, not a number of days.
Pruning runs after a successful backup. Zero disables pruning.

## Enable and verify

1. From a host terminal in the updated repository checkout, create a private
   backup directory. Substitute your path if `KOMODO_BACKUPS_PATH` differs:

   ```sh
   sudo install -d -m 700 /srv/komodo/backups
   docker compose --env-file /srv/komodo/bootstrap.env up -d
   ```

2. Once the configuration is available on `main`, manually run
   `home-server-resources` while the backup Procedure is idle. Confirm **Backup
   Core Database** has the daily schedule, Vilnius timezone, and a valid next
   run. If an older backup Procedure was renamed, disable its schedule to avoid
   duplicate jobs; Resource Sync deliberately does not delete extra resources.
3. Run **Backup Core Database** once in Komodo and check that the execution
   succeeds. A host-terminal alternative uses the same CLI as the execution:

   ```sh
   docker compose --env-file /srv/komodo/bootstrap.env exec -T control-plane km database backup --yes
   sudo ls -la /srv/komodo/backups
   ```

   Expect a timestamped directory containing compressed collection files such
   as `User.gz`, `Procedure.gz`, and `Stack.gz`. A directory alone does not prove
   that a backup completed; check the execution result and logs.

Keep only Komodo database snapshots in this directory. Komodo's pruner treats
all immediate subdirectories as backup candidates. Store keys, bootstrap files,
and other recovery material elsewhere.

## What to preserve off-host

Database snapshots contain Komodo users, resources, variables, and credentials
stored in MongoDB. They do not include Docker application data, files referenced
by configuration, or Core/Periphery key files. Historical server metrics use a
single rolling `Stats.gz` at the backup root, outside the dated snapshots.

Use an encrypted backup destination on another machine or storage service for:

| Source | Recovery purpose |
| --- | --- |
| `/srv/komodo/backups/` (or `KOMODO_BACKUPS_PATH`) | Successful dated snapshots and the top-level `Stats.gz`. |
| `/srv/komodo/bootstrap.env` | Database credentials, admin bootstrap settings, JWT/webhook secrets, and application secrets. |
| The `komodo-keys` volume | Core and Periphery identities; its physical name is normally `server_komodo-keys`. |
| The deployed Git revision and any local configuration | The exact Compose files and image versions used with the snapshot. |

Export the keys into a private directory outside the snapshot retention tree:

```sh
sudo install -d -o "$(id -u)" -g "$(id -g)" -m 700 /srv/komodo/recovery/keys
docker compose --env-file /srv/komodo/bootstrap.env cp control-plane:/config/keys/. /srv/komodo/recovery/keys/
sudo chmod -R go-rwx /srv/komodo/recovery
```

Include that exported directory in the encrypted off-host backup, refreshing it
after key rotations. Keep the encryption recovery key separately accessible.
The generated `komodo-bootstrap-config` volume can be recreated from
`bootstrap.env`. Application volumes, media, Transmission's password file, and
Periphery host files need their own backup policy; a Komodo database snapshot
does not contain them.

This repository configures local snapshots. No off-host destination or transfer
credentials are configured. Local snapshots alone do not cover loss of the Pi's
storage. Komodo's gzip files are not encrypted, and contain sensitive data.

## Restore without merging into the live database

Use a host terminal, since Core will be stopped. Start with the same pinned
Komodo version that created the snapshot. For a replacement host, restore the
private bootstrap file, backup directory, and saved keys first, retaining their
permissions and `MANAGEMENT_VOLUME_PREFIX`. On that replacement host, create
Core and its dependencies without starting them, then copy the saved keys into
its volume:

```sh
docker compose --env-file /srv/komodo/bootstrap.env create control-plane
docker compose --env-file /srv/komodo/bootstrap.env cp /srv/komodo/recovery/keys/. control-plane:/config/keys/
```

Populate the keys before starting Core or Periphery so they reuse their saved
identities. These two commands are for a replacement host, not an in-place
database recovery.

1. Pause deployment webhooks and allow active operations to finish. Record the
   current `KOMODO_DATABASE_DB_NAME` from the private bootstrap file (`komodo`
   if absent). If Core is still usable, take one final backup before stopping it.

   ```sh
   docker compose --env-file /srv/komodo/bootstrap.env stop host-agent control-plane
   docker compose --env-file /srv/komodo/bootstrap.env up -d --wait database
   docker compose --env-file /srv/komodo/bootstrap.env run --rm --no-deps -T secret-bootstrap
   ```

2. Choose a completed snapshot and a **new, unused database name**. The values
   below are examples; use your actual timestamp:

   ```sh
   RESTORE_FOLDER=2026-10-18_01-00-00
   RESTORE_DATABASE=komodo_recovery_20261018
   ```

   Confirm the target contains no collections. Authentication uses environment
   values inside the container, so passwords are not inserted into shell code:

   ```sh
   docker compose --env-file /srv/komodo/bootstrap.env exec -T \
     -e RESTORE_DATABASE="$RESTORE_DATABASE" database mongosh --quiet --eval '
   const admin = db.getSiblingDB("admin");
   if (admin.auth(process.env.MONGO_INITDB_ROOT_USERNAME, process.env.MONGO_INITDB_ROOT_PASSWORD).ok !== 1) { quit(1); }
   const target = db.getSiblingDB(process.env.RESTORE_DATABASE);
   if (target.getCollectionNames().length !== 0) { throw new Error("Restore target is not empty; choose a new database name"); }
   print("Restore target is empty");
   '
   ```

   Continue only after this check succeeds. Komodo restores upsert documents;
   they do not remove records already present in the destination.

3. Restore through a one-off Core container. It connects to MongoDB on the
   private backend network and uses the existing backup mount, without starting
   the Core service or publishing its ports:

   ```sh
   docker compose --env-file /srv/komodo/bootstrap.env run --rm --no-deps -T \
     --entrypoint sh \
     -e RESTORE_FOLDER="$RESTORE_FOLDER" \
     -e KOMODO_CLI_DATABASE_TARGET_DB_NAME="$RESTORE_DATABASE" \
     control-plane -ec '
   export KOMODO_CLI_DATABASE_TARGET_ADDRESS="$KOMODO_DATABASE_ADDRESS"
   export KOMODO_CLI_DATABASE_TARGET_USERNAME="$KOMODO_DATABASE_USERNAME"
   export KOMODO_CLI_DATABASE_TARGET_PASSWORD="$KOMODO_DATABASE_PASSWORD"
   exec km database restore --restore-folder "$RESTORE_FOLDER" --yes
   '
   ```

   Inspect the complete output for per-collection errors. Komodo 2.3.3 can report
   these errors while returning a successful process exit status. Compare the
   restored collection counts and representative resources against the selected
   snapshot before switching. Do not continue after an incomplete restore; fix
   the cause and retry into another empty database.

4. Set `KOMODO_DATABASE_DB_NAME` in `/srv/komodo/bootstrap.env` to the chosen
   target name, then start management:

   ```sh
   docker compose --env-file /srv/komodo/bootstrap.env up -d
   docker compose --env-file /srv/komodo/bootstrap.env ps
   ```

   Verify login, users, Stacks, Procedures, variables, and the `home-server`
   connection. Restored schedules become active when Core starts. Check backup
   and deployment schedules before resuming webhook traffic, and run a fresh
   backup of the restored database. Keep the previous database until recovery
   is accepted; switching `KOMODO_DATABASE_DB_NAME` back and recreating Core
   provides a rollback on the original host.

## Recovery test

With Docker running, execute from the repository root:

```sh
python3 tests/smoke_management.py
```

The test uses the pinned images and fixture credentials. It validates the
configured Procedure through Core's API, executes a backup, exercises retention,
reads compressed documents, restores into a fresh database, compares collection
counts and a known payload, and verifies login after starting Core against the
restored database. It also checks startup readiness and network isolation.
Everything runs in temporary Docker networks and volumes, without production data or a host Docker
socket mount, and is removed on exit.

See [Komodo's backup documentation](https://komo.do/docs/setup/backup) and the
[pinned 2.3.3 restore implementation](https://github.com/moghtech/komodo/blob/v2.3.3/lib/database/src/utils/restore.rs).
