# Komodo session signing

Core reads its session signer once at startup. The private cache at `/srv/komodo/session-signing/core.config.json` contains a JSON string named `jwt_secret`. The launcher decodes that string and passes its literal UTF-8 value to the Core process. This preserves variable references, quotes and surrounding whitespace. Compose mounts the directory read-only. The signer stays out of the Compose environment and the cache stays outside Komodo's interpolated configuration paths. [Pinned Core input handling](https://github.com/moghtech/komodo/blob/v2.3.3/bin/core/src/config.rs#L145-L167)

## Move an existing signer

For a standalone upgrade, keep an authenticated browser session open and run this from the new checkout **before stopping the old Core**. Use the actual container name. The import needs local Docker access and the management directory. It also works with OpenBao sealed or absent.

```sh
sudo python3 scripts/prepare_komodo_identity.py --import-session-from-core management-control-plane
```

The importer follows Core's file-over-environment precedence and accepts an identical cache on reruns. A different existing cache stops the import. Remove legacy JWT settings from site overrides before recreating Core. Reload **Servers** in the same browser session and confirm the Pi is online. On a fresh installation, `--init-new-session` generates the first key in an empty private directory.

When adopting the OpenBao overlay, enroll **both** the session and webhook Agents, including on hosts that already have a session cache. The session Agent has a dedicated client certificate and read access to `kv/komodo/jwt`. The shared cutover captures both active values, checks an authenticated first render from each Agent, then recreates Core once. [Agent enrollment and cutover](komodo-webhook.md#migrate-an-existing-pi)

## Reboot and recovery

The Agent owns the directory (0700) and file (0400) as UID/GID 10004. Core can start from this file while OpenBao is sealed. If the file is missing or empty, startup stops. Unseal OpenBao and start `session-agent` to restore it, or restore the original private directory from an encrypted backup. Then start Core. Generating a new signing key invalidates existing sessions.

The client certificate lasts one year. For renewal, stop `session-agent`, run `sudo python3 scripts/prepare_komodo_identity.py --jwt --renew` and enroll it with `sudo python3 scripts/configure_openbao.py --komodo-jwt --rotate-komodo-jwt-identity --userpass manager --userpass-mount home-admins`. Start the Agent again. The signing value stays in KV throughout certificate renewal.
