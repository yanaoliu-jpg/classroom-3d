import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const HERE = dirname(fileURLToPath(import.meta.url));
export const ROOT = resolve(HERE, '..', '..');
export const HTML = join(ROOT, 'classroom_v4_3.html');
export const OUT = join(ROOT, 'bake', 'out');

// 去掉末尾数据块的副本：用来验证"缺数据 → 回退"
export function noDataCopy() {
  mkdirSync(OUT, { recursive: true });
  const s = readFileSync(HTML, 'utf8').replace(/<script id="bakedData">[\s\S]*?<\/script>/, '');
  const p = join(OUT, 'nodata.html');
  writeFileSync(p, s);
  return p;
}

export const errorsIn = logs => logs.filter(l => /^(error|exception)/.test(l) || /Shader Error|WebGLProgram/.test(l));
