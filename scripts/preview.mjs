#!/usr/bin/env node
/**
 * Build the quick page into a standalone HTML file with a fake Framely bridge.
 *
 *   node scripts/preview.mjs [output.html]
 *
 * The page is the real `src/page.tsx`; only `window.__framelyBridge` is faked,
 * so this doubles as a smoke test that the bundle runs without a host.
 *
 * The output is a normal web page; open it in any browser, or run
 * `scripts/preview.ps1` to build and screenshot it in one step.
 */
import {build} from 'esbuild';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const output = path.resolve(process.argv[2] ?? path.join(root, '.preview/preview.html'));
const work = path.dirname(output);

const sample = {
  hardware: {supported: true, fanPath: '/sys/class/hwmon/hwmon3', message: null},
  daemon: {installed: true, enabled: true, active: true, pid: 4213,
           since: 'Fri 2026-10-09 21:14:02 CST', version: '1.0.0',
           path: '/home/steamos/sf-fan-qam'},
  snapshot: {rpm: 2459, pwm: 30, mode: 'auto',
             temps: {cpu: 48.2, gpu: 44.6, soc: 52.1, ddr: 41.0,
                     heatsink: 38.5, exhaust: 36.9},
             stockActive: true},
  bundled: '1.0.0',
  unit: {name: 'sf-fan-qamd.service', path: '/etc/systemd/system/sf-fan-qamd.service'},
  stock: {name: 'deckard-fan-control.service', active: true},
};

const harness = `
window.__framelyBridge = {
  request: (op, params) => {
    if (op === 'call') {
      if (params && params.method === 'status') return Promise.resolve(${JSON.stringify(sample)});
      return Promise.resolve({ok: true, message: '（预览）'});
    }
    if (op === 'language.get') return Promise.resolve({preference: 'system', language: 'zh-CN'});
    if (op === 'ui.visibility.get') return Promise.resolve({known: true, captureObscured: false, pageVisible: true, sequence: 1});
    return Promise.resolve(null);
  },
  subscribe: () => () => {},
};
import('../src/page.tsx');
`;

await mkdir(work, {recursive: true});
await writeFile(path.join(work, 'harness.tsx'), harness);
await build({
  entryPoints: [path.join(work, 'harness.tsx')],
  bundle: true,
  outfile: path.join(work, 'bundle.js'),
  loader: {'.css': 'text'},
  define: {'process.env.NODE_ENV': '"production"'},
  resolveExtensions: ['.tsx', '.ts', '.js'],
});
const script = await readFile(path.join(work, 'bundle.js'), 'utf8');
await writeFile(output, `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>Frame 风扇面板</title>
<style>body{margin:0;background:#0d141b;display:flex;justify-content:center}
#root{width:520px;min-height:900px;background:#101820}</style>
</head><body><div id="root"></div>
<script>${script}</script>
</body></html>`);
console.log(output);
