# OpenBao on the home server

The existing `home-server` Komodo Server manages two independent, Git-backed Stacks. `openbao` runs OpenBao 2.7.2 with single-node Raft storage. `openbao-backup` runs a native OpenBao Agent and supplies the snapshot command used by the scheduled **Backup OpenBao** Procedure. Management can start independently of OpenBao. Its optional [webhook Agent](komodo-webhook.md) keeps a private startup copy of the signing secret on the Pi.

| Component | Where it runs or persists |
| --- | --- |
| API and UI | HTTPS on the Pi's loopback at `127.0.0.1:18200`. Workload agents reach `https://openbao-server:8200` on the dedicated `openbao-link` Docker bridge. |
| Raft and audit | `/srv/server/openbao/raft` and `/srv/server/openbao/audit` on the Pi. The server runs as UID/GID 10001. |
| Backup identity | A private client key and certificate under `backup-tls`, readable by UID/GID 10002. The agent places its short-lived OpenBao token in a memory-backed volume shared with the snapshot command. |
| Backups | Daily at **02:15 Europe/Vilnius**. The job atomically publishes a complete gzip-checked snapshot under `/srv/server/openbao/snapshots` and keeps 14 by default. Komodo reports job failures. |
| Recovery keys | The operator holds the Shamir shares off the Pi. An unseal quorum is needed after a server process restart. The CA signing key also stays on the operator's signing machine. |

## Prepare the Pi

Start from this repository on a 64-bit Linux host with Docker Compose, OpenSSL, Python 3 and host logrotate. The server uses Raft with memory locking disabled. Disable host swap or use encrypted swap. Keep enough free storage for Raft, the audit file and retained snapshots. A single Pi is a single point of failure.

1. **On the signing machine**, use a dedicated CA or your existing private CA. To create a dedicated CA once, use a private directory and an encrypted signing key. The following command prompts for the CA passphrase.

   ```sh
   umask 077
   openssl req -x509 -newkey rsa:3072 -sha256 -days 3650 \
     -subj '/CN=Home OpenBao CA' -addext 'basicConstraints=critical,CA:TRUE' \
     -addext 'keyUsage=critical,keyCertSign,cRLSign' -addext 'subjectKeyIdentifier=hash' \
     -keyout ca.key -out ca.crt
   sh /path/to/Server/scripts/openbao_certificates.sh ca.crt ca.key openbao-identity-01
   ```

   Transfer only the resulting `openbao-identity-01` directory securely to a private location on the Pi. It contains the CA public certificate and two distinct one-year leaf key pairs. The backup role pins the installed client certificate and checks its `openbao-backup` name. Keep the signing key private for future renewals.

2. **On the Pi**, install the files from the reviewed repository revision before merging it to `main`. The existing push webhook can start the first coordinated deployment as soon as the changes reach that branch.

   ```sh
   sudo python3 scripts/prepare_openbao.py /private/path/to/openbao-identity-01
   sudo install -o root -g root -m 0644 host/openbao/audit.logrotate /etc/logrotate.d/openbao
   ```

   Repeating the command preserves Raft, audit data and snapshots. The default directory is independent of Komodo's Git checkout and Core backup pruning. If you customize a directory, UID/GID, client network or port, set matching values in the affected Stack environments and your manual Compose env files. The two `.env.example` files list the supported settings. Pass the same `--state-dir` and `--port` to `configure_openbao.py` when using custom values. Prepare the same host that runs Periphery. To retain a previously initialized pilot, restore its snapshot with its original quorum, then run the configuration step below with an operator identity from that vault.

3. Sync the repository's `komodo/` directory through **home-server-resources**, then run **home-server-deploy**. Sync an updated Procedure while it is idle. Check for the two **Stacks** and the **Backup OpenBao** Procedure. Before initialization the server reports sealed, the Agent retries and backups cannot yet run. You can bring up the server directly from a Pi checkout when Komodo is unavailable.

   ```sh
   docker compose --env-file stacks/openbao/.env.example -f stacks/openbao/docker-compose.yml up -d
   docker exec openbao-server bao status
   ```

## Initialize and grant backup access

1. Check `bao status`. For a **fresh, uninitialized** store, initialize from a private terminal. The example uses two of three shares. Choose the quorum you can independently safeguard. Preserve the initial root token and the shares outside the Pi, its logs and this repository. Each unseal command prompts for one distinct share.

   ```sh
   docker exec -it openbao-server bao operator init -key-shares=3 -key-threshold=2
   docker exec -it openbao-server bao operator unseal
   docker exec -it openbao-server bao operator unseal
   ```

2. From the Pi checkout, configure the unsealed vault. The script prompts privately for an authorized operator token and can be rerun. It checks the file audit device declared in the server configuration, enables the KV v2 store at `kv/`, and installs the backup ACL and pinned client certificate under the dedicated `auth/openbao-backup/` mount. [OpenBao declarative audit devices](https://openbao.org/docs/configuration/audit/)

   ```sh
   sudo python3 scripts/configure_openbao.py
   ```

   The backup identity can obtain an encrypted Raft snapshot and look up or renew its own token. Its ACL grants no application-secret reads or snapshot restores. Tokens have a 10-minute TTL and a 30-minute maximum. The Agent renews or reauthenticates with its client certificate. The dedicated auth mount lets the operator revoke every outstanding backup token independently of other workloads. Use a separately authorized human login for ongoing administration. Revoke the initial root token after verifying the operator login or quorum-based root recovery procedure. [Root token generation](https://openbao.org/docs/commands/operator/generate-root/)

3. In Komodo run **Backup OpenBao** once and inspect the successful execution. Check `sudo ls -lh /srv/server/openbao/snapshots` and the Procedure's next scheduled run. A manual invocation of the same job is available from the Pi checkout.

   ```sh
   docker compose --env-file stacks/openbao-backup/.env.example \
     -f stacks/openbao-backup/docker-compose.yml run --rm --no-deps snapshot
   ```

   The backup Stack's Agent must be running and the server unsealed. Copy completed `openbao-*.snap` files to a separately administered encrypted off-host destination. This repository schedules the local capture. Choose an off-host destination and verify delivery before relying on recovery after loss of the Pi.

## Ongoing operation

- **Host reboot or server upgrade.** OpenBao starts sealed. Supply the unseal quorum and check `docker exec openbao-server bao status`. The Agent retries automatically. Run a backup after recovery. Existing services can start using their current bootstrap paths.
- **Certificate renewal and revocation.** Check expiry with `sudo openssl x509 -in /srv/server/openbao/backup-tls/current/cert.pem -noout -enddate`. Before the one-year expiry, issue and transfer a new certificate release using the original CA. Between scheduled snapshots, stop the backup Agent, install the new pairs, reload the server listener, then update the pinned client certificate and revoke all outstanding tokens from the backup auth mount. The listener also checks its certificate files every 10 seconds. The operator command is safe to repeat if the cutover is interrupted. Starting the Agent authenticates with the replacement certificate. Verify a successful **Backup OpenBao** run before retiring superseded private-key generations. A CA change requires a coordinated trust rollover. [Listener TLS reload](https://openbao.org/docs/configuration/listener/tcp/) · [OpenBao source-based revocation](https://openbao.org/docs/concepts/lease/)

  ```sh
  docker stop openbao-backup-agent
  sudo python3 scripts/prepare_openbao.py /private/path/to/openbao-identity-02
  docker kill --signal=HUP openbao-server
  sudo python3 scripts/configure_openbao.py --rotate-backup-identity
  docker start openbao-backup-agent
  ```

- **Audit and disk space.** Audit records go to `audit/audit.json`. The supplied Linux logrotate rule rotates daily or above 32 MiB when logrotate runs, keeps 14 archives and signals the server to reopen its file. Check the host's logrotate timer, adjust the rule if you changed the storage path, and monitor free space. OpenBao can refuse requests if it cannot write to an enabled audit device. Preserve audit history separately according to your retention needs. [File audit device](https://openbao.org/docs/audit/file/)
- **New workload.** Give each service a separate identity and policy. A KV entry stores a value. Automatic expiry at the target requires a dynamic secrets engine or target-specific revocation support. The PostgreSQL test verifies that distinction with a fresh login and a session held open across expiry. An application using a pool must reload its credentials and reconnect when a session is terminated.

## Restore onto an isolated host or project

1. Gather one completed snapshot, the **source vault's** original unseal quorum, an authorized operator identity for the restored state, and the TLS trust material. Maintain separate off-host copies. A Komodo Core database dump recovers its resource definitions. The OpenBao Raft snapshot recovers the secrets, policies and auth mounts.
2. On a recovery machine use the pinned OpenBao image and a **fresh** state directory. For a rehearsal on the same machine, assign a new loopback port and separate Docker bridge. From the repository root, the following starts only the replacement server.

   ```sh
   docker network create --internal openbao-recovery-link
   sudo python3 scripts/prepare_openbao.py /private/path/to/signed-identities \
     --state-dir /srv/server/openbao-recovery --network openbao-recovery-link
   OPENBAO_STATE_DIR=/srv/server/openbao-recovery OPENBAO_NETWORK=openbao-recovery-link OPENBAO_PORT=28200 \
     docker compose --env-file stacks/openbao/.env.example -p openbao-recovery \
       -f stacks/openbao/docker-compose.yml up -d
   ```

3. Use a CLI container on the **internal recovery bridge**. Docker can omit published ports for an internal-only bridge. This client can reach the replacement and has no route to live workload databases. From the repository root, stage a verified snapshot and run the same image used by the server. Adjust UID/GID if you customized the backup identity.

   ```sh
   sudo install -o 10002 -g 10002 -m 0400 /private/path/to/backup.snap /srv/server/openbao-recovery/restore.snap
   docker run --rm -it --network openbao-recovery-link --user 10002:10002 \
     --read-only --cap-drop ALL --security-opt no-new-privileges \
     --tmpfs /session:rw,mode=0700,uid=10002,gid=10002 \
     -e HOME=/session -e BAO_ADDR=https://openbao-server:8200 -e BAO_CACERT=/trust/ca.crt \
     --mount type=bind,src=/srv/server/openbao-recovery/trust,dst=/trust,readonly \
     --mount type=bind,src=/srv/server/openbao-recovery/restore.snap,dst=/restore.snap,readonly \
     --entrypoint sh openbao/openbao:2.7.2@sha256:5046911075e137e154ce49ab051502f4ec7cf367d484ae4a4dce665d9b90561f
   ```

4. In that shell check fresh initialization status, initialize and unseal the empty replacement, then log in with its temporary root token at the hidden prompt. A forced restore overwrites the destination state. Keep the original source running separately.

   ```sh
   bao status
   bao operator init
   # Re-run this command with distinct temporary shares until the replacement unseals.
   bao operator unseal
   bao login -no-print
   bao operator raft snapshot restore -force /restore.snap
   ```

5. Check seal status, supply the **original source quorum**, and log in with an identity valid in the snapshot. Verify a known secret or policy and the expected ACLs. Exit the CLI container to discard its temporary token cache. Keep the recovery project isolated until you intend a cutover. [OpenBao Raft snapshot commands](https://openbao.org/docs/commands/operator/raft/)

## Verify changes locally

Run `python3 tests/smoke_openbao.py` with local Docker, OpenSSL, Git and Python 3.9+. It uses a disposable Git origin, Komodo database, private Docker bridge, CA and workload identities. Its temporary Periphery receives the local Docker socket to deploy both Stacks. It checks the scheduled Procedure and backup ACL, runs a retention and isolated restore drill, uses a long-running PostgreSQL monitor to verify expiry and termination of an existing session, and verifies that the retired backup certificate and token lose access after renewal.
