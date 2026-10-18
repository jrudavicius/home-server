"""Render Core secrets from the bootstrap container's environment, never logging values."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


REQUIRED = (
    "GRAFANA_ADMIN_USER",
    "GRAFANA_ADMIN_PASSWORD",
    "TRANSMISSION_USERNAME",
    "NGROK_AUTHTOKEN",
)
OPTIONAL = ("PLEX_CLAIM",)


def core_config(environment):
    missing = [name for name in REQUIRED if not environment.get(name, "").strip()]
    if missing:
        raise ValueError("Set nonempty bootstrap values for: " + ", ".join(missing))

    secrets = {}
    for name in REQUIRED + OPTIONAL:
        value = environment.get(name, "")
        if any(ord(character) < 32 for character in value):
            raise ValueError(name + " must be a single-line value without control characters")
        # Komodo preserves this quoting when writing its Stack .env file.
        # Double quotes escape quotes/backslashes; $$ prevents Compose from
        # treating a literal dollar in a credential as variable interpolation.
        encoded = json.dumps(value, ensure_ascii=False).replace("$", "$$")
        # Komodo's key/value parser strips everything after a literal " #",
        # even inside quotes. This expansion is always empty, whether or not
        # the named variable exists, and prevents that sequence until Compose
        # reads the generated .env. Add it after escaping the input's dollars.
        secrets[name] = encoded.replace(" #", " ${KOMODO_BOOTSTRAP_EMPTY:+}#")
    return {"secrets": secrets}


def write_config(config, destination):
    destination = Path(destination)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.parent.chmod(0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            os.fchmod(output.fileno(), 0o600)
            json.dump(config, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="/bootstrap/core.config.json")
    args = parser.parse_args()
    try:
        config = core_config(os.environ)
        write_config(config, args.output)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    except OSError:
        print("Unable to write the Komodo bootstrap config; check volume permissions.", file=sys.stderr)
        return 1
    print("Komodo application secrets prepared.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
