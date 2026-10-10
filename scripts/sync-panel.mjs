#!/usr/bin/env node
/**
 * Refresh vendor/fan-panel from the standalone fan panel project.
 *
 * The plugin ships a pinned copy of the fan panel so its release build never
 * depends on a sibling checkout. Re-run this after changing the panel:
 *
 *   node scripts/sync-panel.mjs                       # ../debjoyframe1/sf-fan-qam
 *   FAN_PANEL_SOURCE=/path/to/sf-fan-qam node scripts/sync-panel.mjs
 *
 * It rewrites vendor/fan-panel/VENDOR.json, which scripts/build.mjs and
 * tests/test_manifest.py use to prove the vendored copy is intact.
 */
import {createHash} from 'node:crypto';
import {copyFile, mkdir, readFile, rm, writeFile} from 'node:fs/promises';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const source = process.env.FAN_PANEL_SOURCE
  ? path.resolve(process.env.FAN_PANEL_SOURCE)
  : path.resolve(root, '..', 'debjoyframe1', 'sf-fan-qam');
const vendor = path.join(root, 'vendor', 'fan-panel');

// Keep in sync with the `panel` map in scripts/build.mjs.
const FILES = [
  ['device/sf_fan_qamd.py', 'device/sf_fan_qamd.py'],
  ['device/sf_fan_qam.js', 'device/sf_fan_qam.js'],
  ['device/sf-fan-qamd.service', 'device/sf-fan-qamd.service'],
  ['README.md', 'README.md'],
  ['VERSION', 'VERSION'],
];

await rm(vendor, {recursive: true, force: true});
await mkdir(vendor, {recursive: true});

const files = {};
for (const [from, to] of FILES) {
  const target = path.join(vendor, to);
  await mkdir(path.dirname(target), {recursive: true});
  await copyFile(path.join(source, from), target);
  files[to] = createHash('sha256').update(await readFile(target)).digest('hex');
}

await writeFile(path.join(vendor, 'VENDOR.json'), JSON.stringify({
  repository: 'https://github.com/dhies23/steam-frame-fan-panel',
  source: 'sf-fan-qam',
  version: (await readFile(path.join(vendor, 'VERSION'), 'utf8')).trim(),
  files,
}, null, 2) + '\n');

console.log(`Synced ${Object.keys(files).length} panel files from ${source}`);
