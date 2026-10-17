// 生成 bake/out/gltf-exporter.iife.js（只给导出工具注入页面用，不进主文件）
import { mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from '../vendor/node_modules/esbuild/lib/main.js';

const here = dirname(fileURLToPath(import.meta.url));
mkdirSync(join(here, 'out'), { recursive: true });
await build({
  entryPoints: [join(here, 'exporter-entry.mjs')],
  bundle: true,
  format: 'iife',
  outfile: join(here, 'out', 'gltf-exporter.iife.js'),
  alias: { three: join(here, 'three-global.cjs') },
  logLevel: 'warning',
});
console.log('ok: bake/out/gltf-exporter.iife.js');
