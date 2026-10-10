#!/usr/bin/env node
/**
 * Build the plugin payload.
 *
 *   payload/page.js     bunded React quick page
 *   payload/backend.py  root backend
 *   payload/framely.py  vendored SDK (Python side of the bridge)
 *   payload/icon.png    launcher / store icon
 *   payload/sf_fan_qam* vendored fan panel (daemon, injected UI, unit, docs)
 */
import {build} from 'esbuild';
import {chmod, copyFile, mkdir, readFile, rm, writeFile} from 'node:fs/promises';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const payload = path.join(root, 'payload');
// The panel files live in vendor/fan-panel, refreshed by scripts/sync-panel.mjs
// from the standalone project. Set FAN_PANEL_SOURCE to build straight from a
// working checkout instead.
const panelSource = process.env.FAN_PANEL_SOURCE
  ? path.resolve(process.env.FAN_PANEL_SOURCE)
  : path.join(root, 'vendor', 'fan-panel');

async function copy(source, target, mode) {
  await copyFile(source, path.join(payload, target));
  if (mode) await chmod(path.join(payload, target), mode);
}

// A clean payload keeps pack.py's file-set check meaningful.
await rm(payload, {recursive: true, force: true});
await mkdir(payload, {recursive: true});

await build({
  entryPoints: [path.join(root, 'src/page.tsx')],
  outfile: path.join(payload, 'page.js'),
  bundle: true,
  minify: true,
  loader: {'.css': 'text'},
  define: {'process.env.NODE_ENV': '"production"'},
});

await copy(path.join(root, 'src/backend.py'), 'backend.py', 0o755);
await copy(path.join(root, 'vendor/framely-sdk/python/framely.py'), 'framely.py', 0o644);
await copy(path.join(root, 'icon.png'), 'icon.png', 0o644);

// The panel files come from the standalone project so there is exactly one
// copy of the fan logic to keep in sync.
const panel = {
  'device/sf_fan_qamd.py': ['sf_fan_qamd.py', 0o755],
  'device/sf_fan_qam.js': ['sf_fan_qam.js', 0o644],
  'device/sf-fan-qamd.service': ['sf-fan-qamd.service', 0o644],
  'README.md': ['README.md', 0o644],
  'VERSION': ['VERSION', 0o644],
};
for (const [source, [target, mode]] of Object.entries(panel)) {
  await copy(path.join(panelSource, source), target, mode);
}

// The unit shipped with the panel hardcodes the standalone install path; the
// plugin renders it for the Steam user it detects at install time instead.
const unit = path.join(payload, 'sf-fan-qamd.service');
const text = await readFile(unit, 'utf8');
if (!text.includes('/home/steamos/sf-fan-qam/')) {
  throw new Error('Unexpected systemd unit; cannot substitute the install path');
}
await writeFile(unit, text.replaceAll('/home/steamos/sf-fan-qam', '@INSTALL_DIR@'));

// The README talks about the standalone release archives, which do not exist
// inside a Framely package; point readers at the repository instead.
const readme = path.join(payload, 'README.md');
await writeFile(readme, (await readFile(readme, 'utf8'))
  .replace('cd ~/sf-fan-qam-1.0.0\nsudo ./install.sh',
           'cd ~/sf-fan-qam-1.0.0\nsudo ./install.sh   # 或直接在 Framely 插件页点「安装」')
  .replace('cd ~/sf-fan-qam-1.0.0\nsudo ./uninstall.sh',
           'cd ~/sf-fan-qam-1.0.0\nsudo ./uninstall.sh  # 或直接在 Framely 插件页点「卸载」'));

const version = (await readFile(path.join(root, 'VERSION'), 'utf8')).trim();
const manifest = JSON.parse(await readFile(path.join(root, 'manifest.json'), 'utf8'));
if (manifest.version !== version) {
  throw new Error(`manifest.version ${manifest.version} != VERSION ${version}`);
}
console.log('Built payload for ' + manifest.id + ' ' + version);
