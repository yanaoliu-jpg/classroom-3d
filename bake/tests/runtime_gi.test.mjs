import { test } from 'node:test';
import assert from 'node:assert/strict';
import { launch, fileUrl } from '../cdp.mjs';
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { HTML, OUT, noDataCopy, errorsIn } from './helpers.mjs';

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

test('__GI.tune 改天光尺度并逐项关假效果（校准入口）', async () => {
  const b = await open(HTML);
  try {
    await b.evaluate(`applyPreset('noon'); applyView(CAM_VIEWS['5']); true`);
    await sleep(1500);
    const w0 = await b.evaluate('Array.from(__GI.lastWeights.slice(0, 3))');
    const s0 = (await b.evaluate('__GI.tune({})')).skyScale;          // 当前（校准后的）默认尺度
    const r = await b.evaluate(`__GI.tune({ skyScale: ${4 * s0}, fluoroGlow: 0, winPatch: 0, floorFx: 0 })`);
    assert.ok(Math.abs(r.skyScale - 4 * s0) < 1e-9);
    await sleep(500);                                       // 下一帧 GI.update 按新尺度重新合成
    const w1 = await b.evaluate('Array.from(__GI.lastWeights.slice(0, 3))');
    w1.forEach((v, i) => assert.ok(Math.abs(v / w0[i] - 4) < 1e-3, `天光权重应 ×4：${w0} → ${w1}`));
    assert.equal(await b.evaluate('fluoroGlows.some(g => g.visible) || winPatches.some(p => p.visible) || floorMirror.visible'), false);
    assert.deepEqual(errorsIn(b.logs), []);
  } finally { await b.close(); }
});

test('__GI.tune 关了再开，恢复页面自己的可见性（地面光斑创建时即隐藏，不能被"开"出来）', async () => {
  const b = await open(HTML);
  try {
    const vis = '[...fluoroGlows, ...winPatches, ...winShafts, floorMirror, floorHighlight, moonLight].map(o => o.visible)';
    const v0 = await b.evaluate(vis);
    assert.ok(v0.includes(false), '前提：页面里有被隐藏的假效果对象');
    await b.evaluate('__GI.tune({ fluoroGlow: 0, moon: 0, winPatch: 0, floorFx: 0 })');
    await b.evaluate('__GI.tune({ fluoroGlow: 1, moon: 1, winPatch: 1, floorFx: 1 })');
    assert.deepEqual(await b.evaluate(vis), v0);
  } finally { await b.close(); }
});

test('GI 生效：关掉校准判定冗余的假效果，保留接触阴影与月光；缺数据时原样', async () => {
  const fx = `({ glow: fluoroGlows.some(g => g.visible), glass: corrLeak.glass.max, patch: winPatches.some(p => p.visible),
    floor: floorMirror.visible || floorHighlight.visible, contact: contactMat.opacity, moon: !!moonLight.parent && moonLight.visible })`;
  const ref = await open(noDataCopy());
  try {
    assert.deepEqual(await ref.evaluate(fx), { glow: true, glass: 0.35, patch: true, floor: true, contact: 0.85, moon: true });
  } finally { await ref.close(); }
  const b = await open(HTML);
  try {
    assert.deepEqual(await b.evaluate(fx), { glow: false, glass: 0, patch: false, floor: false, contact: 0.85, moon: true });
    await b.evaluate('__GI.tune({})');                     // 调参入口不能把已关掉的假效果"开"回来
    assert.deepEqual(await b.evaluate(fx), { glow: false, glass: 0, patch: false, floor: false, contact: 0.85, moon: true });
  } finally { await b.close(); }
});

test('几何指纹：与当前几何一致时不警告；不一致时控制台警告、GI 照常', async () => {
  const b = await open(HTML);
  try {
    const fp = await b.evaluate('__GI.fingerprint()');
    assert.match(fp, /^[0-9a-f]{8}$/);
    assert.equal(await b.evaluate('BAKED.gi.meta.fingerprint'), fp);
    assert.equal(await b.evaluate('!!__GI.stale'), false);
    assert.ok(!b.logs.some(l => l.includes('烘焙数据与当前几何不一致')));
  } finally { await b.close(); }
  const stale = join(OUT, 'stale.html');
  writeFileSync(stale, readFileSync(HTML, 'utf8').replace(/"fingerprint":"[0-9a-f]{8}"/, '"fingerprint":"00000000"'));
  const c = await open(stale);
  try {
    assert.equal(await c.evaluate('__GI.status'), 'active');
    assert.equal(await c.evaluate('__GI.stale'), true);
    assert.ok(c.logs.some(l => l.startsWith('warning') && l.includes('烘焙数据与当前几何不一致')), c.logs.join('\n'));
  } finally { await c.close(); }
});
