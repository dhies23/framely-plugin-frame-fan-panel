"""Register a published plugin version in the author's database fork."""
import argparse
import json
import os
import pathlib
import re
import subprocess
import tempfile

PLUGIN_ID = re.compile(r'[a-z0-9]+\.[a-z0-9]+(?:[.-][a-z0-9]+)*\Z')
DEFAULT_DATABASE = 'SteamFramelyHomebrew/framely-plugin-database'


def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def channel(version):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?', version):
        raise ValueError('Expected a semantic version')
    return 'testing' if '-' in version.split('+')[0] else 'main'


def release_url(manifest, repository):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Expected a GitHub owner/repository')
    channel(manifest['version'])
    if not PLUGIN_ID.fullmatch(manifest['id']):
        raise ValueError('Invalid plugin ID')
    return ('https://github.com/' + repository + '/releases/download/v' +
            manifest['version'] + '/' + manifest['id'] + '-' + manifest['version'] + '.framely')


def validate_registration_manifest(manifest):
    if not PLUGIN_ID.fullmatch(manifest['id']):
        raise ValueError('Plugin ID must be namespace.name')
    channel(manifest['version'])


def prepare(database, plugin_url, commit, identifier, repository):
    """Stage only the submodule registration, preserving the rest of the database."""
    if not PLUGIN_ID.fullmatch(identifier):
        raise ValueError('Invalid plugin ID')
    path = 'plugins/' + identifier
    modules = pathlib.Path(database) / '.gitmodules'
    existing = run('git', 'config', '-f', str(modules), '--get-regexp', r'^submodule\..*\.path$') if modules.exists() and modules.read_text().strip() else ''
    sections = [line.rsplit(' ', 1)[0][:-5] for line in existing.splitlines() if line.rsplit(' ', 1)[-1] == path]
    if sections:
        registered_url = run('git', 'config', '-f', str(modules), '--get', sections[0] + '.url')
        if registered_url != plugin_url:
            raise ValueError('Existing submodule belongs to another repository')
        run('git', 'submodule', 'update', '--init', '--', path, cwd=database)
    else:
        run('git', 'submodule', 'add', plugin_url, path, cwd=database)
    source = pathlib.Path(database) / path
    run('git', 'fetch', 'origin', commit, cwd=source)
    run('git', 'checkout', '--detach', commit, cwd=source)
    run('git', 'add', '.gitmodules', path, cwd=database)
    return path


def submit(tag, database_repository, branch, remote):
    plugin_repo = os.environ.get('GITHUB_REPOSITORY')
    if not plugin_repo:
        remote_url = run('git', 'remote', 'get-url', remote, cwd=pathlib.Path(__file__).resolve().parents[1])
        match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?', remote_url)
        if not match:
            raise ValueError('Cannot infer the plugin repository; set GITHUB_REPOSITORY')
        plugin_repo = match.group(1)
    plugin_url = 'https://github.com/' + plugin_repo + '.git'
    root = pathlib.Path(__file__).resolve().parents[1]
    commit = run('git', 'rev-parse', '--verify', 'refs/tags/' + tag + '^{commit}', cwd=root)
    manifest = json.loads(run('git', 'show', commit + ':manifest.json', cwd=root))
    validate_registration_manifest(manifest)
    version, identifier = manifest['version'], manifest['id']
    if tag != 'v' + version:
        raise ValueError('Release tag must match manifest.version')
    if branch != channel(version):
        raise ValueError('Release version maps to the ' + channel(version) + ' channel, not ' + branch)
    with tempfile.TemporaryDirectory() as temporary:
        database = pathlib.Path(temporary) / 'database'
        run('git', 'clone', '--branch', branch, 'https://github.com/' + database_repository + '.git', str(database))
        run('git', 'config', 'user.name', 'github-actions[bot]', cwd=database)
        run('git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com', cwd=database)
        prepare(database, plugin_url, commit, identifier, plugin_repo)
        # Only .gitmodules and plugins/<id> may change; anything else needs review.
        changed = run('git', 'diff', '--cached', '--name-only', cwd=database).splitlines()
        unexpected = [c for c in changed if c != '.gitmodules' and not c.startswith('plugins/')]
        if unexpected:
            raise ValueError('Unexpected database changes: ' + ', '.join(unexpected))
        if not changed:
            print('Plugin release is already registered on ' + branch)
            return
        run('git', 'commit', '-m', 'Register ' + identifier + ' ' + version, cwd=database)
        run('git', 'push', 'origin', 'HEAD:refs/heads/' + branch, cwd=database)
        print('Registered ' + identifier + ' ' + version + ' on ' + branch)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('tag')
    parser.add_argument('--database', default=os.environ.get('DATABASE_REPOSITORY', DEFAULT_DATABASE))
    parser.add_argument('--branch', default=None, help='defaults to the channel of the released version')
    parser.add_argument('--remote', default='origin')
    arguments = parser.parse_args()
    manifest = json.loads((pathlib.Path(__file__).resolve().parents[1] / 'manifest.json').read_text())
    submit(arguments.tag, arguments.database,
           arguments.branch or channel(manifest['version']), arguments.remote)
