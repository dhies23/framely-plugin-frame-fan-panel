"""Validate the built .framely against the upstream database rules, locally.

Downloads nothing: it reuses scripts/database.py from the plugin database.
"""
import importlib.util
import json
import os
import pathlib
import sys

DB = pathlib.Path(sys.argv[1]).resolve()
ROOT = pathlib.Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location('database', DB / 'scripts/database.py')
database = importlib.util.module_from_spec(spec)
sys.modules['database'] = database
spec.loader.exec_module(database)

manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
repository = os.environ.get('GITHUB_REPOSITORY', 'dhies23/framely-plugin-frame-fan-panel')
source = dict(manifest)
source['downloadUrl'] = ('https://github.com/' + repository + '/releases/download/v'
                         + source['version'] + '/' + source['id'] + '-' + source['version'] + '.framely')

package_path = ROOT / 'dist' / f"{manifest['id']}-{manifest['version']}.framely"
data = package_path.read_bytes()

entry = {'id': manifest['id'], 'version': manifest['version'], 'manifest': source,
         'packageUrl': source['downloadUrl']}
packed, files = database.verify_package(data, entry)
database.registrations  # noqa: B018 - documentation only

# The Rust host must accept the same declarations.
packed_manifest = json.dumps(packed, ensure_ascii=False)
print('package      :', package_path.name, len(data), 'bytes')
print('payload files:', ', '.join(sorted(files)))
print('downloadUrl  :', packed['downloadUrl'])
print('backend      :', packed['backend']['entry'], packed['backend'].get('runAs', 'steamos'))
print('lifecycle    :', sorted(k for k, v in packed['lifecycle'].items() if v not in (None, False)))
print('ui.quickPage :', packed['ui']['quickPage'])
print('icon bytes   :', len(files[packed['icon']]))
assert set(packed['files']) == set(files)
assert packed['downloadUrl'].endswith(
    f"/releases/download/v{manifest['version']}/{manifest['id']}-{manifest['version']}.framely")
print('OK: database verification passed')
