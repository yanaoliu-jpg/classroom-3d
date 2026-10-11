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
