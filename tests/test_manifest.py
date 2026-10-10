#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local checks that need no device: manifest shape, payload contents, docs.

Run from the repository root:  python tests/test_manifest.py
"""

import hashlib
import json
import pathlib
import re
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
ID = re.compile(r'[a-z0-9]+\.[a-z0-9]+(?:[.-][a-z0-9]+)*\Z')
SEMVER = re.compile(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?\Z')
SAFE_PATH = re.compile(r'[A-Za-z0-9/._+-]+\Z')

failures = []


def check(condition, message):
    if condition:
        print('  ok   ' + message)
    else:
        print('  FAIL ' + message)
        failures.append(message)


manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()

print('manifest')
check(manifest['schemaVersion'] == 1 and manifest['apiVersion'] == 1, 'schema/api version are 1')
check(bool(ID.fullmatch(manifest['id'])), 'id is namespace.name: ' + manifest['id'])
check(bool(SEMVER.fullmatch(manifest['version'])), 'version is semver: ' + manifest['version'])
check(manifest['version'] == version, 'VERSION matches manifest.version')
check(manifest['version'] == json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version'],
      'package.json version matches manifest.version')
check(manifest['icon'] == 'icon.png', 'icon is icon.png')
check(manifest['ui']['quickPage'] == 'page.js', 'ui.quickPage is page.js')
check(manifest['backend']['entry'] == 'backend.py', 'backend.entry is backend.py')
check(manifest['backend']['runAs'] == 'root', 'backend runs as root (pwm1 + stock service)')
check(manifest['lifecycle']['runAs'] == 'root', 'lifecycle runAs matches the backend')
check(manifest['backend']['restart'] == 'on-failure' and 1 <= manifest['backend']['restartLimit'] <= 10,
      'restart policy within the allowed range')
check(1 <= manifest['lifecycle']['timeoutSeconds'] <= 15, 'lifecycle timeout within 1..15')
check(len(manifest['description'].encode()) <= 4096, 'description within 4096 bytes')
check(len(manifest['details'].encode()) <= 32768, 'details within 32768 bytes')
check(len(manifest['changelog'].encode()) <= 16384, 'changelog within 16384 bytes')
check(len(manifest.get('tags', [])) <= 12, 'at most 12 tags')

print('icon')
icon = (ROOT / 'icon.png').read_bytes()
check(icon.startswith(b'\x89PNG\r\n\x1a\n') and icon[12:16] == b'IHDR', 'icon is a PNG')
check(24 <= len(icon) <= 1024 * 1024, 'icon size within 24 B .. 1 MiB')

print('payload')
built = (ROOT / 'payload').is_dir()
if not built:
    print('  skip payload not built yet (run npm run build)')
else:
    entries = sorted(p.name for p in (ROOT / 'payload').iterdir())
    expected = ['README.md', 'VERSION', 'backend.py', 'framely.py', 'icon.png', 'page.js',
                'sf-fan-qamd.service', 'sf_fan_qam.js', 'sf_fan_qamd.py']
    check(entries == expected, 'payload contains exactly the packaged files')
    for name in entries:
        check(bool(SAFE_PATH.fullmatch(name)), 'payload path is safe: ' + name)
    unit = (ROOT / 'payload/sf-fan-qamd.service').read_text(encoding='utf-8')
    check('@INSTALL_DIR@' in unit, 'the shipped unit keeps the install-path placeholder')
    check('/home/steamos' not in unit, 'the shipped unit contains no hardcoded home')
    check('ExecStopPost=/usr/bin/systemctl start deckard-fan-control.service' in unit,
          'the unit hands the fan back when it stops')
    backend = (ROOT / 'payload/backend.py').read_text(encoding='utf-8')
    check('deckard-fan-control.service' in backend, 'the backend knows the stock controller')
    check('sf-fan-qamd.service' in backend, 'the backend knows its own service')

print('package')
package = ROOT / 'dist' / f"{manifest['id']}-{manifest['version']}.framely"
if not package.is_file():
    print('  skip package not built yet (run python scripts/pack.py)')
else:
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        packed = json.loads(archive.read('manifest.json'))
        check('manifest.json' in names, 'package carries manifest.json')
        check(set(names) == {'manifest.json', *packed['files']}, 'member list matches manifest.files')
        for name, digest in packed['files'].items():
            check(hashlib.sha256(archive.read(name)).hexdigest() == digest, 'payload hash: ' + name)
    check(packed['version'] == manifest['version'], 'package version matches the repository')
    check('downloadUrl' in packed, 'package carries the release downloadUrl')
    check('downloadSha256' not in packed, 'package drops the registration-only downloadSha256')
    check(packed['downloadUrl'].endswith(
        f"/releases/download/v{manifest['version']}/{manifest['id']}-{manifest['version']}.framely"),
        'downloadUrl follows the GitHub Release convention')
    sums = (ROOT / 'dist/SHA256SUMS').read_text(encoding='utf-8').strip()
    check(sums.split()[0] == hashlib.sha256(package.read_bytes()).hexdigest(), 'SHA256SUMS matches the package')

print('workflow')
workflow = (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8')
check('ubuntu-24.04-arm' in workflow, 'the release builds on an arm64 runner')
check('sha256sum --check SHA256SUMS' in workflow, 'the release verifies its own checksums')

print()
if failures:
    print(str(len(failures)) + ' check(s) failed')
    sys.exit(1)
print('all checks passed')
