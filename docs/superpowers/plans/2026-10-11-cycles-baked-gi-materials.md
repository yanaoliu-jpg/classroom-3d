# Cycles 烘焙 GI + 材质升级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Blender Cycles 离线烘焙"探针体积"全局光照 + 生成高质量材质贴图，回灌进 `classroom_v4_3.html`，让实时画面接近路径追踪参考图，同时帧率不降。

**Architecture:** 离线管线在 `bake/`：Node+CDP 驱动无头 Chrome 导出真实几何 → Blender（Python，后台）按光源分组烘焙约 2.2 万个探针的六面辐照度 + 生成贴图 → 系统 Python 修补/编码 → `embed.py` 写入 HTML 末尾 `<script id="bakedData">`。运行时在加载完成后异步解码，GPU 一次合成"当前间接光"图集，所有 PBR 材质的着色器在教室/走廊体积内用它替换半球光/环境光，并拆掉 11 盏假补光。

**Tech Stack:** three.js r164（已内联）、Blender 5.2.2 Cycles（Metal GPU）、Node 24（内置 WebSocket/fetch，`node --test`）、Python 3.14 + numpy + Pillow（`python3 -m unittest`）、Google Chrome 无头 + ANGLE Metal、esbuild（vendor 里已有）。

**Spec:** `docs/superpowers/specs/2026-10-11-cycles-baked-gi-materials-design.md`

## Global Constraints

- 不用任何补帧手段：无动态分辨率 / 运动模糊 / TAA / 帧生成（项目铁律）。
- 帧率 ≥ 改前：`性能优化计划.md` 的 readPixels 强制同步计时，4 预设 × 5 机位 + 监控墙。
- 仍是单个 HTML 直接打开；烘焙数据只放在文件末尾 `<script id="bakedData">`（`bake/embed.py` 生成）；缺数据 → 画面与改前一致。
- three.js 版本与 vendor bundle 不变；GLTFExporter 只存在于 `bake/` 工具里，不进主文件。
- 灯的数量只在加载期改变（拆灯在烘焙数据激活时一次完成），运行时不改灯数；激活后对"在教室/在走廊"两种灯数组合各预编译一次。
- 早期就会执行的代码读到的 `let/const` 必须在渲染器初始化处声明（TDZ，本文件已踩三次）：新增的 `giPresetKey` 放在 `let monitorOn = false;` 旁边。
- Blender 路径 `/Applications/Blender.app/Contents/MacOS/Blender`，统一 `-b --factory-startup`；Cycles 设备 METAL；首次运行要编译内核（实测约 144s）。
- Poly Haven 只用 `ash_veneer`、`plywood`（CC0，dl.polyhaven.org），原始下载不进 git（`bake/assets/`、`bake/out/` 加入 `.gitignore`）。
- HTML 总体积 ≤ 10MB。
- 提交在 `feat/cycles-baked-gi` 分支，提交信息以 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` 结尾；合并回 main 需用户确认。
- 单位约定（已实测）：Cycles 漫反射通道 = E/π；Blender Sun 强度 = three DirectionalLight 强度；Blender 点光功率 = 4π × three 点光强度；Blender 坐标 (x,y,z) = three (x,−z,y)。

## Review Focus

1. **某种材质变体的着色器编译失败**（InstancedMesh+instanceColor、DoubleSide、无贴图/有法线贴图、带自发光）——激活后控制台必须没有 `Shader Error` / `WebGLProgram` 报错，且画面不是黑屏。→ Task 7 测试 `控制台无着色器错误`。
2. **监控墙（M）与 GI 合成同帧运行**——合成通道切换渲染目标后，监控墙的分格视口/裁剪仍正确、阴影图更新不被吞掉。→ Task 7 测试 `监控墙与 GI 共存`。
3. **时间轴全天推移**——每帧都要重新合成；夜间太阳在地平线下、太阳关键帧两端外推时权重仍有限且非负。→ Task 7 测试 `时间轴全天推移权重有限`。
4. **切天气 / 深夜预设**——天光权重要跟着变（雨天更灰更暗、深夜接近暗蓝），不能停在晴天值。→ Task 7 测试 `天气与深夜改变天光权重`。
5. **相机穿过右墙进出走廊**——走廊直射组权重要随之切换（走廊里由实时灯接管），且不触发新的着色器编译卡顿。→ Task 7 测试 `进出走廊切换走廊直射组`。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `bake/cdp.mjs` | 无依赖 CDP 小工具：启动无头 Chrome、导航、执行 JS、取画布 PNG |
| `bake/three-global.cjs`、`bake/exporter-entry.mjs`、`bake/build_exporter.mjs` | 把 GLTFExporter 打包成使用页面 `window.THREE` 的 IIFE |
| `bake/export_in_page.js` | 在页面内执行：筛真实几何、展开实例、导出 GLB、收集元数据 |
| `bake/export_scene.mjs` | 导出入口：`bake/out/scene.glb` + `scene_meta.json` |
| `bake/fetch_polyhaven.py` | 下载两套木纹原图 |
| `bake/blender_floor.py` | Blender：倒角瓷砖几何 → 烘焙法线/AO |
| `bake/tex_lib.py`、`bake/pack_textures.py` | numpy 程序化贴图（墙漆/吸音板/地砖反照率与粗糙度）、木纹调色、WebP 输出 |
| `bake/embed.py` | 把贴图与 GI 数据写入 HTML 末尾数据块（幂等） |
| `bake/gi_lib.py` | 探针网格、图集布局、对数编码、坏探针修补（Blender 与系统 Python 共用） |
| `bake/blender_common.py`、`bake/blender_gi.py` | Blender：导入、灯光分组、探针、逐组 Cycles 烘焙 |
| `bake/pack_gi.py` | 原始探针 → `gi_atlas.png` + `gi.json` |
| `bake/capture_views.mjs`、`bake/blender_reference.py`、`bake/compare.py` | 同机位截图 / Cycles 参考图 / 三联图与偏差统计 |
| `bake/bench.mjs` | 帧率基准（改前 vs 改后） |
| `bake/run_all.sh`、`bake/README.md` | 一键重烘 + 说明 |
| `bake/tests/*` | 单测与集成测试 |
| `classroom_v4_3.html` | 新增"烘焙数据接入"脚本段（贴图 + GI）、少量钩子、末尾数据块 |

---

### Task 1: 场景导出工具链（CDP + GLTFExporter）

**Files:**
- Create: `bake/cdp.mjs`, `bake/three-global.cjs`, `bake/exporter-entry.mjs`, `bake/build_exporter.mjs`, `bake/export_in_page.js`, `bake/export_scene.mjs`
- Create: `bake/tests/test_export.py`, `bake/tests/blender_import_smoke.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `launch({width,height}) → {send, evaluate(expr), waitFor(expr,ms), goto(url,readyExpr), canvasPNG(path), close(), logs}`；`fileUrl(path, hash)`。
- Produces: `bake/out/scene.glb`（只含 MeshStandardMaterial 网格、实例已展开、无自发光）；`bake/out/scene_meta.json` = `{stats, bytes, room:{RW,RD,RH,BACK_Z,CORR_X0,CORR_X1,CORR_Z0,CORR_Z1}, lights:{ceil:[[x,y,z]×12], corr:[[x,y,z]×8]}, sunKeys:[{angle,dir:[x,y,z]}×9], views:{'5'|'6'|'7'|'9'|'0': {name,fov,aspect,position,quaternion}}}`（three 坐标）。

- [ ] **Step 1: 忽略生成物**

在 `.gitignore` 末尾追加：

```
bake/out/
bake/assets/
```

- [ ] **Step 2: 写失败的导出测试**

`bake/tests/test_export.py`：

```python
import json, struct, unittest
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'out'

class TestExport(unittest.TestCase):
    def test_glb_header(self):
        b = (OUT / 'scene.glb').read_bytes()
        magic, ver, length = struct.unpack('<4sII', b[:12])
        self.assertEqual(magic, b'glTF')
        self.assertEqual(ver, 2)
        self.assertEqual(length, len(b))

    def test_meta(self):
        m = json.loads((OUT / 'scene_meta.json').read_text())
        self.assertEqual(len(m['lights']['ceil']), 12)
        self.assertEqual(len(m['lights']['corr']), 8)
        self.assertEqual([k['angle'] for k in m['sunKeys']], list(range(-80, 81, 20)))
        for k in m['sunKeys']:
            self.assertLess(k['dir'][1], 0)          # 光从上往下照
            self.assertGreater(k['dir'][0], 0)       # 太阳恒在左窗外(-x)，光朝 +x
        self.assertGreater(m['stats']['meshes'] + m['stats']['instances'], 500)
        self.assertEqual(set(m['views']), {'5', '6', '7', '9', '0'})

if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 3: 运行，确认失败**

Run: `cd /Users/liuyanao/Desktop/修复-光影模拟器 && python3 -m unittest bake/tests/test_export.py -v`
Expected: FAIL / ERROR（`scene.glb` 不存在）

- [ ] **Step 4: CDP 小工具**

`bake/cdp.mjs`：

```js
// 无依赖的 Chrome DevTools Protocol 小工具（Node ≥ 22：内置 WebSocket / fetch）。
// 用于导出场景、截图、帧率基准、运行时集成测试。全部跑在无头 Chrome + ANGLE Metal 上。
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

export const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const sleep = ms => new Promise(r => setTimeout(r, ms));

// 路径含中文（"修复"），必须走 pathToFileURL 编码
export function fileUrl(path, hash = '') {
  return pathToFileURL(path).href + (hash ? '#' + hash : '');
}

export async function launch({ width = 1600, height = 900 } = {}) {
  const port = 9300 + Math.floor(Math.random() * 600);
  const userDir = mkdtempSync(join(tmpdir(), 'cdp-'));
  const proc = spawn(CHROME, [
    '--headless=new', '--use-angle=metal', '--enable-webgl', '--ignore-gpu-blocklist',
    '--hide-scrollbars', `--window-size=${width},${height}`,
    `--remote-debugging-port=${port}`, `--user-data-dir=${userDir}`,
    '--no-first-run', '--no-default-browser-check', 'about:blank',
  ], { stdio: 'ignore' });
  let page = null;
  for (let i = 0; i < 150 && !page; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      page = list.find(t => t.type === 'page') || null;
    } catch { /* 还没起来 */ }
    if (!page) await sleep(200);
  }
  if (!page) { proc.kill('SIGKILL'); throw new Error('Chrome 没有启动'); }
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let seq = 0;
  const pending = new Map();
  const logs = [];
  ws.onmessage = ev => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
    } else if (msg.method === 'Runtime.consoleAPICalled') {
      logs.push(`${msg.params.type}: ` + msg.params.args.map(a => a.value ?? a.description ?? '').join(' '));
    } else if (msg.method === 'Runtime.exceptionThrown') {
      const d = msg.params.exceptionDetails;
      logs.push('exception: ' + (d.exception?.description || d.text));
    }
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++seq;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
  await send('Page.enable');
  await send('Runtime.enable');

  async function evaluate(expression, timeout = 600000) {
    const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true, timeout });
    if (r.exceptionDetails) {
      throw new Error('页面内报错: ' + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
    }
    return r.result.value;
  }
  async function waitFor(expr, ms = 120000) {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) {
      try { if (await evaluate(`!!(${expr})`)) return; } catch { /* 页面还在加载 */ }
      await sleep(250);
    }
    throw new Error('等待超时: ' + expr);
  }
  async function goto(url, readyExpr = "document.readyState === 'complete' && typeof composer !== 'undefined'") {
    await send('Page.navigate', { url });
    await waitFor(readyExpr);
  }
  // 只取 WebGL 画布（preserveDrawingBuffer=true），不含 DOM 界面与 2D 叠层（辉光/颗粒/暗角）
  async function canvasPNG(path) {
    const b64 = await evaluate(`renderer.domElement.toDataURL('image/png').split(',')[1]`);
    writeFileSync(path, Buffer.from(b64, 'base64'));
  }
  async function close() {
    try { ws.close(); } catch { /* 已关闭 */ }
    proc.kill('SIGKILL');
    await sleep(300);
    rmSync(userDir, { recursive: true, force: true });
  }
  return { send, evaluate, waitFor, goto, canvasPNG, close, logs };
}
```

- [ ] **Step 5: 打包 GLTFExporter（使用页面里的 THREE）**

`bake/three-global.cjs`：

```js
// esbuild 别名目标：让 GLTFExporter 里的 `import … from 'three'` 用页面已有的 window.THREE
// （同一套类，instanceof 判断才成立；也不必再打进第二份 three）
module.exports = window.THREE;
```

`bake/exporter-entry.mjs`（用相对路径引入，避免 `three` 别名误伤 `three/examples/...` 子路径）：

```js
import { GLTFExporter } from '../vendor/node_modules/three/examples/jsm/exporters/GLTFExporter.js';
window.__GLTFExporter = GLTFExporter;
```

`bake/build_exporter.mjs`：

```js
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
```

Run: `node bake/build_exporter.mjs`
Expected: `ok: bake/out/gltf-exporter.iife.js`

- [ ] **Step 6: 页面内导出脚本**

`bake/export_in_page.js`（整段作为一个表达式被 CDP 求值，返回元数据）：

```js
// 在模拟器页面里执行（export_scene.mjs 经 CDP 注入）。依赖页面全局：THREE / scene / fluoroLights /
// corrLampLights / CAM_VIEWS / applyViewToCamera / SUN_DIST / RW / RD / RH / BACK_Z / CORR_*，
// 以及先注入的 window.__GLTFExporter。
(async () => {
  const T = THREE;
  const visibleDeep = o => { for (let p = o; p; p = p.parent) if (p.visible === false) return false; return true; };
  // 只要"真实受光"的几何：MeshBasicMaterial 全是假贴片/光晕/标记；透明度 < 0.5 的是玻璃（不挡光）
  const exportable = m => m && m.isMeshStandardMaterial && m.visible !== false && !(m.transparent && m.opacity < 0.5);
  scene.updateMatrixWorld(true);
  const out = new T.Scene();
  const cache = new Map();
  // 导出用材质：只留反照率/粗糙度/金属度/单双面；不带自发光（灯由 Blender 里的光源代表）
  const conv = (m, tint) => {
    const key = m.uuid + (tint ? '|' + tint.getHexString() : '');
    if (cache.has(key)) return cache.get(key);
    const e = new T.MeshStandardMaterial({
      color: m.color.clone(), roughness: m.roughness, metalness: m.metalness,
      map: m.map || null, side: m.side, name: m.name || ('m' + cache.size),
    });
    if (tint) e.color.multiply(tint);
    cache.set(key, e);
    return e;
  };
  const stats = { meshes: 0, instances: 0, skippedNonStandard: 0, skippedTransparent: 0, skippedHidden: 0 };
  const _m = new T.Matrix4(), _c = new T.Color();
  scene.traverse(o => {
    if (!o.isMesh) return;
    if (!visibleDeep(o)) { stats.skippedHidden++; return; }
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    if (mats.some(m => m && !m.isMeshStandardMaterial)) { stats.skippedNonStandard++; return; }
    if (!mats.every(exportable)) { stats.skippedTransparent++; return; }
    let tint = null;
    if (o.isInstancedMesh && o.instanceColor) {   // 逐实例色只差 ±2%：取平均色作为这批实例的反照率
      const acc = new T.Color(0, 0, 0);
      for (let i = 0; i < o.count; i++) { o.getColorAt(i, _c); acc.r += _c.r; acc.g += _c.g; acc.b += _c.b; }
      tint = new T.Color(acc.r / o.count, acc.g / o.count, acc.b / o.count);
    }
    const em = Array.isArray(o.material) ? o.material.map(m => conv(m, tint)) : conv(o.material, tint);
    const n = o.isInstancedMesh ? o.count : 1;
    for (let i = 0; i < n; i++) {
      const mesh = new T.Mesh(o.geometry, em);
      mesh.matrixAutoUpdate = false;
      if (o.isInstancedMesh) { o.getMatrixAt(i, _m); mesh.matrix.multiplyMatrices(o.matrixWorld, _m); stats.instances++; }
      else { mesh.matrix.copy(o.matrixWorld); stats.meshes++; }
      mesh.name = (o.name || o.geometry.type) + '_' + (stats.meshes + stats.instances);
      out.add(mesh);
    }
  });
  const glb = await new window.__GLTFExporter().parseAsync(out, { binary: true, maxTextureSize: 1024, onlyVisible: false });
  // ArrayBuffer → base64，按 3MB 分块交给 Node（单条 CDP 消息不宜过大）
  const bytes = new Uint8Array(glb);
  const CH = 3 * 1024 * 1024, chunks = [];
  for (let i = 0; i < bytes.length; i += CH) {
    const sub = bytes.subarray(i, Math.min(bytes.length, i + CH));
    let s = '';
    for (let j = 0; j < sub.length; j += 0x8000) s += String.fromCharCode.apply(null, sub.subarray(j, j + 0x8000));
    chunks.push(btoa(s));
  }
  window.__bakeChunks = chunks;

  const v3 = v => [v.x, v.y, v.z].map(x => +x.toFixed(5));
  const wp = o => v3(o.getWorldPosition(new T.Vector3()));
  // 太阳关键帧：与静态 sync() 完全相同的轨迹公式（角度滑块 a → 光源位置），方向 = 目标 − 光源
  const sunKeys = [];
  for (let a = -80; a <= 80; a += 20) {
    const rad = a * Math.PI / 180, sunH = Math.max(0, 1 - Math.abs(a) / 78);
    const pos = new T.Vector3(-9 * SUN_DIST, 0.4 + (1.0 + sunH * 26 - 0.4) * SUN_DIST, 6 + Math.sin(rad) * 7 * SUN_DIST);
    sunKeys.push({ angle: a, dir: v3(new T.Vector3(0, 0.4, 6).sub(pos).normalize()) });
  }
  const cam = new T.PerspectiveCamera(60, 16 / 9, 0.3, 80);
  const views = {};
  for (const [k, v] of Object.entries(CAM_VIEWS)) {
    applyViewToCamera(v, cam); cam.fov = v.fov; cam.updateMatrixWorld(true);
    views[k] = { name: v.name, fov: v.fov, aspect: 16 / 9, position: v3(cam.position),
                 quaternion: [cam.quaternion.x, cam.quaternion.y, cam.quaternion.z, cam.quaternion.w] };
  }
  return {
    stats, chunks: chunks.length, bytes: bytes.length,
    room: { RW, RD, RH, BACK_Z, CORR_X0, CORR_X1, CORR_Z0, CORR_Z1 },
    lights: { ceil: fluoroLights.map(wp), corr: corrLampLights.map(wp) },
    sunKeys, views,
  };
})()
```

- [ ] **Step 7: 导出入口**

`bake/export_scene.mjs`：

```js
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
```

- [ ] **Step 8: 运行导出，测试转绿**

Run: `node bake/export_scene.mjs && python3 -m unittest bake/tests/test_export.py -v`
Expected: 打印 `scene.glb …MB {"meshes":…}`，2 个测试 PASS。

- [ ] **Step 9: Blender 导入冒烟测试**

`bake/tests/blender_import_smoke.py`：

```python
# blender -b --factory-startup -P bake/tests/blender_import_smoke.py
import sys
from pathlib import Path
import bpy
from mathutils import Vector

OUT = Path(__file__).resolve().parents[1] / 'out'
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(OUT / 'scene.glb'))
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
mn = Vector((1e9, 1e9, 1e9)); mx = Vector((-1e9, -1e9, -1e9))
for o in meshes:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        mn = Vector(map(min, mn, w)); mx = Vector(map(max, mx, w))
culled = sum(1 for m in bpy.data.materials if m.use_backface_culling)
print('SMOKE meshes', len(meshes), 'bbox', tuple(round(v, 2) for v in mn), tuple(round(v, 2) for v in mx),
      'single-sided mats', culled, '/', len(bpy.data.materials))
# three(x,y,z) → blender(x,-z,y)：教室 x∈[-7,7]、走廊到 x=8.9、层高 3.5（屋顶到 3.9）
ok = len(meshes) > 500 and mn.x <= -7.0 and mx.x >= 8.8 and mx.z >= 3.4
print('SMOKE', 'OK' if ok else 'FAIL')
sys.exit(0 if ok else 1)
```

Run: `/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P bake/tests/blender_import_smoke.py 2>&1 | grep SMOKE`
Expected: `SMOKE … ` 与 `SMOKE OK`；单面材质数 > 0（证明 glTF 的 doubleSided 被正确导入成背面剔除标记，Task 4 判坏探针要用）。

- [ ] **Step 10: Commit**

```bash
git add .gitignore bake/cdp.mjs bake/three-global.cjs bake/exporter-entry.mjs bake/build_exporter.mjs bake/export_in_page.js bake/export_scene.mjs bake/tests/test_export.py bake/tests/blender_import_smoke.py
git commit -m "feat(bake): 场景导出工具链（CDP 无头 Chrome + GLTFExporter → scene.glb/元数据）

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 材质贴图（Poly Haven 木纹 + Blender 倒角瓷砖 + 程序化墙漆/吸音板）与运行时接入

**Files:**
- Create: `bake/fetch_polyhaven.py`, `bake/blender_common.py`（本任务先写 Cycles/世界/设备部分，Task 4 追加探针函数）, `bake/blender_floor.py`, `bake/tex_lib.py`, `bake/pack_textures.py`, `bake/embed.py`
- Create: `bake/tests/test_tex_lib.py`, `bake/tests/test_embed.py`, `bake/tests/runtime_textures.test.mjs`, `bake/tests/helpers.mjs`
- Modify: `classroom_v4_3.html`（tileMesh 打标签；`- / =` 地面反照率热键改读活基准；新增"烘焙数据接入"脚本段；末尾数据块由 embed.py 写入）
- Modify: `docs/superpowers/specs/2026-10-11-cycles-baked-gi-materials-design.md`（D8 表：墙漆/吸音板改为 numpy 程序化，地砖法线/AO 由 Blender 倒角几何烘焙）

**Interfaces:**
- Produces（tex_lib）：`periodic_noise(n, beta, seed, fmin=1.0, fmax=None) → (n,n)∈[0,1]`、`normal_from_height(h, strength) → (n,n,3)∈[0,1]`、`linear_to_srgb(x)`、`srgb_to_linear(x)`、`seam_ratio(img) → float`、`gaussian_blur_periodic(img, sigma)`、`make_wall(n, seed) → (albedo_srgb, normal)`、`make_ceiling_tile(n, seed) → (albedo_srgb, normal)`、`make_floor(ao, n, seed) → (albedo_srgb, rough)`、`grade_to_mean(img_srgb, target_srgb) → img_srgb`。
- Produces：`bake/out/tex/tex.json` = `{floor:{albedo,normal,rough,size:2.4,tint:[r,g,b]}, wall:{albedo,normal,size:2.0}, ceilTile:{albedo,normal}, ash:{albedo,normal,rough,size:1.0}, plywood:{albedo,normal,rough,size:0.5}}`（文件名为同目录 .webp）。
- Produces（embed）：`build_payload(out) → {version:1, textures:{meta, <kind>_<slot>:dataURI}|None, gi:{meta, atlas}|None}`、`render_block(payload) → str`、`embed(html_path, payload) → int`。
- Produces（运行时）：`window.__GI = {status, texStatus, active, ...}`；`texStatus ∈ 'pending'|'active'|'absent'|'error'`。

- [ ] **Step 1: 写失败的 tex_lib 单测**

`bake/tests/test_tex_lib.py`：

```python
import sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tex_lib as X

class TestTexLib(unittest.TestCase):
    def test_periodic_noise_is_seamless(self):
        n = X.periodic_noise(256, 2.0, seed=1, fmin=2, fmax=40)
        self.assertEqual(n.shape, (256, 256))
        self.assertAlmostEqual(float(n.min()), 0.0, places=6)
        self.assertAlmostEqual(float(n.max()), 1.0, places=6)
        self.assertLess(X.seam_ratio(n), 1.6)

    def test_seam_ratio_detects_seam(self):
        ramp = np.tile(np.linspace(0, 1, 256), (256, 1))      # 左黑右白 → 首尾强跳变
        self.assertGreater(X.seam_ratio(ramp), 20)

    def test_normal_orientation(self):
        # 高度向右(+u)升高 → 法线朝 -u 倾斜（红 < 0.5）
        h = np.tile(np.sin(np.linspace(0, 2 * np.pi, 64, endpoint=False)), (64, 1))
        n = X.normal_from_height(h, 4.0)
        col = 16                                              # sin 上升段
        self.assertLess(n[10, col, 0], 0.5)
        # 高度向图像上方(行号变小 = +v)升高 → 法线朝 -v 倾斜（绿 < 0.5）
        hv = np.tile(np.cos(np.linspace(0, 2 * np.pi, 64, endpoint=False))[:, None], (1, 64))
        nv = X.normal_from_height(hv, 4.0)
        row = 16                                              # cos 在此处随行号增加而下降 → 向上(行号减小)升高
        self.assertLess(nv[row, 10, 1], 0.5)
        self.assertTrue(np.all(n[..., 2] > 0.5))

    def test_srgb_roundtrip(self):
        x = np.linspace(0, 1, 101)
        self.assertLess(np.abs(X.srgb_to_linear(X.linear_to_srgb(x)) - x).max(), 1e-9)

    def test_wall_is_subtle_and_seamless(self):
        a, n = X.make_wall(256, seed=3)
        self.assertEqual(a.shape, (256, 256, 3))
        self.assertLess(abs(float(a.mean()) - 0.97), 0.01)
        self.assertLess(float(a.max() - a.min()), 0.08)
        self.assertGreater(float((n[..., 2] * 2 - 1).mean()), 0.97)   # 法线几乎朝外：只是微纹
        self.assertLess(X.seam_ratio(n[..., 0]), 1.6)

    def test_floor_grout_darker_and_tiles_shiny(self):
        ao = np.ones((512, 512))
        alb, rough = X.make_floor(ao, n=512, seed=5)
        lum = alb.mean(-1)
        grout = lum[0, :].mean()                 # 第 0 行正好落在缝上（半缝在贴图边沿）
        tile = lum[64, 64]
        self.assertLess(grout, tile * 0.85)
        self.assertGreater(rough[0, 5], 0.8)     # 缝哑
        self.assertLess(rough[64, 64], 0.5)      # 砖面光
        self.assertLess(X.seam_ratio(lum), 1.6)

    def test_grade_to_mean(self):
        img = np.random.default_rng(0).random((64, 64, 3))
        g = X.grade_to_mean(img, [0.70, 0.54, 0.36])
        lin_mean = X.srgb_to_linear(g).mean(axis=(0, 1))
        self.assertTrue(np.allclose(lin_mean, X.srgb_to_linear(np.array([0.70, 0.54, 0.36])), atol=0.01))

if __name__ == '__main__':
    unittest.main()
```

Run: `python3 -m unittest bake/tests/test_tex_lib.py -v`
Expected: ERROR（`No module named 'tex_lib'`）

- [ ] **Step 2: 实现 tex_lib**

`bake/tex_lib.py`：

```python
"""程序化贴图工具（numpy）：四方连续噪声、法线、色彩空间、墙漆/吸音板/地砖生成、木纹调色。
约定：所有图像数组"行 0 = 图像顶部 = 纹理 v=1"（three.js 读图片时 flipY=true）。"""
import numpy as np

def periodic_noise(n, beta, seed, fmin=1.0, fmax=None):
    """四方连续 1/f^beta 噪声（FFT 合成，天然无缝），归一化到 [0,1]。fmin/fmax 以"每张贴图的周期数"计。"""
    rng = np.random.default_rng(seed)
    white = rng.standard_normal((n, n))
    fy = np.fft.fftfreq(n)[:, None] * n
    fx = np.fft.fftfreq(n)[None, :] * n
    f = np.sqrt(fx ** 2 + fy ** 2)
    m = f >= fmin
    if fmax is not None:
        m &= f <= fmax
    amp = np.zeros_like(f)
    amp[m] = f[m] ** (-beta / 2.0)
    out = np.real(np.fft.ifft2(np.fft.fft2(white) * amp))
    out -= out.min()
    out /= max(out.max(), 1e-12)
    return out

def gaussian_blur_periodic(img, sigma):
    n0, n1 = img.shape
    fy = np.fft.fftfreq(n0)[:, None]
    fx = np.fft.fftfreq(n1)[None, :]
    k = np.exp(-2.0 * (np.pi ** 2) * (sigma ** 2) * (fx ** 2 + fy ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(img) * k))

def normal_from_height(h, strength):
    """高度图 → OpenGL 切线空间法线 RGB∈[0,1]（绿 = +v = 图像上方）。周期边界。"""
    h = np.asarray(h, np.float64)
    dhdu = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5
    dhdrow = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * 0.5
    dhdv = -dhdrow                         # 行号向下增加，v 向上增加
    nx, ny, nz = -dhdu * strength, -dhdv * strength, np.ones_like(h)
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx * inv, ny * inv, nz * inv], -1) * 0.5 + 0.5

def linear_to_srgb(x):
    x = np.clip(np.asarray(x, np.float64), 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)

def srgb_to_linear(x):
    x = np.clip(np.asarray(x, np.float64), 0, 1)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))

def seam_ratio(img):
    """接缝检查：首尾行/列的跳变 ÷ 内部相邻行/列的平均跳变。≈1 无缝；≫1 有接缝。"""
    a = np.asarray(img, np.float64)
    inner_c = np.mean(np.abs(np.diff(a, axis=1))); edge_c = np.mean(np.abs(a[:, 0] - a[:, -1]))
    inner_r = np.mean(np.abs(np.diff(a, axis=0))); edge_r = np.mean(np.abs(a[0] - a[-1]))
    return max(edge_c / max(inner_c, 1e-12), edge_r / max(inner_r, 1e-12))

def make_wall(n=1024, seed=11):
    """乳胶漆墙面：反照率是均值 0.97、±2% 的低频斑驳（乘在原墙色上，不改墙色）；法线是滚筒橘皮微纹。"""
    mottle = periodic_noise(n, 3.0, seed, fmin=1, fmax=24)
    alb = 0.97 + (mottle - 0.5) * 0.04
    stipple = periodic_noise(n, 1.2, seed + 1, fmin=40) * 0.7 + periodic_noise(n, 2.5, seed + 2, fmin=8, fmax=80) * 0.3
    return np.repeat(alb[..., None], 3, -1), normal_from_height(stipple, strength=1.2)

def make_ceiling_tile(n=1024, seed=21, boards=2):
    """矿棉吸音板（一张贴图 = 一块吊顶面板）：2×2 小板 V 形分缝 + 蠕虫状裂纹 + 针孔。反照率是乘在原色上的明暗。"""
    rng = np.random.default_rng(seed)
    y, x = (np.mgrid[0:n, 0:n] + 0.5) / n
    cx = (x * boards) % 1.0; cy = (y * boards) % 1.0
    edge = np.minimum(np.minimum(cx, 1 - cx), np.minimum(cy, 1 - cy)) / boards
    groove = np.clip(edge / 0.004, 0, 1)                        # 0=缝里 1=板面
    r = periodic_noise(n, 2.2, seed + 1, fmin=6, fmax=160)
    ridge = 1 - np.abs(r - 0.5) * 2
    fiss = np.clip((ridge - 0.86) / 0.1, 0, 1)                  # 裂纹
    holes = np.zeros((n, n))
    pts = (rng.random((int(n * n / 120), 2)) * n).astype(int)
    holes[pts[:, 1] % n, pts[:, 0] % n] = 1.0
    pits = gaussian_blur_periodic(holes, 1.1)
    pits /= max(pits.max(), 1e-12)                              # 针孔
    fine = periodic_noise(n, 1.0, seed + 2, fmin=60)
    height = 0.55 * groove - 0.35 * fiss - 0.6 * pits + 0.05 * fine
    alb = 0.95 - 0.10 * fiss - 0.22 * pits - 0.12 * (1 - groove) + 0.03 * (fine - 0.5)
    return np.repeat(np.clip(alb, 0, 1)[..., None], 3, -1), normal_from_height(height, strength=6.0)

def make_floor(ao, n=2048, seed=31, tiles=4, gap_m=0.003, tile_m=0.6):
    """600mm 米白抛光瓷砖（4×4 块/张）：反照率 sRGB + 粗糙度。ao 为 Blender 烘焙的 AO（行0=顶，同尺寸）。"""
    rng = np.random.default_rng(seed)
    y, x = (np.mgrid[0:n, 0:n] + 0.5) / n
    tx = np.floor(x * tiles).astype(int) % tiles
    ty = np.floor(y * tiles).astype(int) % tiles
    fx = (x * tiles) % 1.0; fy = (y * tiles) % 1.0
    half_gap = gap_m / tile_m / 2.0
    grout = np.minimum(np.minimum(fx, 1 - fx), np.minimum(fy, 1 - fy)) < half_gap
    tone = rng.normal(0, 0.025, (tiles, tiles))[ty, tx]          # 每块砖 ±2.5% 色差
    mott = periodic_noise(n, 2.6, seed + 1, fmin=2, fmax=60) - 0.5
    speck = periodic_noise(n, 0.3, seed + 2, fmin=300) - 0.5
    base = np.array([0.80, 0.78, 0.74])
    lum = 1 + tone + mott * 0.05 + speck * 0.03
    alb = base[None, None, :] * lum[..., None]
    alb = np.where(grout[..., None], np.array([0.55, 0.53, 0.50]), alb)
    alb = alb * (0.65 + 0.35 * np.asarray(ao))[..., None]
    wear = periodic_noise(n, 2.0, seed + 3, fmin=1, fmax=12)
    rough = np.where(grout, 0.88, 0.28 + 0.14 * wear ** 2 + (speck + 0.5) * 0.03)
    return np.clip(alb, 0, 1), np.clip(rough, 0, 1)

def grade_to_mean(img_srgb, target_srgb):
    """逐通道在线性空间缩放，使平均色等于目标（保留木纹明暗对比）。"""
    lin = srgb_to_linear(img_srgb)
    tgt = srgb_to_linear(np.asarray(target_srgb, np.float64))
    lin = lin * (tgt / np.maximum(lin.mean(axis=(0, 1)), 1e-6))[None, None, :]
    return linear_to_srgb(lin)
```

Run: `python3 -m unittest bake/tests/test_tex_lib.py -v`
Expected: 7 个测试 PASS

- [ ] **Step 3: 下载两套木纹（已获用户同意：ash_veneer + plywood，2K，约 18MB）**

`bake/fetch_polyhaven.py`：

```python
#!/usr/bin/env python3
"""下载课桌/椅子用的两套 Poly Haven 实拍木纹（CC0，dl.polyhaven.org）。已存在则跳过。
用 curl 而不是 urllib：python.org 版 Python 在 macOS 上常缺根证书。"""
import json, subprocess
from pathlib import Path

DIR = Path(__file__).resolve().parent / 'assets' / 'polyhaven'
ASSETS = ['ash_veneer', 'plywood']
MAPS = {'Diffuse': 'diff', 'nor_gl': 'nor_gl', 'Rough': 'rough'}

def curl_json(url):
    return json.loads(subprocess.run(['curl', '-fsSL', url], check=True, capture_output=True).stdout)

def main():
    DIR.mkdir(parents=True, exist_ok=True)
    for a in ASSETS:
        files = curl_json(f'https://api.polyhaven.com/files/{a}')
        for key, short in MAPS.items():
            dst = DIR / f'{a}_{short}_2k.jpg'
            if dst.exists() and dst.stat().st_size > 0:
                continue
            url = files[key]['2k']['jpg']['url']
            print('下载', url)
            subprocess.run(['curl', '-fsSL', url, '-o', str(dst)], check=True)
    for p in sorted(DIR.glob('*.jpg')):
        print(f'{p.name:28s} {p.stat().st_size // 1024:6d} KB')

if __name__ == '__main__':
    main()
```

Run: `python3 bake/fetch_polyhaven.py`
Expected: 6 个 jpg（ash_veneer_diff/nor_gl/rough、plywood_diff/nor_gl/rough），合计约 18MB。

- [ ] **Step 4: Blender 公用（Cycles 部分）+ 倒角瓷砖烘焙**

`bake/blender_common.py`（本任务先写这些，Task 4 在文件末尾追加）：

```python
"""Blender 侧公用：Cycles/GPU 设置、世界、导入、坐标换算。只在 Blender 里 import。"""
import math, time
import bpy
import numpy as np
from mathutils import Vector

def three_to_bl(p):
    """three (x,y,z) → blender (x,-z,y)"""
    p = np.asarray(p, np.float64)
    return np.stack([p[..., 0], -p[..., 2], p[..., 1]], -1)

def setup_cycles(samples):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'METAL'
    prefs.get_devices()
    for d in prefs.devices:
        d.use = (d.type != 'CPU')
    sc.cycles.device = 'GPU'
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.cycles.max_bounces = 8
    sc.cycles.diffuse_bounces = 6
    sc.cycles.glossy_bounces = 2
    sc.cycles.transmission_bounces = 2
    sc.cycles.transparent_max_bounces = 4
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.sample_clamp_indirect = 10.0
    return sc

def world_bg():
    sc = bpy.context.scene
    if sc.world is None:
        sc.world = bpy.data.worlds.new('World')
    w = sc.world
    try:
        w.use_nodes = True          # 5.x 已弃用但仍可用；6.0 移除后此句无害跳过
    except Exception:
        pass
    nt = w.node_tree
    bg = nt.nodes.get('Background')
    if bg is None:
        bg = nt.nodes.new('ShaderNodeBackground')
        out = nt.nodes.get('World Output') or nt.nodes.new('ShaderNodeOutputWorld')
        nt.links.new(bg.outputs[0], out.inputs[0])
    return bg

def set_world(rgb, strength=1.0):
    bg = world_bg()
    bg.inputs['Color'].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
    bg.inputs['Strength'].default_value = strength

def new_material(name):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    return m
```

`bake/blender_floor.py`：

```python
"""地砖：在 Blender 里用真实倒角几何建 4×4 块 600mm 瓷砖（3mm 缝、1.5mm 倒角、±0.3mm 高差），
Cycles 烘焙到平面得到切线空间法线 + AO。网格居中排布 → 贴图四方连续。
用法：blender -b --factory-startup -P bake/blender_floor.py -- [--res 2048]"""
import sys, random, argparse
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import bpy
import blender_common as B

def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser(); ap.add_argument('--res', type=int, default=2048)
    a = ap.parse_args(argv)
    out = HERE / 'out' / 'tex_raw'; out.mkdir(parents=True, exist_ok=True)
    N, T, GAP, BEV, TH = 4, 0.6, 0.003, 0.0015, 0.010
    S = N * T
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = B.setup_cycles(64)
    B.set_world((1, 1, 1), 1.0)
    sc.world.light_settings.distance = 0.01            # AO 只看 1cm 内（缝/倒角尺度）
    rng = random.Random(7)
    high = []
    for i in range(N):
        for j in range(N):
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-S / 2 + T / 2 + i * T, -S / 2 + T / 2 + j * T,
                                                                -TH / 2 + rng.uniform(-0.0003, 0.0003)))
            ob = bpy.context.active_object
            ob.scale = (T - GAP, T - GAP, TH)
            ob.rotation_euler = (rng.uniform(-4e-4, 4e-4), rng.uniform(-4e-4, 4e-4), 0.0)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
            mod = ob.modifiers.new('bev', 'BEVEL'); mod.width = BEV; mod.segments = 3
            high.append(ob)
    bpy.ops.mesh.primitive_plane_add(size=S + 0.2, location=(0, 0, -0.0015))    # 缝底（勾缝剂面）
    high.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_plane_add(size=S, location=(0, 0, 0.002))            # 烘焙目标：UV 0..1 ↔ [-S/2, S/2]
    low = bpy.context.active_object
    mat = B.new_material('bake')
    tex = mat.node_tree.nodes.new('ShaderNodeTexImage'); mat.node_tree.nodes.active = tex
    low.data.materials.append(mat)

    def bake(kind, **kw):
        img = bpy.data.images.new(kind, a.res, a.res, float_buffer=True)
        img.colorspace_settings.name = 'Non-Color'
        tex.image = img
        bpy.ops.object.select_all(action='DESELECT')
        for o in high:
            o.select_set(True)
        low.select_set(True); bpy.context.view_layer.objects.active = low
        bpy.ops.object.bake(type=kind, use_selected_to_active=True, cage_extrusion=0.01,
                            max_ray_distance=0.02, margin=0, use_clear=True, **kw)
        px = np.array(img.pixels[:], np.float32).reshape(a.res, a.res, 4)
        return np.flipud(px)       # Blender 像素行0=底部 → 统一成行0=顶部（与图片文件一致）

    nrm = bake('NORMAL', normal_space='TANGENT')[..., :3]
    ao = bake('AO')[..., 0]
    np.save(out / 'floor_normal.npy', nrm.astype(np.float32))
    np.save(out / 'floor_ao.npy', ao.astype(np.float32))
    print('FLOOR normal mean', nrm.reshape(-1, 3).mean(0).round(3), 'ao min/mean', float(ao.min()), float(ao.mean()))

main()
```

Run: `/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P bake/blender_floor.py 2>&1 | grep FLOOR`
Expected: `FLOOR normal mean [~0.5 ~0.5 ~1.0] ao min/mean …`（法线均值 z≈1、AO 最小值 < 0.8：缝里有遮蔽）

- [ ] **Step 5: 打包贴图（WebP + tex.json）**

`bake/pack_textures.py`：

```python
#!/usr/bin/env python3
"""生成运行时贴图：地砖（Blender 法线/AO + numpy 反照率/粗糙度）、墙漆、吸音板、两套木纹 → bake/out/tex/*.webp + tex.json"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tex_lib as X

OUT = HERE / 'out' / 'tex'; RAW = HERE / 'out' / 'tex_raw'; PH = HERE / 'assets' / 'polyhaven'
# 旧地砖的平均线性反照率（0xaaa69b × 旧 floorTex 均值），新地砖用 tint 对齐它，避免强阳光下"死白"回潮
OLD_FLOOR_ALBEDO = np.array([0.204, 0.187, 0.146])
WOOD_TARGET = {'ash': [0.70, 0.54, 0.36], 'plywood': [0.68, 0.52, 0.35]}   # 暖蜂蜜色，降饱和（sRGB 均值）

def u8(a):
    return (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)

def save(arr01, name, q):
    if arr01.ndim == 2:
        arr01 = np.repeat(arr01[..., None], 3, -1)
    Image.fromarray(u8(arr01), 'RGB').save(OUT / name, 'WEBP', quality=q, method=6)
    return name

def load_jpg(path, size):
    im = Image.open(path).convert('RGB').resize((size, size), Image.LANCZOS)
    return np.asarray(im, np.float64) / 255.0

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {}
    # 地砖
    ao = np.load(RAW / 'floor_ao.npy'); nrm = np.load(RAW / 'floor_normal.npy')
    alb, rough = X.make_floor(ao, n=ao.shape[0])
    tint = OLD_FLOOR_ALBEDO / X.srgb_to_linear(alb).mean(axis=(0, 1))
    meta['floor'] = dict(albedo=save(alb, 'floor_albedo.webp', 90), normal=save(nrm, 'floor_normal.webp', 92),
                         rough=save(rough, 'floor_rough.webp', 85), size=2.4, tint=[round(float(t), 4) for t in tint])
    # 墙漆
    wa, wn = X.make_wall(1024)
    meta['wall'] = dict(albedo=save(wa, 'wall_albedo.webp', 90), normal=save(wn, 'wall_normal.webp', 92), size=2.0)
    # 吸音板
    ca, cn = X.make_ceiling_tile(1024)
    meta['ceilTile'] = dict(albedo=save(ca, 'ceil_albedo.webp', 90), normal=save(cn, 'ceil_normal.webp', 92))
    # 木纹（Poly Haven）：调色 + 粗糙度按清漆面重映射
    for kind, src, size in [('ash', 'ash_veneer', 1.0), ('plywood', 'plywood', 0.5)]:
        d = load_jpg(PH / f'{src}_diff_2k.jpg', 1024)
        n = load_jpg(PH / f'{src}_nor_gl_2k.jpg', 1024)
        r = load_jpg(PH / f'{src}_rough_2k.jpg', 1024)[..., 0]
        meta[kind] = dict(albedo=save(X.grade_to_mean(d, WOOD_TARGET[kind]), f'{kind}_albedo.webp', 88),
                          normal=save(n, f'{kind}_normal.webp', 90),
                          rough=save(0.32 + 0.25 * r, f'{kind}_rough.webp', 85), size=size)
    (OUT / 'tex.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    total = sum(p.stat().st_size for p in OUT.glob('*.webp'))
    print(f'TEX {len(list(OUT.glob("*.webp")))} 张 WebP，共 {total / 1e6:.2f} MB；地砖 tint={meta["floor"]["tint"]}')

if __name__ == '__main__':
    main()
```

Run: `python3 bake/pack_textures.py`
Expected: `TEX 13 张 WebP，共 ~2–3 MB；地砖 tint=[…]`

- [ ] **Step 6: 看一眼生成的贴图**

Run: `python3 -c "from PIL import Image; import glob; ims=[Image.open(p).resize((256,256)) for p in sorted(glob.glob('bake/out/tex/*.webp'))]; s=Image.new('RGB',(256*5,256*3)); [s.paste(im,((i%5)*256,(i//5)*256)) for i,im in enumerate(ims)]; s.save('bake/out/tex_sheet.png')"`，然后用 Read 工具查看 `bake/out/tex_sheet.png`。
Expected: 地砖有清晰砖缝与倒角高光、墙漆近乎平、吸音板有分缝/针孔/裂纹、木纹为暖蜂蜜色。若木纹纹理方向与课桌长边不一致（纹理应沿桌面长边 x 方向），记下需在运行时 `rotation = Math.PI/2`。

- [ ] **Step 7: 写失败的 embed 单测**

`bake/tests/test_embed.py`：

```python
import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import embed as E

HTML = '<html><body>\n<script>var a=1;</script>\n</body></html>\n'

class TestEmbed(unittest.TestCase):
    def test_insert_then_replace_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'x.html'; p.write_text(HTML, encoding='utf-8')
            payload = {'version': 1, 'textures': {'meta': {}, 'floor_albedo': 'data:image/webp;base64,AAAA'}, 'gi': None}
            E.embed(p, payload); once = p.read_text(encoding='utf-8')
            E.embed(p, payload); twice = p.read_text(encoding='utf-8')
            self.assertEqual(once, twice)
            self.assertEqual(once.count('<script id="bakedData">'), 1)
            self.assertLess(once.index('bakedData'), once.index('</body>'))
            self.assertIn('var a=1;', once)

    def test_block_is_script_safe_json(self):
        block = E.render_block({'version': 1, 'textures': None, 'gi': {'meta': {'s': 'a</b'}, 'atlas': 'x'}})
        body = block[len(E.BEGIN):-len(E.END)]
        self.assertNotIn('</', body)
        js = body.split('window.BAKED = ', 1)[1].rsplit(';', 1)[0]
        self.assertEqual(json.loads(js)['gi']['meta']['s'], 'a</b')

if __name__ == '__main__':
    unittest.main()
```

Run: `python3 -m unittest bake/tests/test_embed.py -v`
Expected: ERROR（`No module named 'embed'`）

- [ ] **Step 8: 实现 embed.py**

`bake/embed.py`：

```python
#!/usr/bin/env python3
"""把 bake/out 里的贴图与 GI 数据整块写进 HTML 末尾的 <script id="bakedData">。可重复执行，结果一致。"""
import base64, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / 'out'
BEGIN = '<script id="bakedData">'
END = '</script>'
MIME = {'.webp': 'image/webp', '.png': 'image/png'}

def data_uri(p):
    return f'data:{MIME[p.suffix]};base64,' + base64.b64encode(p.read_bytes()).decode()

def build_payload(out=OUT):
    payload = {'version': 1, 'textures': None, 'gi': None}
    tj = out / 'tex' / 'tex.json'
    if tj.exists():
        meta = json.loads(tj.read_text())
        tex = {'meta': meta}
        for kind, d in meta.items():
            for slot in ('albedo', 'normal', 'rough'):
                if slot in d:
                    tex[f'{kind}_{slot}'] = data_uri(out / 'tex' / d[slot])
        payload['textures'] = tex
    gj = out / 'gi.json'
    if gj.exists():
        payload['gi'] = {'meta': json.loads(gj.read_text()), 'atlas': data_uri(out / 'gi_atlas.png')}
    return payload

def render_block(payload):
    js = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    return (BEGIN + '\n// 由 bake/embed.py 生成，勿手改。重新生成：bake/run_all.sh\nwindow.BAKED = '
            + js + ';\n' + END)

def embed(html_path, payload):
    html_path = Path(html_path)
    s = html_path.read_text(encoding='utf-8')
    block = render_block(payload)
    i = s.find(BEGIN)
    if i >= 0:
        j = s.find(END, i)
        s = s[:i] + block + s[j + len(END):]
    else:
        k = s.rfind('</body>')
        s = s[:k] + block + '\n' + s[k:]
    tmp = html_path.with_suffix('.tmp')
    tmp.write_text(s, encoding='utf-8')
    tmp.replace(html_path)
    return len(block)

if __name__ == '__main__':
    html = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'classroom_v4_3.html'
    n = embed(html, build_payload())
    print(f'bakedData 写入 {html.name}：{n / 1e6:.2f} MB')
```

Run: `python3 -m unittest bake/tests/test_embed.py -v`
Expected: 2 个测试 PASS

- [ ] **Step 9: 写失败的运行时贴图集成测试**

`bake/tests/helpers.mjs`：

```js
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
```

`bake/tests/runtime_textures.test.mjs`：

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { launch, fileUrl } from '../cdp.mjs';
import { HTML, noDataCopy, errorsIn } from './helpers.mjs';

test('烘焙贴图接入', async () => {
  const b = await launch();
  try {
    await b.goto(fileUrl(HTML));
    await b.waitFor("window.__GI && __GI.texStatus !== 'pending'");
    assert.equal(await b.evaluate('__GI.texStatus'), 'active');
    assert.equal(await b.evaluate('floor.material.map.image.width'), 2048);
    assert.ok(await b.evaluate('deskMat.normalMap !== null && deskMat.roughnessMap !== null'));
    assert.ok(await b.evaluate('chairWoodMat.map.source !== deskTex.source'));
    assert.equal(await b.evaluate(`(() => { let n = 0; scene.traverse(o => { if (o.isInstancedMesh && o.material.userData.giTex === 'ceilTile' && o.material.map) n++; }); return n; })()`), 1);
    // 地砖按世界坐标对齐：主地板与补地板的贴图偏移使砖缝在 z 方向连续
    assert.ok(await b.evaluate('Math.abs(floor.material.map.repeat.x - 14 / 2.4) < 1e-6'));
    assert.deepEqual(errorsIn(b.logs), []);
  } finally { await b.close(); }
});

test('缺数据块时沿用程序化贴图', async () => {
  const b = await launch();
  try {
    await b.goto(fileUrl(noDataCopy()));
    await b.waitFor("window.__GI && __GI.texStatus !== 'pending'");
    assert.equal(await b.evaluate('__GI.texStatus'), 'absent');
    assert.ok(await b.evaluate('floor.material.map === floorTex'));
    assert.deepEqual(errorsIn(b.logs), []);
  } finally { await b.close(); }
});
```

Run: `node --test bake/tests/runtime_textures.test.mjs`
Expected: FAIL（`window.__GI` 不存在 → 等待超时）

- [ ] **Step 10: HTML 小钩子**

1) 吊顶板打标签。在 `classroom_v4_3.html` 中找到：

```js
  const tileMesh = new THREE.InstancedMesh(new THREE.PlaneGeometry(gw, gd), mat(0xffffff, 0.92), nTiles);
```

在其下一行插入：

```js
  tileMesh.material.userData.giTex = 'ceilTile';   // 烘焙贴图接入按此标签换上矿棉吸音板贴图（见"烘焙数据接入"段）
```

2) `- / =` 地面反照率热键改读活基准。找到：

```js
      floor.material.color.copy(floorBase).multiplyScalar(FLOOR_ALBEDO_MUL);
```

替换为：

```js
      // 换上烘焙贴图后地砖底色是 tint（见"烘焙数据接入"段），基准要读活值而不是开场快照
      floor.material.color.copy(floor.userData.albedoBase || floorBase).multiplyScalar(FLOOR_ALBEDO_MUL);
```

- [ ] **Step 11: 新增"烘焙数据接入"脚本段（贴图部分）**

在主脚本结束标签 `</script>` 与 `<!-- ══ 开场封面逻辑 · Title-screen logic ══ -->` 之间插入新脚本段：

```html
<script>
// ══ 烘焙数据接入：Blender / Cycles 离线生成的贴图与全局光照（GI） ═══════════════════════
// 数据在文件末尾 <script id="bakedData">（bake/embed.py 生成，重新生成见 bake/run_all.sh）。
// 加载完成(load)后异步解码；缺数据或解码失败 → 一切照旧（沿用程序化贴图、原补光灯）。
// 开场封面此时正盖在画面上，换贴图/重编着色器的那一下用户看不到。
(() => {
  const GI = window.__GI = { status: 'pending', texStatus: 'pending', active: false };

  function loadImage(uri) {
    return new Promise((res, rej) => {
      const im = new Image();
      im.onload = () => res(im);
      im.onerror = () => rej(new Error('图片解码失败'));
      im.src = uri;
    });
  }
  async function loadTex(uri, srgb) {
    const t = new THREE.Texture(await loadImage(uri));
    t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.anisotropy = renderer.capabilities.getMaxAnisotropy();
    t.needsUpdate = true;
    return t;
  }
  // 材质 → 贴图种类：按原贴图的来源识别，建模代码不用改
  function texKind(m) {
    if (m === chairWoodMat) return 'plywood';
    if (m === deskMat || m === douMat) return 'ash';
    const src = m.map && m.map.source;
    if (src && src === floorTex.source) return 'floor';
    if (src && src === wallTex.source) return 'wall';
    return (m.userData && m.userData.giTex) || null;
  }
  const rep = (base, rx, ry, ox = 0, oy = 0) => {
    const t = base.clone(); t.repeat.set(rx, ry); t.offset.set(ox, oy); t.needsUpdate = true; return t;
  };
  const _box = new THREE.Box3(), _size = new THREE.Vector3();

  async function applyTextures(B) {
    const meta = B.meta, set = {};
    for (const kind of Object.keys(meta)) {
      set[kind] = {};
      for (const slot of ['albedo', 'normal', 'rough']) {
        const uri = B[`${kind}_${slot}`];
        if (uri) set[kind][slot] = await loadTex(uri, slot === 'albedo');
      }
    }
    const done = new Set();
    scene.updateMatrixWorld(true);
    scene.traverse(o => {
      if (!o.isMesh) return;
      for (const m of (Array.isArray(o.material) ? o.material : [o.material])) {
        if (!m || !m.isMeshStandardMaterial || done.has(m)) continue;
        const kind = texKind(m);
        if (!kind || !set[kind]) continue;
        done.add(m);
        const S = set[kind], M = meta[kind];
        if (kind === 'floor') {
          // 世界坐标对齐：uv' = (x, -z) / 砖块贴图边长 → 主地板、补地板、讲台地台的砖缝严丝合缝
          _box.setFromObject(o); _box.getSize(_size);
          const a = [_size.x / M.size, _size.z / M.size, _box.min.x / M.size, -_box.max.z / M.size];
          m.map = rep(S.albedo, ...a); m.normalMap = rep(S.normal, ...a); m.roughnessMap = rep(S.rough, ...a);
          m.color.setRGB(M.tint[0], M.tint[1], M.tint[2]);           // 线性 tint：平均反照率与旧地砖一致
          if (o === floor) floor.userData.albedoBase = m.color.clone();
          m.roughness = 1.0; m.metalness = 0.0; m.normalScale.set(1, 1);
        } else if (kind === 'wall') {
          // PlaneGeometry（前后墙/墙裙/天花底板）UV 0..1 对应 width×height；左右墙 ShapeGeometry 的 UV 已按 RD×RH 归一化
          const P = o.geometry.parameters || {};
          let rx, ry;
          if (P.width !== undefined && P.height !== undefined) { rx = P.width / M.size; ry = P.height / M.size; }
          else { rx = RD / M.size; ry = RH / M.size; }
          m.map = rep(S.albedo, rx, ry); m.normalMap = rep(S.normal, rx, ry); m.normalScale.set(0.6, 0.6);
          // 墙色保留原值：贴图只是 ±2% 的中性明暗
        } else if (kind === 'ceilTile') {
          m.map = S.albedo; m.normalMap = S.normal; m.normalScale.set(1, 1);
        } else if (kind === 'ash') {
          if (m === deskMat) {
            const rx = deskW / M.size, ry = deskD / M.size;           // 桌面 1.1×0.65m，贴图对应 1m×1m 实物
            m.map = rep(S.albedo, rx, ry); m.normalMap = rep(S.normal, rx, ry); m.roughnessMap = rep(S.rough, rx, ry);
            m.color.set(0xffffff); m.roughness = 1.0;
          } else {                                                     // 桌斗：同木纹、暗一档、不加法线（在暗处看不见）
            m.map = rep(S.albedo, 0.6 / M.size, 0.6 / M.size); m.color.setRGB(0.35, 0.30, 0.26);
          }
        } else if (kind === 'plywood') {
          const rx = 0.52 / M.size, ry = 0.44 / M.size;               // 椅面 seatGeo = roundedBox(0.52, 0.03, 0.44)
          m.map = rep(S.albedo, rx, ry); m.normalMap = rep(S.normal, rx, ry); m.roughnessMap = rep(S.rough, rx, ry);
          m.color.set(0xffffff); m.roughness = 1.0;
        }
        m.needsUpdate = true;
      }
    });
    GI.texturedMaterials = done.size;
  }

  async function boot() {
    const B = window.BAKED;
    if (!B || !B.textures) GI.texStatus = 'absent';
    else {
      try { await applyTextures(B.textures); GI.texStatus = 'active'; }
      catch (e) { console.warn('[baked] 贴图加载失败，沿用程序化贴图：', e); GI.texStatus = 'error'; }
    }
    if (!B || !B.gi) GI.status = 'absent';
  }
  window.addEventListener('load', () => { boot(); });
})();
</script>
```

- [ ] **Step 12: 写入数据块，测试转绿**

Run: `python3 bake/embed.py && node --test bake/tests/runtime_textures.test.mjs`
Expected: `bakedData 写入 classroom_v4_3.html：~3 MB`，2 个测试 PASS。

- [ ] **Step 13: 截图对比（只换材质）**

```bash
mkdir -p bake/out/shots
git show main:classroom_v4_3.html > bake/out/before.html
node -e "
import('./bake/cdp.mjs').then(async ({launch, fileUrl}) => {
  for (const [tag, p] of [['before','bake/out/before.html'],['tex','classroom_v4_3.html']]) {
    const b = await launch();
    await b.goto(fileUrl(process.cwd() + '/' + p));
    await b.waitFor(\"!window.__GI || __GI.texStatus !== 'pending'\");
    await b.evaluate(\"applyPreset('morning'); applyView(CAM_VIEWS['5']); true\");
    await new Promise(r => setTimeout(r, 3000));
    await b.canvasPNG('bake/out/shots/' + tag + '_morning_5.png');
    await b.close();
  }
});"
```

用 Read 工具查看 `bake/out/shots/before_morning_5.png` 与 `bake/out/shots/tex_morning_5.png`。
Expected: 课桌木纹自然、不再是橙色条纹；地砖为正方形且有砖缝；整体亮度与改前接近（地砖 tint 起作用）。

- [ ] **Step 14: 更新 spec 的 D8 表**

把 spec 中 D8 表的"墙面 / 吊顶板"两行的"来源"改为 `numpy 程序化（FFT 四方连续噪声）`，"地砖"行说明改为 `Blender 倒角几何烘焙法线/AO + numpy 反照率/粗糙度`。

- [ ] **Step 15: Commit**

```bash
git add bake/fetch_polyhaven.py bake/blender_common.py bake/blender_floor.py bake/tex_lib.py bake/pack_textures.py bake/embed.py bake/tests/test_tex_lib.py bake/tests/test_embed.py bake/tests/helpers.mjs bake/tests/runtime_textures.test.mjs classroom_v4_3.html docs/superpowers/specs/2026-10-11-cycles-baked-gi-materials-design.md
git commit -m "feat: 材质升级——Poly Haven 实拍木纹 + Blender 倒角瓷砖 + 程序化墙漆/吸音板，运行时接入

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 探针数据库 gi_lib（纯 numpy）

**Files:**
- Create: `bake/gi_lib.py`, `bake/tests/test_gi_lib.py`

**Interfaces:**
- Produces: 常量 `LAYERS`（10 层）、`FACES`、`GROUPS`（13 组，顺序 `SKY, CEIL, CORR_D, CORR_I, SUN_0..SUN_8`）、`SUN_ANGLES`；函数 `volumes() → [dict(name,x0,x1,nx,z0,z1,nz,box)]`、`grid_centers(v) → (N,3)`（索引 `(iz*ny+iy)*nx+ix`）、`all_centers(vols)`、`probe_offsets(vols) → (offs, total)`、`layer_coord(y)`、`atlas_layout(vols, n_groups, cols=4, max_w=504) → {W,H,cols,rows,regions:[{x0,y0,tpr,tw,th,rows}]}`、`tile_origin(region, face, iz, nz)`、`pack_atlas(E, vols, layout) → (H,W,3)`、`unpack_probe(A, vols, layout, vi, ix, iy, iz, face)`、`encode_log(x, scale) → uint8`、`decode_log(u8, scale)`、`robust_scale(A)`、`fill_invalid(E_grid, valid) → (E, ok)`、`fill_invalid_all(E, valid, vols)`、`ambient_cube(c6, n)`、`tile_groups(cells, layout)`、`runtime_meta(layout, vols, groups, scales, sun_dirs, extra)`。

- [ ] **Step 1: 写失败的单测**

`bake/tests/test_gi_lib.py`：

```python
import sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi_lib as G

class TestGrid(unittest.TestCase):
    def test_index_order_x_fastest(self):
        v = G.volumes()[0]; c = G.grid_centers(v); ny = len(G.LAYERS)
        self.assertEqual(len(c), v['nx'] * ny * v['nz'])
        dx = c[1] - c[0]
        self.assertGreater(dx[0], 0); self.assertAlmostEqual(dx[1], 0); self.assertAlmostEqual(dx[2], 0)
        self.assertAlmostEqual(c[v['nx']][1], G.LAYERS[1])                 # 下一行 = 下一层
        self.assertGreater(c[v['nx'] * ny][2], c[0][2])                    # 下一片 = z 增加

    def test_volumes_inside_walls(self):
        for v in G.volumes():
            (bx0, by0, bz0), (bx1, by1, bz1) = v['box']
            self.assertTrue(bx0 < v['x0'] < v['x1'] < bx1)
            self.assertTrue(bz0 < v['z0'] < v['z1'] < bz1)
            self.assertTrue(by0 < G.LAYERS[0] and G.LAYERS[-1] < by1)

    def test_layer_coord(self):
        self.assertEqual(G.layer_coord(-1.0), 0.0)
        self.assertEqual(G.layer_coord(G.LAYERS[3]), 3.0)
        mid = (G.LAYERS[3] + G.LAYERS[4]) / 2
        self.assertAlmostEqual(G.layer_coord(mid), 3.5)
        self.assertEqual(G.layer_coord(9.0), float(len(G.LAYERS) - 1))

class TestAtlas(unittest.TestCase):
    def test_layout_no_overlap_and_fits(self):
        vols = G.volumes(); L = G.atlas_layout(vols)
        self.assertLessEqual(L['W'], 504)
        self.assertLessEqual(L['W'] * L['cols'], 2048); self.assertLessEqual(L['H'] * L['rows'], 2048)
        used = np.zeros((L['H'], L['W']), np.int32)
        for v, reg in zip(vols, L['regions']):
            for f in range(6):
                for iz in range(v['nz']):
                    x, y = G.tile_origin(reg, f, iz, v['nz'])
                    used[y:y + reg['th'], x:x + reg['tw']] += 1
        self.assertEqual(int(used.max()), 1)

    def test_pack_unpack_roundtrip(self):
        vols = G.volumes(); L = G.atlas_layout(vols); _, n = G.probe_offsets(vols)
        E = np.random.default_rng(0).random((n, 6, 3)).astype(np.float32)
        A = G.pack_atlas(E, vols, L); offs, _ = G.probe_offsets(vols); ny = len(G.LAYERS)
        for vi, (ix, iy, iz, f) in [(0, (0, 0, 0, 0)), (0, (35, 9, 52, 5)), (1, (4, 3, 64, 2)), (1, (0, 9, 0, 3))]:
            v = vols[vi]; idx = offs[vi] + (iz * ny + iy) * v['nx'] + ix
            self.assertTrue(np.allclose(G.unpack_probe(A, vols, L, vi, ix, iy, iz, f), E[idx, f]))

class TestCodec(unittest.TestCase):
    def test_log_roundtrip_relative_error(self):
        s = 7.0; x = s * np.logspace(-2, 0, 200)
        y = G.decode_log(G.encode_log(x, s), s)
        self.assertLess(float(np.max(np.abs(y - x) / x)), 0.03)
        self.assertEqual(int(G.encode_log(np.array([0.0]), s)[0]), 0)
        self.assertEqual(int(G.encode_log(np.array([2 * s]), s)[0]), 255)   # 超范围截断
        self.assertAlmostEqual(float(G.decode_log(np.array([255]), s)[0]), s)

class TestFill(unittest.TestCase):
    def test_fill_invalid_from_neighbours(self):
        E = np.full((6, 5, 7, 6, 3), 5.0); valid = np.ones((6, 5, 7), bool)
        valid[2:4, 1:3, 2:5] = False; E[~valid] = 999.0
        out, ok = G.fill_invalid(E, valid)
        self.assertTrue(ok.all()); self.assertTrue(np.allclose(out, 5.0))

    def test_no_valid_neighbours_becomes_zero(self):
        E = np.full((2, 2, 2, 6, 3), 3.0); valid = np.zeros((2, 2, 2), bool)
        out, ok = G.fill_invalid(E, valid)
        self.assertFalse(ok.any()); self.assertTrue(np.all(out == 0))

class TestAmbientCube(unittest.TestCase):
    def test_axis_and_diagonal(self):
        c6 = np.array([[1, 0, 0], [2, 0, 0], [3, 0, 0], [4, 0, 0], [5, 0, 0], [6, 0, 0]], float)
        self.assertEqual(G.ambient_cube(c6, [0, -1, 0])[0], 4)
        n = np.array([1, 1, 0]) / np.sqrt(2)
        self.assertAlmostEqual(G.ambient_cube(c6, n)[0], 0.5 * 1 + 0.5 * 3)

if __name__ == '__main__':
    unittest.main()
```

Run: `python3 -m unittest bake/tests/test_gi_lib.py -v`
Expected: ERROR（`No module named 'gi_lib'`）

- [ ] **Step 2: 实现 gi_lib**

`bake/gi_lib.py`：

```python
"""探针体积（irradiance volume）的纯数据工具：网格、图集布局、对数编码、坏探针修补。
Blender 内（烘焙）与系统 Python（打包/单测）共用。坐标一律是 three.js 世界坐标（y 向上）。"""
import math
import numpy as np

LAYERS = [0.07, 0.28, 0.51, 0.81, 1.18, 1.55, 2.00, 2.50, 3.00, 3.36]   # 非均匀层高：紧贴地面/椅面/桌面/讲台面上方
FACES = ['+X', '-X', '+Y', '-Y', '+Z', '-Z']
SUN_ANGLES = list(range(-80, 81, 20))
GROUPS = ['SKY', 'CEIL', 'CORR_D', 'CORR_I'] + [f'SUN_{k}' for k in range(len(SUN_ANGLES))]
GROUP_COLS = 4
MAX_REGION_W = 504
LOG_K = 255.0

def volumes():
    return [
        dict(name='classroom', x0=-6.85, x1=6.85, nx=36, z0=-4.85, z1=15.85, nz=53,
             box=[[-7.0, 0.0, -5.0], [7.0, 3.5, 16.0]]),
        dict(name='corridor', x0=7.15, x1=8.75, nx=5, z0=-4.35, z1=21.35, nz=65,
             box=[[7.0, 0.0, -4.5], [8.9, 3.5, 21.5]]),
    ]

def grid_centers(v):
    """(nz*ny*nx, 3)，索引 = (iz*ny + iy)*nx + ix（x 最快）。"""
    xs = np.linspace(v['x0'], v['x1'], v['nx'])
    zs = np.linspace(v['z0'], v['z1'], v['nz'])
    ys = np.asarray(LAYERS, np.float64)
    Z, Y, X = np.meshgrid(zs, ys, xs, indexing='ij')
    return np.stack([X, Y, Z], axis=-1).reshape(-1, 3)

def all_centers(vols):
    return np.concatenate([grid_centers(v) for v in vols], axis=0)

def probe_offsets(vols):
    offs, n = [], 0
    for v in vols:
        offs.append(n)
        n += v['nx'] * len(LAYERS) * v['nz']
    return offs, n

def layer_coord(y, layers=LAYERS):
    """世界 y → 连续层号（与着色器 giLayerCoord、运行时 giLayerCoord 一致）。"""
    if y <= layers[0]:
        return 0.0
    for i in range(len(layers) - 1):
        if y < layers[i + 1]:
            return i + (y - layers[i]) / (layers[i + 1] - layers[i])
    return float(len(layers) - 1)

def atlas_layout(vols, n_groups=len(GROUPS), cols=GROUP_COLS, max_w=MAX_REGION_W):
    """每个体积占图集里的一段区域；区域内按"面 f、z 片 iz"排成 (nx × 层数) 的小格。"""
    ny = len(LAYERS)
    regions, y, W = [], 0, 0
    for v in vols:
        tiles = 6 * v['nz']
        tpr = max(1, min(tiles, max_w // v['nx']))
        rows = math.ceil(tiles / tpr)
        regions.append(dict(x0=0, y0=y, tpr=tpr, tw=v['nx'], th=ny, rows=rows))
        y += rows * ny
        W = max(W, tpr * v['nx'])
    return dict(W=W, H=y, cols=cols, rows=math.ceil(n_groups / cols), regions=regions)

def tile_origin(region, face, iz, nz):
    t = face * nz + iz
    return region['x0'] + (t % region['tpr']) * region['tw'], region['y0'] + (t // region['tpr']) * region['th']

def pack_atlas(E, vols, layout):
    """E: (N,6,3) 全体探针的六面辐照度 → (H, W, 3) 单组图集（行 = 层，列 = x）。"""
    A = np.zeros((layout['H'], layout['W'], 3), np.float32)
    offs, _ = probe_offsets(vols)
    ny = len(LAYERS)
    for v, off, reg in zip(vols, offs, layout['regions']):
        nx, nz = v['nx'], v['nz']
        Ev = E[off: off + nx * ny * nz].reshape(nz, ny, nx, 6, 3)
        for f in range(6):
            for iz in range(nz):
                x, y = tile_origin(reg, f, iz, nz)
                A[y:y + ny, x:x + nx] = Ev[iz, :, :, f, :]
    return A

def unpack_probe(A, vols, layout, vi, ix, iy, iz, face):
    x, y = tile_origin(layout['regions'][vi], face, iz, vols[vi]['nz'])
    return A[y + iy, x + ix]

def encode_log(x, scale):
    r = np.clip(np.asarray(x, np.float64) / scale, 0.0, 1.0)
    return np.round(np.log2(1.0 + LOG_K * r) / math.log2(1.0 + LOG_K) * 255.0).astype(np.uint8)

def decode_log(u8, scale):
    """与着色器 scale * (exp2(8*e) - 1) / 255 完全一致（K=255 → log2(1+K)=8）。"""
    e = np.asarray(u8, np.float64) / 255.0
    return scale * (np.power(1.0 + LOG_K, e) - 1.0) / LOG_K

def robust_scale(A, q=99.98):
    v = float(np.percentile(A, q)) if A.size else 0.0
    return max(v * 1.02, 1e-6)

def fill_invalid(E_grid, valid, max_iter=200):
    """E_grid: (nz,ny,nx,6,3)；valid: (nz,ny,nx)。无效探针用有效六邻居均值逐轮向内填补；孤立无援的置 0。"""
    E = np.array(E_grid, np.float64, copy=True)
    ok = np.array(valid, bool, copy=True)
    for _ in range(max_iter):
        if ok.all():
            break
        acc = np.zeros_like(E)
        cnt = np.zeros(ok.shape, np.float64)
        for axis in range(3):
            for s in (1, -1):
                sh_ok = np.roll(ok, s, axis=axis)
                sh_E = np.roll(E, s, axis=axis)
                edge = [slice(None)] * 3
                edge[axis] = slice(0, 1) if s == 1 else slice(-1, None)
                sh_ok[tuple(edge)] = False                 # 不回绕到对边
                acc += sh_E * sh_ok[..., None, None]
                cnt += sh_ok
        newly = (~ok) & (cnt > 0)
        if not newly.any():
            break
        E[newly] = acc[newly] / cnt[newly][..., None, None]
        ok |= newly
    E[~ok] = 0.0
    return E, ok

def fill_invalid_all(E, valid, vols):
    offs, _ = probe_offsets(vols)
    ny = len(LAYERS)
    out = np.array(E, np.float64, copy=True)
    for v, off in zip(vols, offs):
        n = v['nx'] * ny * v['nz']
        g, _ = fill_invalid(E[off:off + n].reshape(v['nz'], ny, v['nx'], 6, 3),
                            valid[off:off + n].reshape(v['nz'], ny, v['nx']))
        out[off:off + n] = g.reshape(n, 6, 3)
    return out

def ambient_cube(c6, n):
    n = np.asarray(n, np.float64)
    n2 = n * n
    fx = 0 if n[0] >= 0 else 1
    fy = 2 if n[1] >= 0 else 3
    fz = 4 if n[2] >= 0 else 5
    return n2[0] * np.asarray(c6[fx]) + n2[1] * np.asarray(c6[fy]) + n2[2] * np.asarray(c6[fz])

def tile_groups(cells, layout):
    H, W, C = layout['H'], layout['W'], layout['cols']
    big = np.zeros((layout['rows'] * H, C * W, 3), np.uint8)
    for g, cell in enumerate(cells):
        r, c = divmod(g, C)
        big[r * H:(r + 1) * H, c * W:(c + 1) * W] = cell
    return big

def runtime_meta(layout, vols, groups, scales, sun_dirs, extra=None):
    m = dict(version=1, layers=LAYERS, groups=list(groups), scales=[float(s) for s in scales],
             atlas=dict(W=layout['W'], H=layout['H'], cols=layout['cols'], rows=layout['rows'],
                        regions=layout['regions']),
             volumes=[dict(name=v['name'], x0=v['x0'], x1=v['x1'], nx=v['nx'], z0=v['z0'], z1=v['z1'],
                           nz=v['nz'], box=v['box']) for v in vols],
             sunKeys=[list(map(float, d)) for d in sun_dirs],
             units='E = 辐照度（three.js 物理单位，已乘 π）；对数编码 v = s*(2^(8e)-1)/255')
    if extra:
        m.update(extra)
    return m
```

Run: `python3 -m unittest bake/tests/test_gi_lib.py -v`
Expected: 9 个测试 PASS

- [ ] **Step 3: Commit**

```bash
git add bake/gi_lib.py bake/tests/test_gi_lib.py
git commit -m "feat(bake): 探针体积数据库 gi_lib（网格/图集/对数编码/坏探针修补）+ 单测

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Blender 逐组烘焙探针

**Files:**
- Modify: `bake/blender_common.py`（追加导入/去自发光/地面/灯/探针/坏探针检测/烘焙）
- Create: `bake/blender_gi.py`, `bake/tests/test_gi_raw.py`

**Interfaces:**
- Consumes: `gi_lib.volumes/all_centers/GROUPS`；`bake/out/scene.glb`、`scene_meta.json`（Task 1）。
- Produces: `bake/out/gi_raw/<GROUP>.npy`（float32 `(N,6,3)`，E 已乘 π）、`valid.npy`（bool `(N,)`）、`bake_info.json` = `{groups, samples, quick, n_probes, sunKeys:[[x,y,z]×9]}`。

- [ ] **Step 1: 写失败的原始数据物理合理性测试**

`bake/tests/test_gi_raw.py`：

```python
import json, sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi_lib as G

RAW = Path(__file__).resolve().parents[1] / 'out' / 'gi_raw'

class TestGiRaw(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.info = json.loads((RAW / 'bake_info.json').read_text())
        cls.vols = G.volumes(); cls.C = G.all_centers(cls.vols)
        cls.offs, cls.n = G.probe_offsets(cls.vols)
        cls.valid = np.load(RAW / 'valid.npy')
        cls.room = np.arange(cls.n) < cls.offs[1]

    def load(self, g):
        E = np.load(RAW / f'{g}.npy'); self.assertEqual(E.shape, (self.n, 6, 3))
        self.assertTrue(np.isfinite(E).all()); self.assertGreaterEqual(float(E.min()), 0.0)
        return E

    def test_all_groups_present(self):
        self.assertEqual(self.info['groups'], G.GROUPS)

    def test_sky_enters_through_left_windows(self):
        E = self.load('SKY'); C = self.C; mid = (C[:, 1] > 1.0) & (C[:, 1] < 2.1) & self.room & self.valid
        near = E[mid & (C[:, 0] < -5.0), 1].mean()     # -X 面：朝向窗户
        far = E[mid & (C[:, 0] > 5.0), 1].mean()
        self.assertGreater(near, 3 * far)

    def test_corridor_direct_lives_in_corridor(self):
        E = self.load('CORR_D').sum(axis=(1, 2))
        self.assertGreater(E[~self.room].mean(), 10 * E[self.room].mean())

    def test_ceiling_bounce_positive(self):
        E = self.load('CEIL')
        self.assertGreater(E[self.room & self.valid].mean(), 0.0)

    def test_sun_bounce_brightens_ceiling_near_windows(self):
        E = self.load('SUN_1')                         # -60°：晨光低斜入窗
        C = self.C; top = (C[:, 1] > 3.0) & self.room & self.valid
        near = E[top & (C[:, 0] < -4.0), 3].mean()     # -Y 面：朝下看被晒亮的地面
        far = E[top & (C[:, 0] > 4.0), 3].mean()
        self.assertGreater(near, far)

    def test_podium_interior_probes_invalid(self):
        C = self.C
        inside = self.room & (np.abs(C[:, 0]) < 1.3) & (C[:, 2] > -3.15) & (C[:, 2] < -2.45) & (C[:, 1] > 0.2) & (C[:, 1] < 0.9)
        self.assertTrue(inside.any())
        self.assertFalse(self.valid[inside].any())
        self.assertGreater(self.valid.mean(), 0.85)

if __name__ == '__main__':
    unittest.main()
```

Run: `python3 -m unittest bake/tests/test_gi_raw.py -v`
Expected: ERROR（`bake_info.json` 不存在）

- [ ] **Step 2: blender_common 追加探针与烘焙函数**

在 `bake/blender_common.py` 末尾追加：

```python
def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [o for o in bpy.data.objects if o not in before and o.type == 'MESH']

def kill_emission(objs):
    """所有自发光置 0：灯由点光源/天空代表，避免重复计光（导出时已去掉，这里兜底）。"""
    seen = set()
    for o in objs:
        for slot in o.material_slots:
            m = slot.material
            if not m or m in seen or not m.node_tree:
                continue
            seen.add(m)
            for n in m.node_tree.nodes:
                if n.type == 'BSDF_PRINCIPLED' and 'Emission Strength' in n.inputs:
                    n.inputs['Emission Strength'].default_value = 0.0
                elif n.type == 'EMISSION':
                    n.inputs['Strength'].default_value = 0.0

def add_ground(size=400.0, albedo=0.25, z=-0.02):
    """室外地面：天光/阳光经它反射进窗（真实采光里天花板的亮主要来自这里）。"""
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, z))
    g = bpy.context.active_object
    g.name = 'GI_ground'
    m = new_material('GI_ground')
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (albedo, albedo, albedo, 1)
    b.inputs['Roughness'].default_value = 1.0
    g.data.materials.append(m)
    return g

def clear_lights():
    for o in [o for o in bpy.data.objects if o.type == 'LIGHT']:
        bpy.data.objects.remove(o, do_unlink=True)

def add_point(pos_three, power, radius=0.05, color=(1, 1, 1), name='pt'):
    L = bpy.data.lights.new(name, 'POINT')
    L.energy = power; L.shadow_soft_size = radius; L.color = color
    o = bpy.data.objects.new(name, L)
    o.location = Vector(three_to_bl(pos_three).tolist())
    bpy.context.collection.objects.link(o)
    return o

def add_sun(dir_three, strength=1.0, color=(1, 1, 1), angle_deg=0.53, name='sun'):
    L = bpy.data.lights.new(name, 'SUN')
    L.energy = strength; L.color = color; L.angle = math.radians(angle_deg)
    o = bpy.data.objects.new(name, L)
    d = Vector(three_to_bl(dir_three).tolist()).normalized()
    o.rotation_mode = 'QUATERNION'
    o.rotation_quaternion = d.to_track_quat('-Z', 'Y')     # 太阳沿自身 -Z 照射
    bpy.context.collection.objects.link(o)
    return o

PROBE_VIS_OFF = ('visible_camera', 'visible_diffuse', 'visible_glossy', 'visible_transmission', 'visible_shadow')
FACE_NORMALS_BL = [(1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1), (0, -1, 0), (0, 1, 0)]   # three +X,-X,+Y,-Y,+Z,-Z

def make_probe_mesh(centers_three, size=0.004, name='GI_probes'):
    """每个探针 6 个朝外小方面；第 i 个探针第 k 面 → 图集第 6i+k 个像素（UV 只覆盖该像素中心）。"""
    C = three_to_bl(centers_three)
    n = len(C); nt = 6 * n
    W = int(math.ceil(math.sqrt(nt))); H = int(math.ceil(nt / W))
    h = size / 2.0
    N = np.array(FACE_NORMALS_BL, np.float64)
    A = np.where(np.abs(N[:, 2:3]) < 0.5, np.array([[0.0, 0.0, 1.0]]), np.array([[1.0, 0.0, 0.0]]))
    U = np.cross(N, A); U /= np.linalg.norm(U, axis=1, keepdims=True)
    Wv = np.cross(N, U)                                          # U × Wv = N → 下列角点顺序从外看为逆时针
    corners = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]], np.float64)
    off = corners[None, :, 0, None] * U[:, None, :] + corners[None, :, 1, None] * Wv[:, None, :]   # (6,4,3)
    V = (C[:, None, None, :] + N[None, :, None, :] * h + off[None] * h).reshape(-1, 3)
    faces = np.arange(nt * 4).reshape(nt, 4)
    me = bpy.data.meshes.new(name)
    me.from_pydata(V.tolist(), [], faces.tolist())
    uv = me.uv_layers.new(name='UVMap')
    t = np.arange(nt)
    uc = (t % W + 0.5) / W; vc = (t // W + 0.5) / H
    uvs = np.empty((nt, 4, 2), np.float32)
    uvs[:, :, 0] = uc[:, None] + corners[None, :, 0] * (0.3 / W)
    uvs[:, :, 1] = vc[:, None] + corners[None, :, 1] * (0.3 / H)
    uv.data.foreach_set('uv', uvs.ravel())
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    for a in PROBE_VIS_OFF:
        setattr(ob, a, False)
    ob.visible_volume_scatter = True        # 六项全关会被 Cycles 剔除 → 烘出全 0（可行性实验实测）
    img = bpy.data.images.new(name + '_img', width=W, height=H, float_buffer=True, alpha=True)
    img.colorspace_settings.name = 'Non-Color'
    mat = new_material(name + '_mat')
    b = mat.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (1, 1, 1, 1)
    b.inputs['Roughness'].default_value = 1.0
    for nm in ('Specular IOR Level', 'Specular'):
        if nm in b.inputs:
            b.inputs[nm].default_value = 0.0
    tex = mat.node_tree.nodes.new('ShaderNodeTexImage'); tex.image = img; mat.node_tree.nodes.active = tex
    me.materials.append(mat)
    return ob, img, W, H

def _double_sided(ob, poly_index):
    try:
        m = ob.material_slots[ob.data.polygons[poly_index].material_index].material
        return m is not None and not m.use_backface_culling     # glTF 导入：doubleSided → 不剔除背面
    except Exception:
        return False

DIRS14 = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1),
          (1, 1, 1), (1, 1, -1), (1, -1, 1), (1, -1, -1), (-1, 1, 1), (-1, 1, -1), (-1, -1, 1), (-1, -1, -1)]

def probe_validity(centers_three, max_dist=0.45):
    """探针若在 0.45m 内任一方向打到单面几何的背面 → 它在桌子/讲台/柜机内部 → 无效。必须在建探针网格之前调用。"""
    sc = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    dirs = [Vector(d).normalized() for d in DIRS14]
    C = three_to_bl(centers_three)
    valid = np.ones(len(C), bool)
    for i, c in enumerate(C):
        o = Vector(c.tolist())
        for d in dirs:
            hit, loc, nrm, idx, ob, _ = sc.ray_cast(dg, o, d, distance=max_dist)
            if hit and nrm.dot(d) > 0 and not _double_sided(ob, idx):
                valid[i] = False
                break
    return valid

def bake_irradiance(ob, img, W, H, passes, n_probes):
    """返回 (n_probes, 6, 3) 辐照度 E = π × Cycles 漫反射通道（可行性实验已验证）。"""
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    t0 = time.time()
    bpy.ops.object.bake(type='DIFFUSE', pass_filter=set(passes), margin=0, use_clear=True, target='IMAGE_TEXTURES')
    px = np.array(img.pixels[:], dtype=np.float32).reshape(H * W, 4)[: 6 * n_probes, :3]
    print(f'  烘焙 {sorted(passes)} {time.time() - t0:.1f}s', flush=True)
    return (px * math.pi).reshape(n_probes, 6, 3)
```

- [ ] **Step 3: 烘焙入口**

`bake/blender_gi.py`：

```python
"""Cycles 烘焙探针体积：每个光源分组一份六面辐照度。
用法：blender -b --factory-startup -P bake/blender_gi.py -- [--quick] [--samples 1024] [--groups SKY,CEIL]"""
import sys, json, time, argparse, math
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import bpy
import gi_lib as G
import blender_common as B

def parse():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument('--quick', action='store_true')
    p.add_argument('--samples', type=int, default=1024)
    p.add_argument('--groups', default=','.join(G.GROUPS))
    return p.parse_args(argv)

def main():
    a = parse()
    out = HERE / 'out'; raw = out / 'gi_raw'; raw.mkdir(parents=True, exist_ok=True)
    meta = json.loads((out / 'scene_meta.json').read_text())
    bpy.ops.wm.read_factory_settings(use_empty=True)
    samples = 64 if a.quick else a.samples
    B.setup_cycles(samples)
    t0 = time.time()
    objs = B.import_glb(out / 'scene.glb')
    print(f'导入 {len(objs)} 个网格 {time.time() - t0:.0f}s', flush=True)
    B.kill_emission(objs)
    B.add_ground()
    vols = G.volumes()
    centers = G.all_centers(vols)
    t0 = time.time()
    valid = B.probe_validity(centers)
    print(f'坏探针 {int((~valid).sum())}/{len(valid)} {time.time() - t0:.0f}s', flush=True)
    np.save(raw / 'valid.npy', valid)
    ob, img, W, H = B.make_probe_mesh(centers)
    groups = [g for g in a.groups.split(',') if g]
    for g in groups:
        B.clear_lights()
        B.set_world((1, 1, 1), 0.0)
        if g == 'SKY':
            B.set_world((1, 1, 1), 1.0); passes = {'DIRECT', 'INDIRECT'}
        elif g == 'CEIL':
            for i, p in enumerate(meta['lights']['ceil']): B.add_point(p, 4 * math.pi, name=f'ceil{i}')
            passes = {'INDIRECT'}
        elif g in ('CORR_D', 'CORR_I'):
            for i, p in enumerate(meta['lights']['corr']): B.add_point(p, 4 * math.pi, name=f'corr{i}')
            passes = {'DIRECT'} if g == 'CORR_D' else {'INDIRECT'}
        elif g.startswith('SUN_'):
            B.add_sun(meta['sunKeys'][int(g[4:])]['dir']); passes = {'INDIRECT'}
        else:
            raise ValueError(g)
        print(f'[{g}]', flush=True)
        E = B.bake_irradiance(ob, img, W, H, passes, len(centers))
        np.save(raw / f'{g}.npy', E.astype(np.float32))
    (raw / 'bake_info.json').write_text(json.dumps(dict(
        groups=groups, samples=samples, quick=a.quick, n_probes=int(len(centers)),
        sunKeys=[k['dir'] for k in meta['sunKeys']]), ensure_ascii=False))

main()
```

- [ ] **Step 4: 快速烘焙（64 采样），测试转绿**

Run: `time /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P bake/blender_gi.py -- --quick 2>&1 | grep -E "导入|坏探针|^\[|烘焙|Error" ; python3 -m unittest bake/tests/test_gi_raw.py -v`
Expected: 13 组都打印 `烘焙 … s`；6 个测试 PASS。记录每组耗时（用于估算完整烘焙）。

- [ ] **Step 5: 完整烘焙（1024 采样）**

Run: `time /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P bake/blender_gi.py 2>&1 | grep -E "导入|坏探针|^\[|烘焙|Error" ; python3 -m unittest bake/tests/test_gi_raw.py -v`
Expected: 测试 PASS。若总时长 > 40 分钟，改为 `--samples 512` 并在 `bake_info.json` 里体现。

- [ ] **Step 6: Commit**

```bash
git add bake/blender_common.py bake/blender_gi.py bake/tests/test_gi_raw.py
git commit -m "feat(bake): Blender Cycles 逐组烘焙探针体积（天光/吊顶/走廊/太阳×9）

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 打包 GI 图集并写入 HTML

**Files:**
- Create: `bake/pack_gi.py`, `bake/tests/test_pack_gi.py`

**Interfaces:**
- Consumes: Task 4 的 `gi_raw/*`；`gi_lib.*`；`embed.build_payload/embed`。
- Produces: `bake/out/gi_atlas.png`（RGB8，`rows*H × cols*W`）、`bake/out/gi.json`（`runtime_meta` 结构 + `samples/quick/invalid`）。

- [ ] **Step 1: 写失败的单测（用合成数据）**

`bake/tests/test_pack_gi.py`：

```python
import json, sys, tempfile, unittest
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi_lib as G
import pack_gi

class TestPackGi(unittest.TestCase):
    def test_pack_synthetic(self):
        vols = G.volumes(); _, n = G.probe_offsets(vols)
        with tempfile.TemporaryDirectory() as d:
            out = Path(d); raw = out / 'gi_raw'; raw.mkdir()
            valid = np.ones(n, bool); valid[100:140] = False
            for gi, g in enumerate(G.GROUPS):
                E = np.full((n, 6, 3), float(gi + 1), np.float32); E[100:140] = 1e6   # 坏探针里是垃圾值
                np.save(raw / f'{g}.npy', E)
            np.save(raw / 'valid.npy', valid)
            (raw / 'bake_info.json').write_text(json.dumps(dict(groups=G.GROUPS, samples=8, quick=True, n_probes=n,
                                                                sunKeys=[[1, -1, 0]] * 9)))
            pack_gi.main(out)
            meta = json.loads((out / 'gi.json').read_text())
            big = np.asarray(Image.open(out / 'gi_atlas.png').convert('RGB'))
            L = meta['atlas']
            self.assertEqual(big.shape, (L['rows'] * L['H'], L['cols'] * L['W'], 3))
            for gi in [0, 5, 12]:
                r, c = divmod(gi, L['cols'])
                cell = big[r * L['H']:(r + 1) * L['H'], c * L['W']:(c + 1) * L['W']]
                v = G.decode_log(cell[3, 3, 0], meta['scales'][gi])
                self.assertAlmostEqual(float(v), gi + 1, delta=(gi + 1) * 0.03)   # 坏探针已被邻居填补，不是 1e6
            self.assertEqual(meta['groups'], G.GROUPS)
            self.assertEqual(meta['invalid'], 40)

if __name__ == '__main__':
    unittest.main()
```

Run: `python3 -m unittest bake/tests/test_pack_gi.py -v`
Expected: ERROR（`No module named 'pack_gi'`）

- [ ] **Step 2: 实现 pack_gi.py**

`bake/pack_gi.py`：

```python
#!/usr/bin/env python3
"""把 Blender 烘出的原始探针数据修补、编码成运行时图集：bake/out/gi_atlas.png + gi.json"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gi_lib as G

def main(out=HERE / 'out'):
    out = Path(out); raw = out / 'gi_raw'
    info = json.loads((raw / 'bake_info.json').read_text())
    groups = info['groups']
    if groups != G.GROUPS:
        raise SystemExit(f'组不全：{groups}（需要全部 {len(G.GROUPS)} 组，先完整烘焙）')
    vols = G.volumes(); layout = G.atlas_layout(vols)
    valid = np.load(raw / 'valid.npy')
    cells, scales = [], []
    for g in groups:
        E = np.nan_to_num(np.maximum(np.load(raw / f'{g}.npy').astype(np.float64), 0.0))
        E = G.fill_invalid_all(E, valid, vols)
        A = G.pack_atlas(E, vols, layout)
        s = G.robust_scale(A)
        cells.append(G.encode_log(A, s)); scales.append(s)
        print(f'{g:7s} scale={s:.4g} mean={A.mean():.4g}')
    big = G.tile_groups(cells, layout)
    Image.fromarray(big, 'RGB').save(out / 'gi_atlas.png', optimize=True)
    meta = G.runtime_meta(layout, vols, groups, scales, info['sunKeys'],
                          extra=dict(samples=info['samples'], quick=info['quick'], invalid=int((~valid).sum())))
    (out / 'gi.json').write_text(json.dumps(meta, ensure_ascii=False))
    print('gi_atlas.png', (out / 'gi_atlas.png').stat().st_size // 1024, 'KB', big.shape)

if __name__ == '__main__':
    main()
```

Run: `python3 -m unittest bake/tests/test_pack_gi.py -v`
Expected: PASS

- [ ] **Step 3: 打包真实数据并写入 HTML**

Run: `python3 bake/pack_gi.py && python3 bake/embed.py && ls -la classroom_v4_3.html`
Expected: 13 行 `scale=…`；`gi_atlas.png` 约 1.5–3MB；HTML ≤ 10MB。（运行时还没接 GI，画面不变——`__GI.status` 仍是 `'absent'` 以外的值也无妨，Task 7 才消费。）

- [ ] **Step 4: Commit**

```bash
git add bake/pack_gi.py bake/tests/test_pack_gi.py classroom_v4_3.html
git commit -m "feat(bake): GI 图集打包（坏探针修补 + 对数编码）并写入数据块

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 运行时纯函数（权重 / 太阳插值 / 天光）+ Node 单测

**Files:**
- Modify: `classroom_v4_3.html`（在"烘焙数据接入"段开头加入 `GI-PURE` 区块）
- Create: `bake/tests/gi_runtime.test.mjs`

**Interfaces:**
- Produces（页面全局，供 Task 7 使用）：`GI_GROUPS`（与 gi_lib.GROUPS 同序）、`giDecodeLog(u8, scale)`、`giLayerCoord(y, layers)`、`giSunAzimuth(dir)`、`giSunKeyWeights(dir, keyDirs) → number[]`（和为 1）、`giSkyRadiance(phase, wx:{fill,grey}) → [r,g,b]`、`giComputeWeights(st, keyDirs) → Float32Array(13*3)`，其中 `st = {sky:[3], skyScale, ceilI, ceilColor:[3], corrI, corrColor:[3], camInCorridor, sunI, sunColor:[3], sunDir:[3]}`。

- [ ] **Step 1: 写失败的 Node 单测**

`bake/tests/gi_runtime.test.mjs`：

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { HTML } from './helpers.mjs';

const src = readFileSync(HTML, 'utf8').match(/\/\/ ==GI-PURE-BEGIN==([\s\S]*?)\/\/ ==GI-PURE-END==/);
assert.ok(src, '页面里找不到 GI-PURE 区块');
const P = vm.runInNewContext(src[1] + ';({GI_GROUPS, giDecodeLog, giLayerCoord, giSunAzimuth, giSunKeyWeights, giSkyRadiance, giComputeWeights})', { Math, Float32Array, Array });

// 与导出脚本相同的太阳轨迹公式生成关键帧方向
const SD = 4, keys = [];
for (let a = -80; a <= 80; a += 20) {
  const rad = a * Math.PI / 180, h = Math.max(0, 1 - Math.abs(a) / 78);
  const p = [-9 * SD, 0.4 + (1 + h * 26 - 0.4) * SD, 6 + Math.sin(rad) * 7 * SD];
  const d = [0 - p[0], 0.4 - p[1], 6 - p[2]], l = Math.hypot(...d);
  keys.push(d.map(x => x / l));
}
const base = { sky: [0.2, 0.25, 0.3], skyScale: 1, ceilI: 0.5, ceilColor: [1, 1, 1], corrI: 1.3, corrColor: [0.7, 0.8, 0.9],
               camInCorridor: false, sunI: 4, sunColor: [1, 0.9, 0.8], sunDir: keys[2] };

test('分组顺序与 Python 一致', () => {
  assert.deepEqual([...P.GI_GROUPS], ['SKY', 'CEIL', 'CORR_D', 'CORR_I', 'SUN_0', 'SUN_1', 'SUN_2', 'SUN_3', 'SUN_4', 'SUN_5', 'SUN_6', 'SUN_7', 'SUN_8']);
});

test('对数解码端点', () => {
  assert.equal(P.giDecodeLog(0, 3), 0);
  assert.ok(Math.abs(P.giDecodeLog(255, 3) - 3) < 1e-12);
});

test('层号与 gi_lib 一致', () => {
  const L = [0.07, 0.28, 0.51, 0.81, 1.18, 1.55, 2.0, 2.5, 3.0, 3.36];
  assert.equal(P.giLayerCoord(-1, L), 0);
  assert.equal(P.giLayerCoord(0.81, L), 3);
  assert.ok(Math.abs(P.giLayerCoord((0.81 + 1.18) / 2, L) - 3.5) < 1e-12);
  assert.equal(P.giLayerCoord(5, L), 9);
});

test('太阳关键帧插值', () => {
  const w = P.giSunKeyWeights(keys[3], keys);
  assert.ok(Math.abs(w[3] - 1) < 1e-9);
  const mid = keys[3].map((x, i) => (x + keys[4][i]) / 2);
  const wm = P.giSunKeyWeights(mid, keys);
  assert.ok(wm[3] > 0.3 && wm[4] > 0.3 && Math.abs(wm[3] + wm[4] - 1) < 1e-9);
  const far = P.giSunKeyWeights([0.3, -0.1, -0.95], keys);   // 超出 +80° 端
  assert.equal(far.reduce((a, b) => a + b, 0), 1);
  assert.equal(far[8], 1);
});

test('天光：正午 > 清晨 > 深夜，深夜偏蓝，阴天更灰', () => {
  const sum = c => c[0] + c[1] + c[2];
  const clear = { fill: 1, grey: 0 };
  const noon = P.giSkyRadiance(0.5, clear), morning = P.giSkyRadiance(0.2, clear), night = P.giSkyRadiance(0.96, clear);
  assert.ok(sum(noon) > sum(morning) && sum(morning) > sum(night) && sum(night) > 0);
  assert.ok(night[2] > night[0]);
  const rain = P.giSkyRadiance(0.5, { fill: 1.18, grey: 0.64 });
  const sat = c => (Math.max(...c) - Math.min(...c)) / Math.max(...c);
  assert.ok(sat(rain) < sat(noon));
});

test('权重：走廊直射组在走廊里关闭；太阳为 0 或在地平线下时无太阳组', () => {
  const w = P.giComputeWeights(base, keys);
  assert.equal(w.length, 13 * 3);
  assert.ok(w[2 * 3] > 0);
  const wc = P.giComputeWeights({ ...base, camInCorridor: true }, keys);
  assert.equal(wc[2 * 3], 0); assert.ok(wc[3 * 3] > 0);
  const sunSum = ww => { let s = 0; for (let g = 4; g < 13; g++) s += ww[g * 3]; return s; };
  assert.ok(Math.abs(sunSum(w) - base.sunI * base.sunColor[0]) < 1e-5);
  assert.equal(sunSum(P.giComputeWeights({ ...base, sunI: 0 }, keys)), 0);
  assert.equal(sunSum(P.giComputeWeights({ ...base, sunDir: [0.5, 0.2, 0.0] }, keys)), 0);
  for (const x of w) assert.ok(Number.isFinite(x) && x >= 0);
});
```

Run: `node --test bake/tests/gi_runtime.test.mjs`
Expected: FAIL（`页面里找不到 GI-PURE 区块`）

- [ ] **Step 2: 在"烘焙数据接入"段开头加入纯函数区块**

在该段 `(() => {` 之前插入：

```js
// ==GI-PURE-BEGIN==  纯函数：不碰 DOM/WebGL，bake/tests/gi_runtime.test.mjs 直接抽出来单测
const GI_GROUPS = ['SKY', 'CEIL', 'CORR_D', 'CORR_I', 'SUN_0', 'SUN_1', 'SUN_2', 'SUN_3', 'SUN_4', 'SUN_5', 'SUN_6', 'SUN_7', 'SUN_8'];
function giDecodeLog(u8, scale) { return scale * (Math.pow(2, 8 * u8 / 255) - 1) / 255; }
function giLayerCoord(y, L) {
  if (y <= L[0]) return 0;
  for (let i = 0; i < L.length - 1; i++) if (y < L[i + 1]) return i + (y - L[i]) / (L[i + 1] - L[i]);
  return L.length - 1;
}
// 光线方向（太阳 → 场景）的水平方位：太阳恒在左窗外，光朝 +x（dir.x > 0）；沿窗墙(z)扫掠，
// 角度滑块 a 越大太阳越往 +z → -dir.z 越大 → 方位角单调增加，跨正午也连续（不会在 ±π 处跳变）
function giSunAzimuth(dir) { return Math.atan2(-dir[2], dir[0]); }
function giSunKeyWeights(dir, keyDirs) {
  const a = giSunAzimuth(dir), ks = keyDirs.map(giSunAzimuth), n = ks.length;
  const w = new Array(n).fill(0);
  if (a <= ks[0]) { w[0] = 1; return w; }
  if (a >= ks[n - 1]) { w[n - 1] = 1; return w; }
  for (let i = 0; i < n - 1; i++) {
    if (a >= ks[i] && a <= ks[i + 1]) { const t = (a - ks[i]) / (ks[i + 1] - ks[i]); w[i] = 1 - t; w[i + 1] = t; return w; }
  }
  w[0] = 1; return w;
}
// 均匀天空亮度（烘焙 SKY 组的倍数）。曲线与时间轴里驱动半球光的那条一致（dayUp / skyLevel / warmK / moonGlow），
// 天气：fill 抬高漫射、grey 向冷灰 (0.60,0.66,0.75) 靠拢——与 applyWeatherLighting 的 _wxGrey 同色。
function giSkyRadiance(phase, wx) {
  const DAWN = 0.10, DUSK = 0.90;
  const dayUp = (phase > DAWN && phase < DUSK) ? Math.sin(Math.PI * (phase - DAWN) / (DUSK - DAWN)) : 0;
  const dayLit = Math.min(1, dayUp * 3);
  const skyLevel = Math.min(1, dayUp * 1.4);
  const warmK = dayLit * Math.max(0, 1 - dayUp * 1.6);
  const moonGlow = (1 - dayLit) * 0.05;
  const I = Math.max(moonGlow, skyLevel * (0.22 + 0.46 * dayUp)) * wx.fill;
  let r = 0.70 + warmK * 0.30, g = 0.82 - warmK * 0.06, b = 1.0 - warmK * 0.52;
  const k = wx.grey;
  r += (0.60 - r) * k; g += (0.66 - g) * k; b += (0.75 - b) * k;
  return [r * I, g * I, b * I];
}
function giComputeWeights(st, keyDirs) {
  const w = new Float32Array(GI_GROUPS.length * 3);
  const set = (i, c, s) => { w[i * 3] = c[0] * s; w[i * 3 + 1] = c[1] * s; w[i * 3 + 2] = c[2] * s; };
  set(0, st.sky, st.skyScale);
  set(1, st.ceilColor, st.ceilI);
  set(2, st.corrColor, st.camInCorridor ? 0 : st.corrI);    // 走廊里由实时走廊灯给直射，烘焙直射组让位
  set(3, st.corrColor, st.corrI);
  if (st.sunI > 0 && st.sunDir[1] < 0) {
    const kw = giSunKeyWeights(st.sunDir, keyDirs);
    for (let k = 0; k < kw.length; k++) if (kw[k]) set(4 + k, st.sunColor, st.sunI * kw[k]);
  }
  return w;
}
// ==GI-PURE-END==
```

Run: `node --test bake/tests/gi_runtime.test.mjs`
Expected: 7 个测试 PASS

- [ ] **Step 3: Commit**

```bash
git add classroom_v4_3.html bake/tests/gi_runtime.test.mjs
git commit -m "feat: GI 运行时纯函数（分组权重/太阳关键帧插值/天光曲线）+ Node 单测

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 运行时 GI 接入（GPU 合成 + 着色器补丁 + 拆灯 + 权重接线）

**Files:**
- Modify: `classroom_v4_3.html`（顶部声明 `giPresetKey`；`applyPreset`/`markCustom` 各加一行；`animate` 里加 `GI.update` 调用；"烘焙数据接入"段加入 GI 部分）
- Create: `bake/tests/runtime_gi.test.mjs`

**Interfaces:**
- Consumes: Task 6 纯函数；`window.BAKED.gi = {meta, atlas}`（Task 5）；页面全局 `scene, renderer, camera, mainLight, fluoroLights, ceilColor, corrLampLights, wxFillMul, wxHemiGrey, driftOn, driftT, PRESET_SKY_PHASE, _corridorLayerOn, applyCorridorLayer, updateCorridorLightLayer, windowFills, ceilBounce, floorBounce, winSpot, rWin, doorCorridorLeaks, corrGlowMats`。
- Produces: `window.__GI = {status:'active'|'absent'|'error', active, removedLights:11, lastWeights:Float32Array, update(), uniforms}`；`GI_SKY_SCALE`（Task 8 校准）。

- [ ] **Step 1: 写失败的集成测试（含 Review Focus 1–5）**

`bake/tests/runtime_gi.test.mjs`：

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { launch, fileUrl } from '../cdp.mjs';
import { HTML, noDataCopy, errorsIn } from './helpers.mjs';

const lightCount = `(() => { let n = 0; scene.traverse(o => { if (o.isLight) n++; }); return n; })()`;
const meanLum = `(() => { renderer.render(scene, camera); const gl = renderer.getContext(); const w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
  const px = new Uint8Array(4 * 64 * 36); let s = 0, k = 0;
  const buf = new Uint8Array(w * h * 4); gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, buf);
  for (let y = 0; y < h; y += Math.floor(h / 36)) for (let x = 0; x < w; x += Math.floor(w / 64)) { const i = 4 * (y * w + x); s += (buf[i] + buf[i + 1] + buf[i + 2]) / 3; k++; }
  return s / k; })()`;
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function open(path) {
  const b = await launch();
  await b.goto(fileUrl(path));
  await b.waitFor("window.__GI && __GI.status !== 'pending' && __GI.texStatus !== 'pending'");
  await sleep(800);
  return b;
}

test('GI 激活、拆掉 11 盏假补光、控制台无着色器错误', async () => {
  const ref = await open(noDataCopy());
  const nRef = await ref.evaluate(lightCount);
  assert.equal(await ref.evaluate('__GI.status'), 'absent');
  await ref.close();
  const b = await open(HTML);
  try {
    assert.equal(await b.evaluate('__GI.status'), 'active');
    assert.equal(await b.evaluate('__GI.removedLights'), 11);
    assert.equal(await b.evaluate(lightCount), nRef - 11);
    for (const k of ['morning', 'noon', 'dusk', 'night']) {
      await b.evaluate(`applyPreset('${k}'); applyView(CAM_VIEWS['5']); true`);
      await sleep(1500);
      const L = await b.evaluate(meanLum);
      assert.ok(Number.isFinite(L) && L > 2 && L < 250, `${k} 亮度异常 ${L}`);
    }
    assert.deepEqual(errorsIn(b.logs), []);
  } finally { await b.close(); }
});

test('监控墙与 GI 共存', async () => {
  const b = await open(HTML);
  try {
    await b.evaluate("toggleMonitor(true); true");
    await sleep(1500);
    await b.evaluate("document.getElementById('ceilOn').checked = false; syncCeiling(); true");   // 迫使合成通道在监控墙模式下重跑
    await sleep(800);
    const L = await b.evaluate(`(() => { const gl = renderer.getContext(); const p = new Uint8Array(4);
      gl.readPixels(Math.floor(gl.drawingBufferWidth * 0.25), Math.floor(gl.drawingBufferHeight * 0.6), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, p); return p[0] + p[1] + p[2]; })()`);
    assert.ok(L > 0, '监控墙画面是黑的');
    await b.evaluate("toggleMonitor(false); true");
    assert.deepEqual(errorsIn(b.logs), []);
  } finally { await b.close(); }
});

test('时间轴全天推移权重有限', async () => {
  const b = await open(HTML);
  try {
    const bad = await b.evaluate(`(() => { toggleDrift(); driftPlaying = false; let bad = 0;
      for (let i = 0; i <= 50; i++) { driftT = i / 50; onTimelineScrub(driftT); __GI.update();
        for (const x of __GI.lastWeights) if (!Number.isFinite(x) || x < 0) bad++; }
      return bad; })()`);
    assert.equal(bad, 0);
    assert.deepEqual(errorsIn(b.logs), []);
  } finally { await b.close(); }
});

test('天气与深夜改变天光权重', async () => {
  const b = await open(HTML);
  try {
    const sky = `(__GI.update(), [__GI.lastWeights[0], __GI.lastWeights[1], __GI.lastWeights[2]])`;
    await b.evaluate("applyPreset('noon'); setWeather('clear'); true"); await sleep(300);
    const clear = await b.evaluate(sky);
    await b.evaluate("setWeather('rain'); true"); await sleep(300);
    const rain = await b.evaluate(sky);
    await b.evaluate("setWeather('clear'); applyPreset('night'); true"); await sleep(300);
    const night = await b.evaluate(sky);
    const sat = c => (Math.max(...c) - Math.min(...c)) / Math.max(...c);
    assert.ok(sat(rain) < sat(clear), '雨天天光没有变灰');
    assert.ok(night[0] + night[1] + night[2] < 0.2 * (clear[0] + clear[1] + clear[2]), '深夜天光没有变暗');
    assert.ok(night[2] > night[0], '深夜天光不偏蓝');
  } finally { await b.close(); }
});

test('进出走廊切换走廊直射组', async () => {
  const b = await open(HTML);
  try {
    await b.evaluate("applyView({fov:70, theta:Math.PI, phi:0.02, camR:0.6, panX:7.95, panZ:4.0, panY:0.1, name:'走廊'}); true");
    await sleep(500);
    assert.equal(await b.evaluate('_corridorLayerOn'), true);
    assert.equal(await b.evaluate('(__GI.update(), __GI.lastWeights[2 * 3])'), 0);
    await b.evaluate("applyView(CAM_VIEWS['5']); true");
    await sleep(500);
    assert.equal(await b.evaluate('_corridorLayerOn'), false);
    assert.deepEqual(errorsIn(b.logs), []);
  } finally { await b.close(); }
});
```

Run: `node --test bake/tests/runtime_gi.test.mjs`
Expected: FAIL（`__GI.status` 不是 `'active'`）

- [ ] **Step 2: 早期声明 + 预设钩子 + 渲染循环调用**

1) 在 `let monitorOn = false;` 下一行插入：

```js
// 当前时间预设（供烘焙 GI 的天光曲线取时刻）。必须在这里声明：applyPreset('morning') 在初始化阶段就会调用，
// 而 let/const 在声明前是暂时性死区（typeof 也挡不住，本文件已因此踩过三次）。
let giPresetKey = 'morning';
```

2) 在 `function applyPreset(k){` 下一行插入：`  giPresetKey = k;`

3) 在 `function markCustom(){` 下一行插入：`  giPresetKey = 'custom';`

4) 在 `animate` 里找到：

```js
  applyWeatherLighting();  // 天气→弱化直射/冷灰化（须在 sync 之后、渲染之前）
  updatePrecip();          // 雨/雪下落
```

在其后插入：

```js
  // 烘焙 GI：按当前太阳/天光/吊顶灯/走廊灯重新合成间接光（只在权重变化时才真画；必须在灯光状态都写完之后）
  if(window.__GI && window.__GI.active) window.__GI.update();
```

- [ ] **Step 3: "烘焙数据接入"段加入 GI 部分**

在该段 IIFE 里、`async function boot()` 之前插入：

```js
  // ── 全局光照（GI）：探针体积，见 spec D1–D7 ─────────────────────────────────────────
  // 天光强度绝对尺度：giSkyRadiance 给出的是"半球光强度×颜色"，均匀天空亮度 L 与之相差 1/π（E=πL）。
  // Task 8 以 Cycles 参考图校准后改这里。
  let GI_SKY_SCALE = 1 / Math.PI;
  const U = {
    giAtlas: { value: null }, giAtlasSize: { value: new THREE.Vector2(1, 1) }, giOn: { value: 0 },
    giBoxMin: { value: [new THREE.Vector3(), new THREE.Vector3()] }, giBoxMax: { value: [new THREE.Vector3(), new THREE.Vector3()] },
    giOrigin: { value: [new THREE.Vector3(), new THREE.Vector3()] }, giStep: { value: [new THREE.Vector3(), new THREE.Vector3()] },
    giCount: { value: [new THREE.Vector3(), new THREE.Vector3()] }, giRegion: { value: [new THREE.Vector4(), new THREE.Vector4()] },
    giLayers: { value: new Array(10).fill(0) },
  };
  GI.uniforms = U;
  let giMeta = null, groupTex = null, rt = null, quadScene = null, quadCam = null, combineMat = null;

  const GI_PARS = /* glsl */`
uniform sampler2D giAtlas; uniform vec2 giAtlasSize; uniform float giOn;
uniform vec3 giBoxMin[2]; uniform vec3 giBoxMax[2]; uniform vec3 giOrigin[2]; uniform vec3 giStep[2]; uniform vec3 giCount[2];
uniform vec4 giRegion[2]; uniform float giLayers[10];
float giLayerCoord( float y ) {
  if ( y <= giLayers[ 0 ] ) return 0.0;
  for ( int i = 0; i < 9; i ++ ) { if ( y < giLayers[ i + 1 ] ) return float( i ) + ( y - giLayers[ i ] ) / ( giLayers[ i + 1 ] - giLayers[ i ] ); }
  return 9.0;
}
int giVolumeAt( vec3 p ) {
  if ( all( greaterThan( p, giBoxMin[ 0 ] ) ) && all( lessThan( p, giBoxMax[ 0 ] ) ) ) return 0;
  if ( all( greaterThan( p, giBoxMin[ 1 ] ) ) && all( lessThan( p, giBoxMax[ 1 ] ) ) ) return 1;
  return -1;
}
vec3 giTex( vec4 R, vec3 C, float face, float iz, vec2 inTile ) {
  float tile = face * C.z + iz;
  float tx = mod( tile, R.z ), ty = floor( tile / R.z );
  vec2 px = R.xy + vec2( tx * C.x, ty * C.y ) + inTile;
  return texture2D( giAtlas, px / giAtlasSize ).rgb;
}
vec3 giIrradiance( int v, vec3 p, vec3 n ) {
  vec3 O = v == 0 ? giOrigin[ 0 ] : giOrigin[ 1 ];
  vec3 S = v == 0 ? giStep[ 0 ] : giStep[ 1 ];
  vec3 C = v == 0 ? giCount[ 0 ] : giCount[ 1 ];
  vec4 R = v == 0 ? giRegion[ 0 ] : giRegion[ 1 ];
  float gx = clamp( ( p.x - O.x ) / S.x, 0.0, C.x - 1.0 );
  float gz = clamp( ( p.z - O.z ) / S.z, 0.0, C.z - 1.0 );
  vec2 inTile = vec2( gx, giLayerCoord( p.y ) ) + 0.5;            // 双线性只碰本格内的像素
  float z0 = floor( gz ), z1 = min( z0 + 1.0, C.z - 1.0 ), t = gz - z0;
  float fx = n.x >= 0.0 ? 0.0 : 1.0, fy = n.y >= 0.0 ? 2.0 : 3.0, fz = n.z >= 0.0 ? 4.0 : 5.0;
  vec3 cx = mix( giTex( R, C, fx, z0, inTile ), giTex( R, C, fx, z1, inTile ), t );
  vec3 cy = mix( giTex( R, C, fy, z0, inTile ), giTex( R, C, fy, z1, inTile ), t );
  vec3 cz = mix( giTex( R, C, fz, z0, inTile ), giTex( R, C, fz, z1, inTile ), t );
  vec3 n2 = n * n;
  return n2.x * cx + n2.y * cy + n2.z * cz;                         // 环境立方体（ambient cube）
}`;
  const GI_APPLY = /* glsl */`
float giInside = 0.0;
if ( giOn > 0.5 ) {
  vec3 giP = ( vec4( geometryPosition - viewMatrix[ 3 ].xyz, 0.0 ) * viewMatrix ).xyz;   // 视空间 → 世界（刚体逆 = 转置）
  vec3 giN = normalize( ( vec4( geometryNormal, 0.0 ) * viewMatrix ).xyz );
  int giV = giVolumeAt( giP + giN * 0.03 );          // 沿法线外推判内外：双面墙的室内面/室外面各走各的
  if ( giV >= 0 ) { irradiance = giIrradiance( giV, giP + giN * 0.10, giN ); giInside = 1.0; }
}`;
  function giPatchFragment(fs) {
    return fs
      .replace('#include <lights_pars_begin>', '#include <lights_pars_begin>\n' + GI_PARS)
      .replace('#include <lights_fragment_begin>', '#include <lights_fragment_begin>\n' + GI_APPLY)
      .replace('#include <lights_fragment_maps>', '#include <lights_fragment_maps>\niblIrradiance *= ( 1.0 - giInside );');
  }

  function giSnapshot() {
    const d = new THREE.Vector3().subVectors(mainLight.target.position, mainLight.position).normalize();
    const phase = driftOn ? (driftT % 1) : (PRESET_SKY_PHASE[giPresetKey] ?? 0.34);
    const cc = corrLampLights[0].color;
    return {
      sky: giSkyRadiance(phase, { fill: wxFillMul, grey: wxHemiGrey }), skyScale: GI_SKY_SCALE,
      ceilI: fluoroLights[0].intensity, ceilColor: [ceilColor.r, ceilColor.g, ceilColor.b],
      corrI: corrLampLights[0].intensity, corrColor: [cc.r, cc.g, cc.b],
      camInCorridor: !!_corridorLayerOn,
      sunI: mainLight.intensity, sunColor: [mainLight.color.r, mainLight.color.g, mainLight.color.b], sunDir: [d.x, d.y, d.z],
    };
  }

  async function initGI(G) {
    giMeta = G.meta;
    const im = await loadImage(G.atlas);
    const cv = document.createElement('canvas'); cv.width = im.width; cv.height = im.height;
    const g2 = cv.getContext('2d', { willReadFrequently: true }); g2.drawImage(im, 0, 0);
    const px = g2.getImageData(0, 0, im.width, im.height).data;      // 无透明通道的 PNG → alpha 恒 255，无预乘损失
    groupTex = new THREE.DataTexture(new Uint8Array(px.buffer), im.width, im.height, THREE.RGBAFormat, THREE.UnsignedByteType);
    groupTex.minFilter = groupTex.magFilter = THREE.NearestFilter; groupTex.generateMipmaps = false; groupTex.needsUpdate = true;
    const A = giMeta.atlas, nG = giMeta.groups.length;
    rt = new THREE.WebGLRenderTarget(A.W, A.H, { type: THREE.HalfFloatType, format: THREE.RGBAFormat,
      minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, depthBuffer: false, generateMipmaps: false });
    combineMat = new THREE.ShaderMaterial({
      defines: { G: nG },
      uniforms: { groups: { value: groupTex }, scales: { value: giMeta.scales.slice() },
                  weights: { value: giMeta.groups.map(() => new THREE.Vector3()) },
                  cell: { value: new THREE.Vector2(A.W, A.H) }, cols: { value: A.cols } },
      vertexShader: 'void main(){ gl_Position = vec4( position.xy, 0.0, 1.0 ); }',
      fragmentShader: /* glsl */`
        uniform sampler2D groups; uniform float scales[ G ]; uniform vec3 weights[ G ]; uniform vec2 cell; uniform float cols;
        void main() {
          ivec2 p = ivec2( gl_FragCoord.xy );
          vec3 sum = vec3( 0.0 );
          for ( int g = 0; g < G; g ++ ) {
            ivec2 o = ivec2( int( mod( float( g ), cols ) * cell.x ), int( floor( float( g ) / cols ) * cell.y ) );
            vec3 e = texelFetch( groups, o + p, 0 ).rgb;
            sum += weights[ g ] * scales[ g ] * ( exp2( 8.0 * e ) - 1.0 ) / 255.0;     // 对数解码，与 gi_lib.decode_log 一致
          }
          gl_FragColor = vec4( sum, 1.0 );
        }`,
      depthTest: false, depthWrite: false,
    });
    quadScene = new THREE.Scene(); quadCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), combineMat); quad.frustumCulled = false; quadScene.add(quad);
    U.giAtlas.value = rt.texture; U.giAtlasSize.value.set(A.W, A.H);
    giMeta.volumes.forEach((v, i) => {
      U.giBoxMin.value[i].fromArray(v.box[0]); U.giBoxMax.value[i].fromArray(v.box[1]);
      U.giOrigin.value[i].set(v.x0, 0, v.z0);
      U.giStep.value[i].set((v.x1 - v.x0) / (v.nx - 1), 0, (v.z1 - v.z0) / (v.nz - 1));
      U.giCount.value[i].set(v.nx, giMeta.layers.length, v.nz);
      const r = A.regions[i]; U.giRegion.value[i].set(r.x0, r.y0, r.tpr, 0);
    });
    U.giLayers.value = giMeta.layers.slice();
  }

  function combine(w) {
    const W = combineMat.uniforms.weights.value;
    for (let g = 0; g < W.length; g++) W[g].set(w[g * 3], w[g * 3 + 1], w[g * 3 + 2]);
    const prevRT = renderer.getRenderTarget(), prevAuto = renderer.autoClear, prevShadow = renderer.shadowMap.needsUpdate;
    renderer.shadowMap.needsUpdate = false;           // 别让空场景把本帧主场景的阴影刷新"吃掉"
    renderer.autoClear = true;
    renderer.setRenderTarget(rt);
    renderer.render(quadScene, quadCam);
    renderer.setRenderTarget(prevRT);
    renderer.autoClear = prevAuto;
    renderer.shadowMap.needsUpdate = prevShadow;
  }
  GI.update = function () {
    const w = giComputeWeights(giSnapshot(), giMeta.sunKeys);
    const last = GI.lastWeights;
    let changed = !last, mx = 1e-6;
    for (let i = 0; i < w.length; i++) mx = Math.max(mx, Math.abs(w[i]));
    if (last) for (let i = 0; i < w.length; i++) if (Math.abs(w[i] - last[i]) > 1e-3 * mx) { changed = true; break; }
    if (changed) { combine(w); GI.lastWeights = w; }
  };

  function patchMaterials() {
    const proto = THREE.MeshStandardMaterial.prototype;
    proto.onBeforeCompile = function (shader) {
      if (!GI.active) return;
      Object.assign(shader.uniforms, U);                          // 同一组 uniform 对象：改一次，所有材质同步
      shader.fragmentShader = giPatchFragment(shader.fragmentShader);
    };
    proto.customProgramCacheKey = function () { return GI.active ? 'gi1' : 'gi0'; };   // 否则会复用激活前的旧程序
    scene.traverse(o => {
      for (const m of (Array.isArray(o.material) ? o.material : [o.material])) if (m && m.isMeshStandardMaterial) m.needsUpdate = true;
    });
  }
  // 这 11 盏灯模拟的东西（窗光散射 / 天花板与地面反弹 / 走廊漏光）全部由烘焙组物理地给出。
  // 只在加载期摘一次 → 运行时灯数不变，不会引发着色器重编卡顿。
  function removeFakeLights() {
    const fakes = [...windowFills, ...ceilBounce, ...floorBounce, winSpot, rWin, ...doorCorridorLeaks.map(d => d.light)];
    for (const L of fakes) { L.removeFromParent(); if (L.target) L.target.removeFromParent(); }
    GI.removedLights = fakes.length;
    // 走廊墙/地/顶的自发光是"假装被灯照亮"——现在由烘焙走廊组真照亮，置 0；灯板本体(isLamp)照旧发光
    corrGlowMats.forEach(g => { if (!g.isLamp) g.emisMax = 0; });
  }
  function warmUp() {
    try {
      for (const inC of [true, false]) { applyCorridorLayer(inC); renderer.compile(scene, camera); }
      updateCorridorLightLayer(undefined);
    } catch (e) { console.warn('[GI] 预编译失败（不影响功能）', e); }
  }
```

然后把 `boot()` 末尾的 `if (!B || !B.gi) GI.status = 'absent';` 替换为：

```js
    if (!B || !B.gi) { GI.status = 'absent'; return; }
    try {
      await initGI(B.gi);
      GI.active = true;
      U.giOn.value = 1;
      patchMaterials();
      removeFakeLights();
      GI.update();
      warmUp();
      GI.status = 'active';
    } catch (e) {
      console.warn('[GI] 烘焙光照加载失败，回退原画面：', e);
      GI.active = false; U.giOn.value = 0; GI.status = 'error';
    }
```

- [ ] **Step 4: 运行集成测试**

Run: `node --test bake/tests/runtime_gi.test.mjs bake/tests/runtime_textures.test.mjs bake/tests/gi_runtime.test.mjs`
Expected: 全部 PASS。若"控制台无着色器错误"失败，看 `b.logs` 里的 GLSL 报错行修 `GI_PARS/GI_APPLY`。

- [ ] **Step 5: 回退逐像素一致**

Run:

```bash
node -e "
import('./bake/cdp.mjs').then(async ({launch, fileUrl}) => {
  const { noDataCopy } = await import('./bake/tests/helpers.mjs');
  const shot = async p => { const b = await launch(); await b.goto(fileUrl(p));
    await b.waitFor(\"!window.__GI || (__GI.status !== 'pending' && __GI.texStatus !== 'pending')\");
    await b.evaluate(\"applyPreset('noon'); applyView(CAM_VIEWS['7']); true\"); await new Promise(r => setTimeout(r, 3000));
    const d = await b.evaluate('renderer.domElement.toDataURL()'); await b.close(); return d; };
  const a = await shot(process.cwd() + '/bake/out/before.html'), a2 = await shot(process.cwd() + '/bake/out/before.html'), c = await shot(noDataCopy());
  console.log('before 自身重复一致:', a === a2, ' 无数据版 == before:', a === c);
});"
```

Expected: `before 自身重复一致: true  无数据版 == before: true`。若 before 自身都不一致（场景含时间动画），改为解码比较 meanAbs，要求无数据版与 before 的差 ≤ before 自身两次之差。

- [ ] **Step 6: 截图看效果**

用 Task 2 Step 13 的脚本把 `tex` 改成 `gi`，拍 morning/noon/dusk/night × 机位 5、7 到 `bake/out/shots/gi_*.png`，Read 查看。
Expected: 天花板近窗处被地面反弹照亮、墙角/桌下有自然暗部、整体不发灰；没有色块、条带、黑斑（若有黑斑，多半是坏探针没修好或层高不贴合——记录位置留给 Task 8）。

- [ ] **Step 7: Commit**

```bash
git add classroom_v4_3.html bake/tests/runtime_gi.test.mjs
git commit -m "feat: 烘焙 GI 接入实时渲染——GPU 合成 + 着色器补丁 + 拆 11 盏假补光 + 权重接线

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Cycles 参考图、三联对比与校准

**Files:**
- Create: `bake/capture_views.mjs`, `bake/blender_reference.py`, `bake/compare.py`, `bake/tests/test_compare.py`
- Modify: `classroom_v4_3.html`（`__GI.tune()` 调参入口；按校准结果写死 `GI_SKY_SCALE` 与假效果开关）
- Modify: spec（追加"校准结果"小节）

**Interfaces:**
- Consumes: `bake/out/before.html`、当前 HTML、`scene.glb`、`__GI.lastWeights`。
- Produces: `bake/out/views/<case>.json`（相机 + 灯光状态）、`<case>_after.png`、`<case>_before.png`、`<case>_ref.npy`；`compare.py` 输出 `docs/superpowers/compare/cyclesgi_<case>.png` 三联图 + 终端表格；`aces_srgb(lin, exposure) → uint8`、`grid_log_error(a, b) → float`。

- [ ] **Step 1: 写失败的 compare 单测**

`bake/tests/test_compare.py`：

```python
import sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare as C

class TestCompare(unittest.TestCase):
    def test_aces_matches_threejs_reference_points(self):
        # three.js ACESFilmicToneMapping(exposure=1)：0 → 0；极亮 → 接近白
        out = C.aces_srgb(np.array([[[0.0, 0.0, 0.0], [100.0, 100.0, 100.0]]]), 1.0)
        self.assertEqual(out[0, 0].tolist(), [0, 0, 0])
        self.assertTrue(np.all(out[0, 1] >= 250))
        mid = C.aces_srgb(np.array([[[0.18, 0.18, 0.18]]]), 1.0)[0, 0, 0]
        self.assertTrue(100 < mid < 160)

    def test_grid_log_error_zero_for_identical(self):
        a = (np.random.default_rng(0).random((90, 160, 3)) * 255).astype(np.uint8)
        self.assertAlmostEqual(C.grid_log_error(a, a), 0.0)
        self.assertGreater(C.grid_log_error(a, (a * 0.5).astype(np.uint8)), 0.5)

if __name__ == '__main__':
    unittest.main()
```

Run: `python3 -m unittest bake/tests/test_compare.py -v`
Expected: ERROR（`No module named 'compare'`）

- [ ] **Step 2: 实现 compare.py**

`bake/compare.py`：

```python
#!/usr/bin/env python3
"""参考图色调映射（与 three.js ACESFilmic 逐式一致）+ 分格亮度偏差 + 三联图。
用法：python3 bake/compare.py   （读 bake/out/views/，写 docs/superpowers/compare/cyclesgi_*.png）"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
HERE = Path(__file__).resolve().parent
VIEWS = HERE / 'out' / 'views'
DOCS = HERE.parent / 'docs' / 'superpowers' / 'compare'

IN = np.array([[0.59719, 0.35458, 0.04823], [0.07600, 0.90834, 0.01566], [0.02840, 0.13383, 0.83777]])
OUTM = np.array([[1.60475, -0.53108, -0.07367], [-0.10208, 1.10813, -0.00605], [-0.00327, -0.07276, 1.07602]])

def aces_srgb(lin, exposure):
    """three.js r164 ACESFilmicToneMapping + sRGB OETF；lin: (H,W,3) 线性 → uint8"""
    c = np.asarray(lin, np.float64) * (exposure / 0.6)
    c = c @ IN.T
    a = c * (c + 0.0245786) - 0.000090537
    b = c * (0.983729 * c + 0.4329510) + 0.238081
    c = np.clip((a / b) @ OUTM.T, 0, 1)
    s = np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - 0.055)
    return (np.clip(s, 0, 1) * 255 + 0.5).astype(np.uint8)

def _lum(img):
    x = np.asarray(img, np.float64) / 255.0
    lin = np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
    return lin @ np.array([0.2126, 0.7152, 0.0722])

def grid_log_error(a, b, gx=8, gy=6, floor=2 / 255):
    """8×6 分格平均线性亮度的 |log(a/b)| 中位数（两边都太暗的格子不计）。0 = 一致。"""
    la, lb = _lum(a), _lum(b)
    H, W = la.shape
    errs = []
    for j in range(gy):
        for i in range(gx):
            sa = la[j * H // gy:(j + 1) * H // gy, i * W // gx:(i + 1) * W // gx].mean()
            sb = lb[j * H // gy:(j + 1) * H // gy, i * W // gx:(i + 1) * W // gx].mean()
            if sa > floor and sb > floor:
                errs.append(abs(np.log(sa / sb)))
    return float(np.median(errs)) if errs else 0.0

def triptych(imgs, labels, path):
    w, h = imgs[0].size
    out = Image.new('RGB', (w * len(imgs), h + 28), (12, 12, 14))
    d = ImageDraw.Draw(out)
    for i, (im, lb) in enumerate(zip(imgs, labels)):
        out.paste(im, (i * w, 28)); d.text((i * w + 10, 8), lb, fill=(230, 230, 230))
    out.save(path)

def main():
    DOCS.mkdir(parents=True, exist_ok=True)
    rows = []
    for js in sorted(VIEWS.glob('*.json')):
        case = js.stem; st = json.loads(js.read_text())
        ref_npy = VIEWS / f'{case}_ref.npy'
        if not ref_npy.exists():
            continue
        after = Image.open(VIEWS / f'{case}_after.png').convert('RGB')
        before = Image.open(VIEWS / f'{case}_before.png').convert('RGB').resize(after.size)
        ref = Image.fromarray(aces_srgb(np.load(ref_npy), st['exposure'])).resize(after.size)
        ea, eb = grid_log_error(np.asarray(after), np.asarray(ref)), grid_log_error(np.asarray(before), np.asarray(ref))
        rows.append((case, eb, ea))
        triptych([before, after, ref], [f'改前  偏差 {eb:.3f}', f'改后  偏差 {ea:.3f}', 'Cycles 参考（同机位同灯光）'],
                 DOCS / f'cyclesgi_{case}.png')
    print(f'{"case":24s} {"改前":>8s} {"改后":>8s}')
    for c, eb, ea in rows:
        print(f'{c:24s} {eb:8.3f} {ea:8.3f} {"✔" if ea < eb else "✘"}')
    if rows:
        print(f'改后更接近参考：{sum(ea < eb for _, eb, ea in rows)}/{len(rows)}')

if __name__ == '__main__':
    main()
```

Run: `python3 -m unittest bake/tests/test_compare.py -v`
Expected: 2 个测试 PASS

- [ ] **Step 3: 调参入口 `__GI.tune`**

在"烘焙数据接入"段 GI 部分末尾（`warmUp` 之后）插入：

```js
  // 校准/对比用：bake/capture_views.mjs 经 CDP 调用。不改 UI，不进存档。
  const TUNE = { skyScale: null, fluoroGlow: 1, corrGlass: 1, contact: 1, moon: 1, winPatch: 1 };
  GI.tune = function (o = {}) {
    Object.assign(TUNE, o);
    if (TUNE.skyScale !== null) GI_SKY_SCALE = TUNE.skyScale;
    fluoroGlows.forEach(g => { g.visible = TUNE.fluoroGlow > 0; });
    corrLeak.glass.max = 0.35 * TUNE.corrGlass;
    contactMat.opacity = 0.85 * TUNE.contact;
    moonLight.visible = TUNE.moon > 0;                       // 改灯数 → 会重编一次着色器（只在校准时用）
    [...winPatches, ...winShafts].forEach(p => { p.visible = TUNE.winPatch > 0; });
    GI.lastWeights = null;                 // 强制下一帧重新合成
    return { ...TUNE, skyScale: GI_SKY_SCALE };
  };
```

- [ ] **Step 4: 同机位截图 + 灯光状态导出**

`bake/capture_views.mjs`：

```js
// 用法：node bake/capture_views.mjs [--tune '{"skyScale":0.5}'] [--only after]
// 为每个 case 拍 改后/改前 画布，并导出相机与灯光状态（供 blender_reference.py 渲参考图）
import { writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { launch, fileUrl } from './cdp.mjs';
import { HTML, OUT } from './tests/helpers.mjs';

const args = process.argv.slice(2);
const tune = args.includes('--tune') ? args[args.indexOf('--tune') + 1] : null;
const only = args.includes('--only') ? args[args.indexOf('--only') + 1] : null;
const VIEWS = join(OUT, 'views'); mkdirSync(VIEWS, { recursive: true });
const CORR = "{fov:70, theta:Math.PI, phi:0.02, camR:0.6, panX:7.95, panZ:4.0, panY:0.1, name:'走廊'}";
const CASES = [];
for (const p of ['morning', 'noon', 'dusk', 'night']) for (const v of ['5', '6', '7', '9']) CASES.push({ id: `${p}_${v}`, preset: p, view: `CAM_VIEWS['${v}']` });
CASES.push({ id: 'night_corr', preset: 'night', view: CORR }, { id: 'noon_corr', preset: 'noon', view: CORR });

const STATE = `(() => {
  const d = new THREE.Vector3().subVectors(mainLight.target.position, mainLight.position).normalize();
  const w = __GI.lastWeights || new Float32Array(39);
  return {
    camera: { position: camera.position.toArray(), quaternion: camera.quaternion.toArray(), fov: camera.fov, aspect: camera.aspect },
    exposure: renderer.toneMappingExposure,
    sky: [w[0], w[1], w[2]],
    sun: { dir: [d.x, d.y, d.z], intensity: mainLight.intensity, color: mainLight.color.toArray() },
    ceil: { positions: fluoroLights.map(l => l.getWorldPosition(new THREE.Vector3()).toArray()), intensity: fluoroLights[0].intensity, color: ceilColor.toArray() },
    corr: { positions: corrLampLights.map(l => l.getWorldPosition(new THREE.Vector3()).toArray()), intensity: corrLampLights[0].intensity, color: corrLampLights[0].color.toArray() },
  }; })()`;

async function run(path, tag) {
  const b = await launch();
  try {
    await b.goto(fileUrl(path));
    await b.waitFor("!window.__GI || (__GI.status !== 'pending' && __GI.texStatus !== 'pending')");
    if (tune && tag === 'after') await b.evaluate(`__GI.tune(${tune})`);
    for (const c of CASES) {
      await b.evaluate(`applyPreset('${c.preset}'); applyView(${c.view}); true`);
      await new Promise(r => setTimeout(r, 3500));          // 等吊顶灯/走廊灯/半球光的平滑过渡收敛
      await b.canvasPNG(join(VIEWS, `${c.id}_${tag}.png`));
      if (tag === 'after') writeFileSync(join(VIEWS, `${c.id}.json`), JSON.stringify(await b.evaluate(STATE)));
    }
  } finally { await b.close(); }
}
if (only !== 'before') await run(HTML, 'after');
if (only !== 'after') await run(join(OUT, 'before.html'), 'before');
console.log('ok', CASES.length, 'cases');
```

Run: `node bake/capture_views.mjs`
Expected: `ok 18 cases`；`bake/out/views/` 下 18 个 json、36 张 png。

- [ ] **Step 5: Cycles 参考图**

`bake/blender_reference.py`：

```python
"""按 capture_views 导出的相机与灯光状态渲染 Cycles 参考图（线性，存 .npy）。
用法：blender -b --factory-startup -P bake/blender_reference.py -- [--samples 256] [--only noon_7]"""
import sys, json, math, argparse
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import bpy
from mathutils import Quaternion, Vector
import blender_common as B

def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser(); ap.add_argument('--samples', type=int, default=256); ap.add_argument('--only', default='')
    a = ap.parse_args(argv)
    out = HERE / 'out'; views = out / 'views'
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = B.setup_cycles(a.samples)
    sc.cycles.use_denoising = True
    sc.view_settings.view_transform = 'Standard'          # 线性输出，色调映射在 compare.py 里按 three.js 做
    sc.render.resolution_x, sc.render.resolution_y = 960, 540
    sc.render.image_settings.file_format = 'OPEN_EXR'
    objs = B.import_glb(out / 'scene.glb'); B.kill_emission(objs); B.add_ground()
    cam_data = bpy.data.cameras.new('cam'); cam = bpy.data.objects.new('cam', cam_data)
    bpy.context.collection.objects.link(cam); sc.camera = cam
    for js in sorted(views.glob('*.json')):
        case = js.stem
        if a.only and case != a.only:
            continue
        st = json.loads(js.read_text())
        B.clear_lights()
        B.set_world(st['sky'], 1.0)                                       # 均匀天空亮度 = 运行时 SKY 组权重
        if st['sun']['intensity'] > 0 and st['sun']['dir'][1] < 0:
            B.add_sun(st['sun']['dir'], st['sun']['intensity'], tuple(st['sun']['color']))
        for i, p in enumerate(st['ceil']['positions']):
            if st['ceil']['intensity'] > 0:
                B.add_point(p, 4 * math.pi * st['ceil']['intensity'], color=tuple(st['ceil']['color']), name=f'c{i}')
        for i, p in enumerate(st['corr']['positions']):
            if st['corr']['intensity'] > 0:
                B.add_point(p, 4 * math.pi * st['corr']['intensity'], color=tuple(st['corr']['color']), name=f'r{i}')
        c = st['camera']
        cam.location = Vector(B.three_to_bl(c['position']).tolist())
        qx, qy, qz, qw = c['quaternion']
        # three → blender：先转到 Z 向上坐标系（绕 X 轴 +90°），相机朝向约定两者相同（看向自身 -Z）
        cam.rotation_mode = 'QUATERNION'
        cam.rotation_quaternion = Quaternion((math.cos(math.pi / 4), math.sin(math.pi / 4), 0, 0)) @ Quaternion((qw, qx, qy, qz))
        cam_data.sensor_fit = 'VERTICAL'; cam_data.angle_y = math.radians(c['fov'])
        cam_data.clip_start, cam_data.clip_end = 0.3, 80
        sc.render.resolution_y = int(round(960 / c['aspect']))
        exr = views / f'{case}_ref.exr'
        sc.render.filepath = str(exr)
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(str(exr))
        px = np.array(img.pixels[:], np.float32).reshape(img.size[1], img.size[0], 4)[::-1, :, :3]
        np.save(views / f'{case}_ref.npy', px); bpy.data.images.remove(img)
        print('REF', case, px.shape, float(px.mean()), flush=True)

main()
```

Run: `/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P bake/blender_reference.py -- --only noon_7 2>&1 | grep REF && python3 bake/compare.py`
Expected: `REF noon_7 …`；生成 `docs/superpowers/compare/cyclesgi_noon_7.png`。Read 查看：参考图与改后画面**机位、构图完全一致**（若不一致，修相机四元数换算：试 `Quaternion((math.cos(math.pi/4), math.sin(math.pi/4), 0, 0))` 改为左乘/右乘，直到桌子与黑板位置重合）。

确认机位一致后渲全部：
Run: `/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P bake/blender_reference.py 2>&1 | grep REF && python3 bake/compare.py`
Expected: 18 张三联图 + 表格；记录"改后更接近参考：x/18"。

- [ ] **Step 6: 校准天光尺度**

参考图的天空亮度取自 `__GI.lastWeights`，所以每档 skyScale 都要重拍改后 + 重渲参考，比较才公平。
对 `skyScale ∈ {0.5/π, 1/π, 2/π, 4/π}` 各跑一次（只渲白天 noon/morning 的机位 5、7 以省时间）：

```bash
for s in 0.159 0.318 0.637 1.273; do
  node bake/capture_views.mjs --only after --tune "{\"skyScale\":$s}" >/dev/null
  for c in morning_5 morning_7 noon_5 noon_7; do
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P bake/blender_reference.py -- --only $c >/dev/null 2>&1
  done
  python3 bake/compare.py | grep -E "^(morning|noon)_(5|7) " | sed "s/^/skyScale=$s  /"
  python3 -c "
from PIL import Image; import numpy as np
r=[np.asarray(Image.open(f'bake/out/views/{c}_after.png').convert('L')).mean()/np.asarray(Image.open(f'bake/out/views/{c}_before.png').convert('L')).mean() for c in ['morning_5','morning_7','noon_5','noon_7']]
print('  改后/改前 平均亮度比', [round(x,2) for x in r])"
done
```

选四个 case 偏差平均最小、且"改后/改前平均亮度比"在 0.8–1.25 的一档，写进 `let GI_SKY_SCALE = …`，然后用该值重跑 Step 4、Step 5 的全部 case 与 `compare.py`。

- [ ] **Step 7: 逐个评估假效果**

在选定的 skyScale 下，依次单独关闭：`{fluoroGlow:0}`（吊顶灯梯形光晕）、`{corrGlass:0}`（走廊窗玻璃自发光）、`{contact:0}`（桌下接触阴影贴片）、`{moon:0}`（无阴影的月光方向光，深夜 case 看）、`{winPatch:0}`（窗光斑/光柱贴片，清晨/傍晚 case 看），各跑一次：

```bash
for t in '{"fluoroGlow":0}' '{"corrGlass":0}' '{"contact":0}' '{"moon":0}' '{"winPatch":0}'; do
  node bake/capture_views.mjs --only after --tune "$t" >/dev/null && python3 bake/compare.py | tail -1 | sed "s/^/$t  /"
done
```

（这些开关不改变灯光状态里的 sky/sun/ceil/corr，参考图不用重渲。）偏差下降或持平 → 在 GI 激活时关闭该效果（写进 `removeFakeLights()`；月光若关闭，就在那里一并 `moonLight.removeFromParent()`，与拆灯同在加载期完成）；偏差上升 → 保留。把结果表追加到 spec 末尾"校准结果"小节。

- [ ] **Step 8: 回归 + Commit**

Run: `node --test bake/tests/*.test.mjs && python3 -m unittest discover -s bake/tests -p 'test_*.py'`
Expected: 全部 PASS

```bash
git add bake/capture_views.mjs bake/blender_reference.py bake/compare.py bake/tests/test_compare.py classroom_v4_3.html docs/superpowers/compare/cyclesgi_*.png docs/superpowers/specs/2026-10-11-cycles-baked-gi-materials-design.md
git commit -m "feat: Cycles 参考图三联对比 + 天光尺度与假效果校准

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: 帧率基准、一键重烘、文档、最终验收

**Files:**
- Create: `bake/bench.mjs`, `bake/run_all.sh`, `bake/README.md`
- Modify: `项目记录.md`, `性能优化计划.md`

**Interfaces:**
- Consumes: 全部前序产物。
- Produces: `bake/out/bench_before.json`、`bench_after.json`；`bake/run_all.sh [--quick]`。

- [ ] **Step 1: 帧率基准脚本**

`bake/bench.mjs`：

```js
// 用法：node bake/bench.mjs <html> <out.json>
// 与 性能优化计划.md 相同的方法：readPixels 强制同步，逐项计时单帧真实成本（ms/帧）
import { writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { launch, fileUrl } from './cdp.mjs';

const [html, outPath] = process.argv.slice(2);
const b = await launch({ width: 1600, height: 900 });
try {
  await b.goto(fileUrl(resolve(html)));
  await b.waitFor("!window.__GI || (__GI.status !== 'pending' && __GI.texStatus !== 'pending')");
  await new Promise(r => setTimeout(r, 1500));
  const res = await b.evaluate(`(async () => {
    const gl = renderer.getContext(), px = new Uint8Array(4);
    const sync = () => gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    const bench = (n, body) => { for (let i = 0; i < 3; i++) body(); sync(); const t0 = performance.now(); for (let i = 0; i < n; i++) body(); sync(); return (performance.now() - t0) / n; };
    const out = {};
    for (const p of ['morning', 'noon', 'dusk', 'night']) for (const v of ['5', '6', '7', '9', '0']) {
      applyPreset(p); applyView(CAM_VIEWS[v]);
      await new Promise(r => setTimeout(r, 400));
      const runs = [0, 1, 2].map(() => bench(15, () => { if (window.__GI && __GI.active) __GI.update(); composer.render(); }));
      out[p + '_' + v] = runs.sort((a, b) => a - b)[1];        // 三次取中位数
    }
    toggleMonitor(true); await new Promise(r => setTimeout(r, 400));
    out.monitor = [0, 1, 2].map(() => bench(15, () => renderMonitorWall())).sort((a, b) => a - b)[1];
    toggleMonitor(false);
    return out; })()`);
  writeFileSync(outPath, JSON.stringify(res, null, 1));
  console.log(Object.entries(res).map(([k, v]) => `${k.padEnd(12)} ${v.toFixed(2)} ms  ${(1000 / v).toFixed(0)} FPS`).join('\n'));
} finally { await b.close(); }
```

- [ ] **Step 2: 跑基准对比**

Run: `node bake/bench.mjs bake/out/before.html bake/out/bench_before.json && node bake/bench.mjs classroom_v4_3.html bake/out/bench_after.json && python3 -c "
import json; a=json.load(open('bake/out/bench_before.json')); b=json.load(open('bake/out/bench_after.json'))
bad=[k for k in a if b[k] > a[k]*1.05]
for k in a: print(f'{k:12s} {a[k]:6.2f} → {b[k]:6.2f} ms')
print('全部不慢于改前' if not bad else '变慢: '+', '.join(bad))"`
Expected: `全部不慢于改前`。若有变慢：先去掉课桌法线贴图（`deskMat.normalMap = null`，Task 2 加的）再测；仍慢则把木纹粗糙度贴图也去掉。每一步把数字记进 `性能优化计划.md`。

- [ ] **Step 3: 一键重烘脚本**

`bake/run_all.sh`：

```bash
#!/bin/zsh
# 一键重新生成全部烘焙数据并写入 classroom_v4_3.html。
# 用法：bake/run_all.sh          （完整：约 20–40 分钟，首次另加 ~2.5 分钟 Metal 内核编译）
#       bake/run_all.sh --quick  （64 采样快速版，几分钟，用于验证流程）
set -euo pipefail
cd "$(dirname "$0")/.."
BL=/Applications/Blender.app/Contents/MacOS/Blender
QUICK=()
[[ "${1:-}" == "--quick" ]] && QUICK=(--quick)
node bake/build_exporter.mjs
python3 bake/fetch_polyhaven.py
$BL -b --factory-startup -P bake/blender_floor.py
python3 bake/pack_textures.py
python3 bake/embed.py                       # 先写贴图：导出时反照率要用新贴图
node bake/export_scene.mjs
$BL -b --factory-startup -P bake/blender_gi.py -- "${QUICK[@]}"
python3 bake/pack_gi.py
python3 bake/embed.py
ls -la classroom_v4_3.html
```

Run: `chmod +x bake/run_all.sh && bake/run_all.sh --quick && node --test bake/tests/runtime_gi.test.mjs`
Expected: 流程跑通、测试 PASS。随后再跑一次完整版 `bake/run_all.sh`（恢复 1024 采样的正式数据）并重跑全部测试。

- [ ] **Step 4: 文档**

`bake/README.md`：说明各脚本职责（照抄本计划"文件结构"表）、`run_all.sh` 用法、何时需要重烘（改了房间几何、灯位、窗洞、主要材质反照率之后）、单位约定、Poly Haven 许可（CC0）。

`项目记录.md`：在"3. 已完成的修复与改动"最前面加一节 `2026-10-11 · Cycles 烘焙全局光照 + 材质升级`，写清：做了什么、拆掉了哪 11 盏灯、帧率前后数字（来自 bench）、三联图位置、校准结果、重烘方法；在"4. 已知情况 / 注意"加两条：①改几何/灯位后要 `bake/run_all.sh`；②`MeshStandardMaterial.prototype.onBeforeCompile` 已被 GI 占用，新增材质补丁要在 `giPatchFragment` 里叠加，不要覆盖原型钩子。

`性能优化计划.md`：追加"第三轮（2026-10-11）：烘焙 GI 替换 11 盏假补光"表格（每个 case 前后 ms/帧）。

- [ ] **Step 5: 最终验收**

Run: `node --test bake/tests/*.test.mjs && python3 -m unittest discover -s bake/tests -p 'test_*.py' && ls -la classroom_v4_3.html`
Expected: 全部 PASS；HTML ≤ 10MB。

再验 URL 复现链接与 DBG 调试工具在 GI 下仍可用：

```bash
node -e "
import('./bake/cdp.mjs').then(async ({launch, fileUrl}) => {
  const b = await launch();
  await b.goto(fileUrl(process.cwd() + '/classroom_v4_3.html', 'preset=dusk&theta=2.2&phi=0.14&camR=8.5&panX=-2&panZ=4&panY=0.3'));
  await b.waitFor(\"__GI.status !== 'pending'\");
  console.log('preset', await b.evaluate('giPresetKey'), 'GI', await b.evaluate('__GI.status'));
  await b.evaluate('DBG.id(); DBG.off(); DBG.uv(); DBG.off(); true');
  console.log('errors', b.logs.filter(l => /^(error|exception)/.test(l)));
  await b.close();
});"
```

Expected: `preset dusk GI active`、`errors []`。

用 Task 2 Step 13 的脚本拍最终 4 预设 × 机位 5/7/9 存到 `docs/superpowers/baselines/cyclesgi_after__*.png`，Read 逐张检查无黑斑/色带/漏光。

- [ ] **Step 6: Commit**

```bash
git add bake/bench.mjs bake/run_all.sh bake/README.md 项目记录.md 性能优化计划.md classroom_v4_3.html docs/superpowers/baselines/cyclesgi_after__*.png
git commit -m "feat: 帧率基准 + 一键重烘 + 文档（Cycles 烘焙 GI 与材质升级完成）

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: 收尾**

调用 `superpowers:finishing-a-development-branch`，由用户决定是否 `--no-ff` 合并回 main。
