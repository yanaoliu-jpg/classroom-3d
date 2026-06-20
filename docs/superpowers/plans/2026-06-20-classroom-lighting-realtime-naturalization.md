# classroom_v4_3 实时光影自然化（第一轮）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `classroom_v4_3.html` 从内联 Three.js r128 升级到 r0.164.x，加入窗户面光源（RectAreaLight）、GTAO、假反弹补光与接地阴影，使室内光影更接近物理自然，同时保持单文件、离线可双击运行。

**Architecture:** 用 esbuild 将 `three` + 所需 addons 打成单个 IIFE 包，内联进 html 替换原 r128 压缩块（保留 app 代码用全局 `THREE`，改动最小）。迁移分步推进：先在 `useLegacyLights=true` 下复刻现状（隔离颜色管理迁移风险），逐步加 GTAO → 窗面光 → 假反弹 → 接地阴影，最后翻到物理单位重平衡。每步用 headless Chrome（`/tmp/cls-verify/` puppeteer harness）出固定相机截图 + 爆白像素统计 + 与上一步 diff 来定位影响。

**Tech Stack:** Three.js r0.164.x（IIFE bundle via esbuild）、EffectComposer/RenderPass/GTAOPass/OutputPass、RectAreaLight(+UniformsLib)、puppeteer-core + pngjs + ImageMagick 验证。

---

## 关键约束与事实（执行者必读）

- 目标文件唯一：`/Users/liuyanao/Desktop/修复/classroom_v4_3.html`（~816KB，4019 行；行 246 是整段压缩的 r128，行号 251 起是 app 代码）。
- **app 代码用全局 `THREE`**（`new THREE.WebGLRenderer(...)` 等），且依赖大量**全局变量/函数**（`theta/phi/camR/panX/panZ/panY`、`renderer`、`scene`、`camera`、`applyPreset`、`corrCtl`、`DBG` 等）。harness 与调试工具靠这些是全局。**不要把 app 代码包进函数/模块作用域**，否则 DBG 与验证全断。
- 因此 three 必须以**设置 `window.THREE` 的经典脚本**形式提供（IIFE），不能用 ESM/importmap（ESM 会强制模块作用域，且 `file://` 下 import 受限）。
- 版本 pin **`three@0.164.1`**：最后一个保留 `renderer.useLegacyLights` 的版本（r165 移除）。用它在步骤 1 先维持旧灯光行为，把"颜色管理迁移"和"灯光物理化"两个风险源分离。GTAOPass(≥r148)/OutputPass(≥r152)/RectAreaLightUniformsLib 均可用。
- 验证 harness 目录：`/tmp/cls-verify/`（已装 `puppeteer-core@^25`、`pngjs@^7`）。Chrome：`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`。`magick`/`compare` 可用（ImageMagick 7）。
- **harness 陷阱**：设完相机全局后必须调用 `updateCam()`（仅输入事件触发，不在渲染循环里）；headless 截图**不要**传 `--virtual-time-budget`（会挂）；每次 run 用独立 `--user-data-dir`；截图前 `setTimeout` 等渲染稳定。
- 当前渲染细节：行 251 `new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true})`；行 258 `shadowMap.enabled=true`；259 `PCFSoftShadowMap`；260 `ACESFilmicToneMapping`；261 `toneMappingExposure=0.50`；262 `outputEncoding=sRGBEncoding`。有 `SUPERSAMPLE` 常量驱动 `setPixelRatio` 做 SSAA。`preserveDrawingBuffer` 必须保留（截图依赖）。
- 灯光（13 盏，行号）：725 `winSpot`(SpotLight)、1361 `corridorLight`(PointLight)、3041 `ambientLight`(0x2a3848,0.06)、3046 `hemiLight`(0xbcdcff,0xc8b898,0.30)、3053 `mainLight`(DirectionalLight 0xfff5e0,1.8 太阳)、3106/3109 `flouroLight1/2`(PointLight)、3119 `fill`(SpotLight)、3134/3148 `b`(SpotLight)、3159 `moonLight`(DirectionalLight)。
- 窗洞参数：右墙高窗 `WIN_CZ=3.0`、`RWIN_W=1.5`、`WIN_YB=2.30`、`WIN_YT=3.28`（行 617-618）；左墙窗在行 608 附近（`// Left wall (with windows)`）。`RW`/`RD`/`RH=3.5` 为房间尺寸常量。
- **本仓库当前不是 git 仓库**——Task 0 会 `git init` 以获得提交/回滚能力（高风险迁移必需）。
- envGate/preset 模型（见 [[classroom-lighting-plan-status]]）：ambient 故意接近 0 的冷蓝、由总光量 gate；暖意来自 `mainLight`+`hemiLight`+窗/顶/地反弹 spot。**改 ambient/hemi 时不要破坏 envGate**。

---

## File Structure

- `classroom_v4_3.html` — 唯一交付物（修改）。
- `vendor/three-bundle-entry.mjs` —（新建，构建用，不内联）esbuild 入口，import three + addons 并挂到 `window.THREE`。
- `vendor/three-bundle.iife.js` —（新建，构建产物）内联进 html 的单文件 IIFE。
- `vendor/package.json` / `vendor/node_modules/` —（新建，构建用）`three@0.164.1` + `esbuild`。
- `/tmp/cls-verify/views.js` —（新建）固定相机视角表。
- `/tmp/cls-verify/verify.js` —（新建）单次渲染：捕获 pageerror/console、截图、爆白统计、退出码。
- `/tmp/cls-verify/diff.js` —（新建）两张 png 的 RMSE + 差异图（pngjs）。
- `docs/superpowers/baselines/` —（新建）基线与各步截图归档。

---

## Task 0: 仓库初始化 + 验证 harness + 基线截图

**Files:**
- Create: `.gitignore`
- Create: `/tmp/cls-verify/views.js`, `/tmp/cls-verify/verify.js`, `/tmp/cls-verify/diff.js`
- Create: `docs/superpowers/baselines/` (截图输出)

- [ ] **Step 1: git init 并提交当前状态**

```bash
cd "/Users/liuyanao/Desktop/修复"
git init
printf '%s\n' 'vendor/node_modules/' '*.tmp' '.DS_Store' > .gitignore
git add -A
git commit -m "chore: snapshot baseline before lighting r164 migration

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

Expected: 一个初始提交，包含现有 html + spec/plan。

- [ ] **Step 2: 写固定相机视角表 `views.js`**

复用 [[classroom-debug-tooling]] 里的有用视角。

```js
// /tmp/cls-verify/views.js
module.exports = {
  // name: {preset, theta,phi,camR,panX,panZ,panY}
  interior_rightwin: { preset:'morning', theta:-1.5708, phi:0.02, camR:7,   panX:7, panZ:3,   panY:1.2 },
  outside_rightwall: { preset:'morning', theta:1.5708,  phi:0.06, camR:3.5, panX:7, panZ:3,   panY:1.5 },
  floor_pool:        { preset:'morning', theta:-1.30,   phi:0.32, camR:7,   panX:4, panZ:2.8, panY:1.0 },
  overview:          { preset:'noon',    theta:0.9,     phi:0.18, camR:12,  panX:0, panZ:3,   panY:1.6 },
  dusk_overview:     { preset:'dusk',    theta:0.9,     phi:0.18, camR:12,  panX:0, panZ:3,   panY:1.6 },
  night_overview:    { preset:'night',   theta:0.9,     phi:0.18, camR:12,  panX:0, panZ:3,   panY:1.6 },
};
```

- [ ] **Step 3: 写 `verify.js`（单次渲染 + 统计 + 退出码）**

```js
// /tmp/cls-verify/verify.js
// 用法: node verify.js <viewName> <outTag>
// 例:   node verify.js interior_rightwin baseline
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');
const VIEWS = require('./views.js');
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const FILE = 'file://' + path.resolve('/Users/liuyanao/Desktop/修复/classroom_v4_3.html');
const OUTDIR = '/Users/liuyanao/Desktop/修复/docs/superpowers/baselines';
const viewName = process.argv[2];
const tag = process.argv[3] || 'out';
const v = VIEWS[viewName];
if (!v) { console.error('unknown view', viewName, 'known:', Object.keys(VIEWS).join(',')); process.exit(2); }
fs.mkdirSync(OUTDIR, { recursive: true });

(async () => {
  const errors = [];
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new',
    args: ['--use-gl=angle','--use-angle=metal','--enable-webgl','--ignore-gpu-blocklist','--window-size=1280,800'],
    defaultViewport: { width: 1280, height: 800 },
  });
  const page = await browser.newPage();
  page.on('pageerror', e => errors.push('PAGEERR ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE ' + m.text()); });
  await page.goto(FILE, { waitUntil: 'load' });
  await new Promise(r => setTimeout(r, 1500));

  await page.evaluate((v) => {
    applyPreset(v.preset);
    theta=v.theta; phi=v.phi; camR=v.camR; panX=v.panX; panZ=v.panZ; panY=v.panY;
    updateCam();            // 关键：不调则相机不动（见 flicker memory）
  }, v);
  await new Promise(r => setTimeout(r, 2500)); // 等渲染/曝光适应稳定

  const out = `${OUTDIR}/${viewName}__${tag}.png`;
  await page.screenshot({ path: out });

  // 爆白/亮度统计（从 webgl canvas 取样）
  const stats = await page.evaluate(() => {
    const W=320,H=200; const c=document.createElement('canvas'); c.width=W;c.height=H;
    const ctx=c.getContext('2d',{willReadFrequently:true});
    ctx.drawImage(renderer.domElement,0,0,W,H);
    const d=ctx.getImageData(0,0,W,H).data; let white=0,bright=0,sum=0,n=W*H;
    for(let i=0;i<d.length;i+=4){const l=0.2126*d[i]+0.7152*d[i+1]+0.0722*d[i+2];sum+=l;if(l>=250)white++;if(l>=200)bright++;}
    return {meanLum:+(sum/n).toFixed(1), clippedWhitePct:+(100*white/n).toFixed(2), brightPct:+(100*bright/n).toFixed(2)};
  });
  console.log(JSON.stringify({view:viewName, tag, out, errors, stats}, null, 0));
  await browser.close();
  process.exit(errors.length ? 1 : 0);   // 有 JS 报错=非零退出（迁移冒烟）
})();
```

- [ ] **Step 4: 写 `diff.js`（两图 RMSE + 差异图）**

```js
// /tmp/cls-verify/diff.js
// 用法: node diff.js <a.png> <b.png> <diffOut.png>
const fs = require('fs'); const { PNG } = require('pngjs');
const [a,b,outp] = process.argv.slice(2);
const A = PNG.sync.read(fs.readFileSync(a));
const B = PNG.sync.read(fs.readFileSync(b));
if (A.width!==B.width || A.height!==B.height) { console.error('size mismatch'); process.exit(2); }
const out = new PNG({width:A.width,height:A.height});
let sq=0, n=A.width*A.height;
for (let i=0;i<A.data.length;i+=4){
  let d2=0; for(let k=0;k<3;k++){const dd=A.data[i+k]-B.data[i+k]; d2+=dd*dd;}
  sq += d2/3;
  const g=Math.min(255, Math.sqrt(d2/3)*3);
  out.data[i]=g; out.data[i+1]=g*0.4; out.data[i+2]=30; out.data[i+3]=255;
}
fs.writeFileSync(outp, PNG.sync.write(out));
console.log(JSON.stringify({rmse:+Math.sqrt(sq/n).toFixed(2), diffImg:outp}));
```

- [ ] **Step 5: 采集基线截图（6 个视角）**

```bash
cd /tmp/cls-verify
for V in interior_rightwin outside_rightwall floor_pool overview dusk_overview night_overview; do
  node verify.js "$V" baseline
done
```

Expected: 每个输出 JSON 的 `errors` 为 `[]`，`docs/superpowers/baselines/<view>__baseline.png` 生成。记录每个的 `stats`（后续比对基准）。

- [ ] **Step 6: 提交基线**

```bash
cd "/Users/liuyanao/Desktop/修复"
git add -A && git commit -m "test: add headless verify harness + baseline screenshots

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 1: 迁移到 three@0.164.1（IIFE 内联），先复刻现状

目标：把 r128 换成 r164，画面**尽量等于基线**。靠 `useLegacyLights=true` 维持旧灯光行为，只吸收颜色管理 + 渲染管线（EffectComposer）变更。

**Files:**
- Create: `vendor/three-bundle-entry.mjs`, `vendor/package.json`
- Build: `vendor/three-bundle.iife.js`
- Modify: `classroom_v4_3.html`（行 246 的 r128 块；行 251、258-262 渲染器配置；新增 composer）

- [ ] **Step 1: 建构建入口与依赖**

```bash
cd "/Users/liuyanao/Desktop/修复"
mkdir -p vendor && cd vendor
cat > package.json <<'JSON'
{ "name":"three-vendor", "private":true, "version":"1.0.0" }
JSON
npm i three@0.164.1 esbuild@0.21.5
```

```js
// vendor/three-bundle-entry.mjs
import * as THREE from 'three';
import { RectAreaLightUniformsLib } from 'three/examples/jsm/lights/RectAreaLightUniformsLib.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/examples/jsm/postprocessing/GTAOPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
Object.assign(THREE, { RectAreaLightUniformsLib, EffectComposer, RenderPass, GTAOPass, OutputPass });
window.THREE = THREE;
```

- [ ] **Step 2: 打 IIFE 包**

```bash
cd "/Users/liuyanao/Desktop/修复/vendor"
npx esbuild three-bundle-entry.mjs --bundle --format=iife --minify --legal-comments=none --outfile=three-bundle.iife.js
ls -la three-bundle.iife.js
```

Expected: 生成 `three-bundle.iife.js`（约 1–1.5MB）。

- [ ] **Step 3: 用包内容替换 html 行 246 的 r128 块**

定位：`classroom_v4_3.html` 行 246 是 `!function(t,e){"object"==typeof exports...THREE={})}` 开头的整段（一行）。把**整行**替换为 `vendor/three-bundle.iife.js` 的全部内容（仍是一个 `<script>...</script>` 内的脚本体——保持它在原来的 `<script>` 标签里）。

执行方式（避免手抄百万字符）：

```bash
cd "/Users/liuyanao/Desktop/修复"
node -e '
const fs=require("fs");
const html=fs.readFileSync("classroom_v4_3.html","utf8").split("\n");
const bundle=fs.readFileSync("vendor/three-bundle.iife.js","utf8");
// 行号从 0 开始：246 行 → index 245
html[245]=bundle;
fs.writeFileSync("classroom_v4_3.html", html.join("\n"));
console.log("replaced line 246, new size", fs.statSync("classroom_v4_3.html").size);
'
```

注意：替换前确认 index 245 确实是 r128 块（`grep -n 'THREE={})}(this' classroom_v4_3.html` 应指向它）。若行号漂移，按该 grep 命中的行号调整。

- [ ] **Step 4: 修渲染器配置 + 引入 composer**

在 `classroom_v4_3.html` 找到渲染器配置块（原行 251、258-262），改为：

```js
const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
// ...原 setSize/setPixelRatio 保留...
renderer.useLegacyLights = true;               // 迁移期：维持 r128 灯光行为，隔离风险
renderer.shadowMap.enabled=true;
renderer.shadowMap.type=THREE.PCFSoftShadowMap;
renderer.toneMapping=THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure=0.50;
renderer.outputColorSpace=THREE.SRGBColorSpace; // 取代 outputEncoding=sRGBEncoding
```

在 `scene`、`camera` 创建之后、渲染循环之前，新增 composer（找到 `new THREE.Scene()` 与渲染循环 `renderer.render(scene,camera)` 的位置）：

```js
// ---- post-processing composer ----
const composer = new THREE.EffectComposer(renderer, new THREE.WebGLRenderTarget(
  innerWidth, innerHeight, { type: THREE.HalfFloatType }   // 线性中间缓冲，防 banding
));
composer.setPixelRatio(renderer.getPixelRatio()); // 与 renderer 一致（SSAA 已含在 pixelRatioCap=min(dpr*1.5,4) 里）
composer.setSize(innerWidth, innerHeight);
const renderPass = new THREE.RenderPass(scene, camera);
const outputPass = new THREE.OutputPass();        // 末端做 ACES tonemap + sRGB
composer.addPass(renderPass);
composer.addPass(outputPass);
```

把渲染循环里的 `renderer.render(scene,camera)` 改为 `composer.render()`。
在 resize 处理里，给 composer 同步：`composer.setSize(innerWidth,innerHeight); composer.setPixelRatio(renderer.getPixelRatio());`。
若仍存在 [[classroom-flicker-investigation]] 提到的 `ssaoPass.setSize` 残留，删除之。

- [ ] **Step 5: 修贴图 colorSpace（17 个 CanvasTexture + 颜色贴图）**

颜色用途的 `CanvasTexture`/贴图需 `.colorSpace=THREE.SRGBColorSpace`；法线/粗糙度/AO 等**数据贴图保持线性**（不设）。

定位所有颜色贴图创建处（`grep -nE 'new THREE.CanvasTexture|TextureLoader|floorTex|wallTex' classroom_v4_3.html`）。对每个**颜色**贴图追加：

```js
someColorTex.colorSpace = THREE.SRGBColorSpace;
```

数据贴图（命名含 `Normal`/`Rough`/`rough`/`normal`/`ao`）**不要**设。逐个核对，避免把法线图当 sRGB（会发蓝/变暗）。

- [ ] **Step 6: 跑迁移冒烟（无报错）**

```bash
cd /tmp/cls-verify && node verify.js overview migrate1
```

Expected: 退出码 0，`errors:[]`（无 `THREE is undefined`/`RectAreaLightUniformsLib`/API 报错）。若非零，读 `errors` 修对应 API（常见：`outputEncoding` 残留、`sRGBEncoding` 常量、`Geometry`/`Face3` 等已移除 API）。

- [ ] **Step 7: 与基线逐视角比对**

```bash
cd /tmp/cls-verify
B=/Users/liuyanao/Desktop/修复/docs/superpowers/baselines
for V in interior_rightwin outside_rightwall floor_pool overview dusk_overview night_overview; do
  node verify.js "$V" migrate1
  node diff.js "$B/${V}__baseline.png" "$B/${V}__migrate1.png" "/tmp/cls-verify/diff_${V}_m1.png"
done
```

Expected：构图/可读性无明显倒退。颜色管理切换会带来轻微整体差异（可接受），但不应出现**整片变暗/变蓝/爆白/丢面**。RMSE 作参考，不设硬阈值；用差异图人工确认。若某视角严重偏色，多半是 Step 5 漏标或错标 colorSpace。

- [ ] **Step 8: 提交**

```bash
cd "/Users/liuyanao/Desktop/修复"
git add -A
git commit -m "feat: migrate Three.js r128 -> r164 (IIFE bundle) + EffectComposer; replicate baseline

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: 加 GTAO

**Files:** Modify `classroom_v4_3.html`（composer 段）

- [ ] **Step 1: 插入 GTAOPass（在 RenderPass 之后、OutputPass 之前）**

```js
const gtaoPass = new THREE.GTAOPass(scene, camera, innerWidth, innerHeight);
// 房间尺度参数（RW×RD×RH=3.5）；起始值，后续按截图调
gtaoPass.output = THREE.GTAOPass.OUTPUT.Default;
const gtaoParams = {
  radius: 0.5, distanceExponent: 1.0, thickness: 1.0, scale: 1.0,
  samples: 16, distanceFallOff: 1.0, screenSpaceRadius: false,
};
gtaoPass.updateGtaoMaterial(gtaoParams);
// 插到 outputPass 前
composer.insertPass(gtaoPass, 1);
```

resize 处理里加 `gtaoPass.setSize(innerWidth, innerHeight)`。

- [ ] **Step 2: 渲一张只看 AO 贡献**

临时把 `gtaoPass.output = THREE.GTAOPass.OUTPUT.AO;` 渲一张，确认 AO 出现在墙角/桌椅接触/物体根部，且无大面积黑斑或 haloing。

```bash
cd /tmp/cls-verify && node verify.js overview gtao_aoonly
```

看 `docs/superpowers/baselines/overview__gtao_aoonly.png`：接触处应变暗、平坦处接近白。若整屏发黑→`radius` 太大或法线/深度异常，调小 `radius`（0.2–0.5）。

- [ ] **Step 3: 调参，恢复 Default 输出，全视角比对**

把 `gtaoPass.output` 改回 `Default`，按上图调 `radius/scale/thickness` 到“接触阴影自然、无 halo、无满屏发灰”。

```bash
cd /tmp/cls-verify
for V in interior_rightwin floor_pool overview; do node verify.js "$V" gtao; \
  node diff.js "/Users/liuyanao/Desktop/修复/docs/superpowers/baselines/${V}__migrate1.png" \
               "/Users/liuyanao/Desktop/修复/docs/superpowers/baselines/${V}__gtao.png" \
               "/tmp/cls-verify/diff_${V}_gtao.png"; done
```

Expected：差异集中在墙角/接触/缝隙的变暗，墙面/地面大平面基本不变。`errors:[]`。

- [ ] **Step 4: 提交**

```bash
cd "/Users/liuyanao/Desktop/修复"
git add -A && git commit -m "feat: add GTAO pass for contact occlusion

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 窗户面光源（RectAreaLight）

**重要事实**：场景里**只有右墙高窗是真窗**（窗框 699-708、玻璃 717-720、走廊在外、`winSpot` 行 725 已在模拟漏光）。左墙（609-611）是**实心墙**，注释 "(with windows)" 已过时——**不要给左墙加面光**。本任务只在右墙窗加一块 RectAreaLight，作为对 `winSpot`（点状聚光）更柔和的面光补充。

**Files:** Modify `classroom_v4_3.html`（renderer 创建后加 init；窗光建在 winSpot 附近 ~725）

- [ ] **Step 1: 初始化 UniformsLib（renderer 创建后、建任何 RectAreaLight 前调一次）**

```js
THREE.RectAreaLightUniformsLib.init();
```

- [ ] **Step 2: 右墙高窗加面光（朝室内 -x 方向）**

已知常量：`RW=14`、`RWIN_W=1.5`、`WIN_CZ=3.0`、`WIN_YB=2.30`、`WIN_YT=3.28`。窗高 `0.98`、竖向中心 `2.79`、窗面 x≈`RW/2=7`。在 `winSpot`（行 725-730）之后新增：

```js
THREE.RectAreaLightUniformsLib.init(); // 若已在 Step1 调过则略
const rWin = new THREE.RectAreaLight(0xdfe8f5 /*偏冷天光; step6 随 preset 调*/, 4.0, RWIN_W, WIN_YT - WIN_YB);
rWin.position.set(RW/2 - 0.05, (WIN_YB + WIN_YT)/2, WIN_CZ); // 窗洞内侧
rWin.lookAt(RW/2 - 2.0, (WIN_YB + WIN_YT)/2, WIN_CZ);        // 法线指向室内 -x
scene.add(rWin);
window.rWin = rWin;            // 暴露全局便于 step6 调参/接 preset/envGate
```

注意：RectAreaLight 不投影、只对 `MeshStandard/MeshPhysicalMaterial` 生效。它与 `winSpot` 同位但作用互补（面光给柔和过渡、spot 给方向感）——若叠加后过亮，step4 里下调 `rWin.intensity` 或 `corrLeak.spot.max`。

- [ ] **Step 3: 接入 corrLeak（随走廊灯开关/preset 缩放）**

`corrLeak` 控制入窗光效随 `corrCtl` 渐变（行 656-658、744 附近，render 循环里 lerp）。把 `rWin` 也纳入，使它随窗光开关/preset 缩放，而不是恒亮：

```js
corrLeak.rect = { light: rWin, max: 4.0 };  // 在 render 循环里随 corrCtl.cur 把 light.intensity = max*cur（仿照 corrLeak.spot 的处理）
```

定位 render 循环里处理 `corrLeak.spot.light.intensity` 的那行，仿照它对 `corrLeak.rect.light.intensity` 做同样的 lerp/缩放。

- [ ] **Step 4: 验证窗光柔和、不爆白**

```bash
cd /tmp/cls-verify
B=/Users/liuyanao/Desktop/修复/docs/superpowers/baselines
for V in interior_rightwin outside_rightwall floor_pool; do node verify.js "$V" rect; \
  node diff.js "$B/${V}__gtao.png" "$B/${V}__rect.png" "/tmp/cls-verify/diff_${V}_rect.png"; done
```

Expected：右墙窗附近墙/地出现柔和面光过渡（比纯 `winSpot` 更软）；`clippedWhitePct` 不显著上升（若上升，调低 `rWin.intensity` 4.0→2–3 或 `corrLeak.spot.max`）。`MeshBasic` 的玻璃/光斑不受 RectAreaLight 影响，属正常。

- [ ] **Step 5: 提交**

```bash
cd "/Users/liuyanao/Desktop/修复"
git add -A && git commit -m "feat: add RectAreaLight window panels (soft area window light)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 假反弹补光 + 重调 hemi/ambient

**Files:** Modify `classroom_v4_3.html`（行 3041 ambient、3046 hemi）

- [ ] **Step 1: 加“地面→上”暖反弹补光**

模拟地面把暖光反弹到桌底/天花板。用一盏宽角、向上的低强度补光（不投影）：

```js
// 地面暖反弹（朝上）
const bounceUp = new THREE.HemisphereLight(0xd8c6a6 /*地面暖*/, 0x000000, 0.0);
// 用第二个 Hemisphere 充当“地反弹”：天空色=地面反照暖色，地面色=黑
bounceUp.position.set(0, 0.1, 3);
scene.add(bounceUp);
window.bounceUp = bounceUp;
```

说明：现有 `hemiLight`(行3046, sky=0xbcdcff 冷, ground=0xc8b898 暖, 0.30) 已是天/地双色补光。**优先重调它**而不是叠太多新灯——把它视作主反弹项。`bounceUp` 仅在重调后仍偏硬时启用（默认 intensity 0，step3 决定是否开）。

- [ ] **Step 2: 重调 hemi/ambient（保持 envGate 不破）**

按 [[classroom-lighting-plan-status]]：ambient 故意冷蓝近 0、由 envGate 控；不要直接把 ambient 设大。微调范围：`hemiLight.intensity` 0.30→可上探 0.45 增加柔和填充；`ambientLight` 维持低值。改动写在原行（3041/3046）。

- [ ] **Step 3: 全视角 + 全 preset 验证**

```bash
cd /tmp/cls-verify
for V in interior_rightwin floor_pool overview dusk_overview night_overview; do
  node verify.js "$V" bounce; \
  node diff.js "/Users/liuyanao/Desktop/修复/docs/superpowers/baselines/${V}__rect.png" \
               "/Users/liuyanao/Desktop/修复/docs/superpowers/baselines/${V}__bounce.png" \
               "/tmp/cls-verify/diff_${V}_bounce.png"; done
```

Expected：暗部（桌底、天花板、墙根上方）柔和提亮，但 `night_overview` 不应被补光“点亮”破坏夜景（envGate 应压住）。若夜景被提亮 → 把新增补光也纳入 envGate 的总光量计算/随 preset 缩放。

- [ ] **Step 4: 提交**

```bash
cd "/Users/liuyanao/Desktop/修复"
git add -A && git commit -m "feat: bounce fill light + retuned hemisphere fill (respecting envGate)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 接地阴影 / 收紧 shadow-map

**现状（不要盲目覆盖）**：`mainLight`（行 3053-3065）已精调：4096 map、frustum `left/right=-16/16`、`top/bottom=22/-22`、`near=0.5 far=55`、`bias=-0.0006`、`normalBias=0.022`、`radius=5`。接触阴影**主要由 Task 2 的 GTAO 承担**；本任务只做小幅微调让物体“踩实”地面，**从现有值出发增量调**，不要整段替换。

**Files:** Modify `classroom_v4_3.html`（`mainLight.shadow.*`，行 3057-3064）

- [ ] **Step 1: 微调 bias 与 radius（从现有值增量）**

```js
// 现有: bias=-0.0006 normalBias=0.022 radius=5
mainLight.shadow.bias = -0.0004;     // 略收，减少接触处漏光/悬浮；过小→acne 条纹
mainLight.shadow.normalBias = 0.018; // 略收
mainLight.shadow.radius = 3;         // 5→3：接触带更实、不过度发糊（远处仍软）
```

可选：若 overview 下阴影分辨率不足，再把 frustum 从 ±16/±22 收向房间实际范围（RW=14→half 7、RD=22→half 11），但**一次只改一项并截图比对**，确认不裁掉任何物体的影子。

- [ ] **Step 2: 验证接触实、无 acne/peter-panning**

```bash
cd /tmp/cls-verify
for V in floor_pool overview; do node verify.js "$V" contact; \
  node diff.js "/Users/liuyanao/Desktop/修复/docs/superpowers/baselines/${V}__bounce.png" \
               "/Users/liuyanao/Desktop/修复/docs/superpowers/baselines/${V}__contact.png" \
               "/tmp/cls-verify/diff_${V}_contact.png"; done
```

可用 `magick` 放大桌椅腿与地面接触处人工核对：

```bash
magick "/Users/liuyanao/Desktop/修复/docs/superpowers/baselines/overview__contact.png" -crop 400x300+440+420 +repage /tmp/cls-verify/contact_zoom.png
```

Expected：桌椅腿/物体根部与地面接触处有实在的暗接触带，无悬浮感、无条纹 acne。

- [ ] **Step 3: 提交**

```bash
cd "/Users/liuyanao/Desktop/修复"
git add -A && git commit -m "feat: tighten shadow-map bias/frustum for grounded contact shadows

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: 翻到物理单位 + 最终重平衡

目标：关闭 `useLegacyLights`，让灯光物理正确，按“物理自然优先”整体重平衡。允许整体色调/亮度变化。

**Files:** Modify `classroom_v4_3.html`（渲染器配置、全部 13 盏灯 + 新增灯强度、exposure）

- [ ] **Step 1: 关闭 legacy lights，先看“破坏”有多大**

```js
renderer.useLegacyLights = false;   // 物理正确：point/spot 强度变暗
```

```bash
cd /tmp/cls-verify && node verify.js overview phys_raw
```

Expected：point/spot 照亮区域明显变暗（物理单位差异）。记录 `meanLum` 跌幅。

- [ ] **Step 2: 重标定 point/spot 强度**

`useLegacyLights=false` 后，PointLight/SpotLight 需上调以补回能量（DirectionalLight/Ambient/Hemisphere 受影响小）。对每盏 PointLight/SpotLight（行 725/1361/3106/3109/3119/3134/3148）按需乘一个起始系数（建议从 ×Math.PI≈3.14 起，按截图收敛），不要照搬常数——以 `floor_pool`/`overview` 的 `meanLum` 接近 Task5(`__contact`) 水平为准。RectAreaLight（Task3）单位本就物理，微调即可。

逐盏调 → 每次：

```bash
cd /tmp/cls-verify && node verify.js overview phys_tune && node verify.js floor_pool phys_tune
```

直到亮度/对比回到自然水平。

- [ ] **Step 3: 物理自然方向的最终曝光/色温整体收一遍**

按“物理自然优先”允许偏离旧氛围：调 `toneMappingExposure`（0.50 起，可上下探）、各 preset 的暖冷，使窗光柔、暗部通透、无爆白。改 `applyPreset` 时确保 RectAreaLight（`rWin/lWin`）、`bounceUp` 也随 preset 缩放（接入 envGate）。

- [ ] **Step 4: 全视角 + 全 preset 终验 + 与基线总对比**

```bash
cd /tmp/cls-verify
for V in interior_rightwin outside_rightwall floor_pool overview dusk_overview night_overview; do
  node verify.js "$V" final; \
  node diff.js "/Users/liuyanao/Desktop/修复/docs/superpowers/baselines/${V}__baseline.png" \
               "/Users/liuyanao/Desktop/修复/docs/superpowers/baselines/${V}__final.png" \
               "/tmp/cls-verify/diff_${V}_final.png"; done
```

Expected：所有视角 `errors:[]`；相对基线——窗光更柔、接触阴影更自然、整体更物理（允许色调/亮度变化）；无爆白（`clippedWhitePct` 不应高于基线很多）；夜景仍暗（envGate 未破）。

- [ ] **Step 5: 人工总览（用户确认）**

把 6 张 `__baseline` 与 `__final` 并排给用户看，确认“物理自然优先”达标后再收尾。

- [ ] **Step 6: 提交**

```bash
cd "/Users/liuyanao/Desktop/修复"
git add -A && git commit -m "feat: switch to physically-correct lights + final natural rebalance

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## 收尾检查清单

- [ ] 单文件 `classroom_v4_3.html` 双击离线可运行（Chrome 直接打开 file://，无控制台报错）。
- [ ] 6 视角 `verify.js` 全部退出码 0。
- [ ] `vendor/` 仅为构建用（已在 .gitignore 忽略 node_modules）；交付物仍是单 html。
- [ ] DBG 工具（U/I/O/H、`DBG.setView`、URL-hash 相机）仍工作（全局未被破坏）。
- [ ] 灰尘粒子/preset/envGate/漫游（WASD+鼠标）行为未回归。

## 范围外（本轮不做）

真·实时 GI（SSGI/irradiance volume/路径追踪）、烘焙 lightMap、高级 contact-shadow buffer、多文件工程化。
