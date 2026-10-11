// 导出模拟器里的真实几何 + 元数据，供 Blender 烘焙。用法：node bake/export_scene.mjs [html路径]
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { launch, fileUrl } from './cdp.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const html = resolve(process.argv[2] || join(root, 'classroom_v4_3.html'));
const out = join(here, 'out');
mkdirSync(out, { recursive: true });
const iife = join(out, 'gltf-exporter.iife.js');
if (!existsSync(iife)) { console.error('缺少 ' + iife + '，先运行 node bake/build_exporter.mjs'); process.exit(1); }

const b = await launch();
try {
  await b.goto(fileUrl(html));
  // 新贴图换上之后再导出（反照率决定反弹光颜色）；没有烘焙数据接入段时 __GI 不存在，直接放行
  await b.waitFor("!window.__GI || window.__GI.texStatus !== 'pending'");
  await b.evaluate(readFileSync(iife, 'utf8') + '; true');
  const meta = await b.evaluate(readFileSync(join(here, 'export_in_page.js'), 'utf8'));
  const parts = [];
  for (let i = 0; i < meta.chunks; i++) parts.push(Buffer.from(await b.evaluate(`window.__bakeChunks[${i}]`), 'base64'));
  const glb = Buffer.concat(parts);
  if (glb.length !== meta.bytes) throw new Error(`GLB 长度不符 ${glb.length} != ${meta.bytes}`);
  writeFileSync(join(out, 'scene.glb'), glb);
  delete meta.chunks;
  writeFileSync(join(out, 'scene_meta.json'), JSON.stringify(meta, null, 1));
  console.log(`scene.glb ${(glb.length / 1e6).toFixed(1)}MB`, JSON.stringify(meta.stats));
  const errs = b.logs.filter(l => /^(error|exception)/.test(l));
  if (errs.length) console.warn('页面报错：\n' + errs.join('\n'));
} finally {
  await b.close();
}
