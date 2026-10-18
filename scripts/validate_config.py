#!/usr/bin/env python3
"""Validate deployment inputs using fixtures only (Python 3.11+ and Compose required)."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib

from render_komodo_secrets import OPTIONAL, RAW_OPTIONAL, REQUIRED


ROOT = Path(__file__).resolve().parents[1]
IMAGE_PIN = re.compile(r'.+:[^/@]+@sha256:[0-9a-f]{64}')
REFERENCE = re.compile(r'\[\[([A-Z][A-Z0-9_]*)\]\]')


def repository_file(path):
    path = path.resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError(f'Missing or non-repository configuration file: {path}')
    return path


def main():
    resources = {}
    for path in sorted((ROOT / 'komodo').glob('*.toml')):
        document = tomllib.loads(path.read_text())
        for kind, entries in document.items():
            for entry in entries:
                key = (kind, entry['name'])
                if key in resources:
                    raise ValueError(f'Duplicate Komodo resource: {key}')
                resources[key] = entry
        print(f'Parsed {path.relative_to(ROOT)}')

    variables = {name for kind, name in resources if kind == 'variable'}
    variables.update(REQUIRED + OPTIONAL + RAW_OPTIONAL)
    for key, entry in resources.items():
        missing = set(REFERENCE.findall(json.dumps(entry))) - variables
        if missing:
            raise ValueError(f'{key} references undefined variables/secrets: {sorted(missing)}')

    for path in sorted((ROOT / 'stacks').rglob('*.json')):
        json.loads(path.read_text())
    print('Parsed stack JSON configuration')

    # Never inherit deployment variables or let Compose load a private .env.
    env = {key: value for key, value in os.environ.items()
           if key in ('PATH', 'HOME', 'TMPDIR', 'SYSTEMROOT')}
    env.update({name: 'validation-only-' + name.lower() for name in REQUIRED})
    env.update({name: 'validation-only' for name in (
        'KOMODO_DATABASE_USERNAME', 'KOMODO_DATABASE_PASSWORD',
        'KOMODO_INIT_ADMIN_USERNAME', 'KOMODO_INIT_ADMIN_PASSWORD',
        'KOMODO_WEBHOOK_SECRET', 'KOMODO_JWT_SECRET',
    )})
    env['GRAFANA_DISCORD_WEBHOOK_URL'] = 'https://example.invalid/validation-only'
    configs = {}
    files = [ROOT / 'docker-compose.yml', *sorted((ROOT / 'stacks').glob('*/docker-compose.yml'))]
    for path in files:
        example = ROOT / 'bootstrap.env.example' if path.parent == ROOT else path.parent / '.env.example'
        command = ['docker', 'compose', '--env-file', str(repository_file(example)), '-f', str(path)]
        result = subprocess.run(command + ['config', '--format', 'json'],
                                env=env, capture_output=True, text=True, check=True)
        config = json.loads(result.stdout)
        configs[path.resolve()] = config
        for service, settings in config['services'].items():
            if not IMAGE_PIN.fullmatch(settings.get('image', '')):
                raise ValueError(f'{path.relative_to(ROOT)}:{service} needs an exact tag and digest')
        print(f'Validated {path.relative_to(ROOT)}')
        for overlay in sorted(path.parent.glob('docker-compose.*.yml')):
            subprocess.run(command + ['-f', str(overlay), 'config', '--quiet'],
                           env=env, capture_output=True, text=True, check=True)
            print(f'Validated optional overlay {overlay.relative_to(ROOT)}')

    for (kind, name), entry in resources.items():
        if kind != 'stack':
            continue
        config = entry['config']
        if ('repo', config['linked_repo']) not in resources:
            raise ValueError(f'{name} links to an undefined Repo')
        directory = ROOT / config['run_directory']
        for relative in config['file_paths']:
            repository_file(directory / relative)
        compose = configs[repository_file(directory / 'docker-compose.yml')]
        for item in config.get('config_files', []):
            repository_file(directory / item['path'])
            missing = set(item.get('services', [])) - set(compose['services'])
            if missing:
                raise ValueError(f'{name} config file references unknown services: {sorted(missing)}')
    print('Komodo repository, file, service, and variable references are valid')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(error.stderr, file=sys.stderr)
        sys.exit(1)
    except (ValueError, KeyError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
