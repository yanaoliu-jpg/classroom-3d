// 画面相关的交互：暗角叠层、开场画幅、归正视角。无头 Chrome 跑真实页面。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { launch, fileUrl } from '../cdp.mjs';
import { HTML } from './helpers.mjs';

const sleep = ms => new Promise(r => setTimeout(r, ms));
async function open() {
  const b = await launch();
  await b.goto(fileUrl(HTML));
  await b.waitFor("window.__GI && __GI.status !== 'pending' && __GI.texStatus !== 'pending'");
  await sleep(600);
  return b;
}
// 暗角叠层画布上相对位置 (fx, fy) 处的不透明度 0..1（叠层是纯黑 + alpha）
const readVignette = `(() => {
  const a = (fx, fy) => grainCtx.getImageData(Math.round(fx * (grainCv.width - 1)), Math.round(fy * (grainCv.height - 1)), 1, 1).data[3] / 255;
  return { l: a(0, 0.5), r: a(1, 0.5), t: a(0.5, 0), btm: a(0.5, 1), corner: a(0, 0), mid: a(0.5, 0.5) };
})()`;

test('暗角柔和且按画幅归一：四边 ≤9%、四角约 22%，换成宽画幅不加重；画面静止时不逐帧重画', async () => {
  const b = await open();
  try {
    const v = await b.evaluate(readVignette);
    for (const k of ['l', 'r', 't', 'btm']) assert.ok(v[k] <= 0.09, `边缘 ${k} 压暗 ${v[k].toFixed(2)}（应 ≤ 0.09）`);
    assert.ok(v.corner >= 0.17 && v.corner <= 0.27, `四角压暗 ${v.corner.toFixed(2)}（应约 0.22）`);
    assert.equal(v.mid, 0);
    await b.evaluate(`setAspect('2.35'); true`); await sleep(500);
    const w = await b.evaluate(readVignette);
    for (const k of ['l', 'r', 't', 'btm', 'corner']) assert.ok(Math.abs(w[k] - v[k]) < 0.03, `换 2.35:1 画幅后 ${k}: ${v[k].toFixed(2)} → ${w[k].toFixed(2)}`);
    const calls = await b.evaluate(`(async () => { let n = 0; const f = window.drawGrain;
      window.drawGrain = function () { n++; return f.apply(this, arguments); };
      await new Promise(r => setTimeout(r, 1000)); window.drawGrain = f; return n; })()`);
    assert.equal(calls, 0, `画面静止时暗角 1 秒内重画了 ${calls} 次`);
  } finally { await b.close(); }
});

test('打开即「铺满」画幅：不锁比例、画面顶满可用区，设置面板的按钮与滑块一致', async () => {
  const b = await open();
  try {
    const s = await b.evaluate(`(() => { const av = viewSize(), r = frameRect(), cv = renderer.domElement.getBoundingClientRect();
      return { frameAspect, FRAME_FILL, w: r.w, h: r.h, avw: av.w, avh: av.h, cssW: Math.round(cv.width), cssH: Math.round(cv.height),
        on: [...document.querySelectorAll('.ar-btn.on')].map(e => e.dataset.ar), fill: +document.getElementById('frameFill').value,
        fillLabel: document.getElementById('frameFillv').textContent }; })()`);
    assert.equal(s.frameAspect, 0, JSON.stringify(s));
    assert.equal(s.FRAME_FILL, 1);
    assert.deepEqual(s.on, ['full']);
    assert.equal(s.fill, 1); assert.equal(s.fillLabel, '100%');
    assert.equal(s.w, s.avw); assert.equal(s.cssW, s.avw);
    assert.ok(Math.abs(s.h - s.avh) <= 1 && Math.abs(s.cssH - s.avh) <= 1, JSON.stringify(s));
  } finally { await b.close(); }
});

test('归正（L 键 / 点罗盘）：人不动，视线放平并对齐最近的墙面方向；罗盘真的点得到', async () => {
  const b = await open();
  try {
    await b.evaluate(`document.getElementById('cvGo')?.click(); true`);        // 先像用户一样点「进入」，让开场封面退场
    await sleep(1500);
    const hit = await b.evaluate(`(() => { const c = document.getElementById('compass'), r = c.getBoundingClientRect();
      const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return c.contains(el) || (el && (el.id || el.tagName)); })()`);
    assert.equal(hit, true, '罗盘挡在 pointer-events:none 后面，鼠标点不到');
    for (const trigger of ['key', 'compass']) {
      await b.evaluate('theta = 0.7; phi = 0.4; camR = 10; panX = -1.2; panZ = 3.5; panY = 0.2; updateCam(); true');
      await sleep(200);
      const p0 = await b.evaluate('camera.position.toArray()');
      await b.evaluate(trigger === 'key' ? `document.dispatchEvent(new KeyboardEvent('keydown', { key: 'l' })); true`
                                         : `document.getElementById('compass').click(); true`);
      await sleep(800);                                                     // 过渡 0.35s
      const s = await b.evaluate('(() => { const d = new THREE.Vector3(); camera.getWorldDirection(d); return { p: camera.position.toArray(), d: d.toArray(), theta }; })()');
      s.p.forEach((v, i) => assert.ok(Math.abs(v - p0[i]) < 1e-3, `${trigger}：相机位置变了 ${p0} → ${s.p}`));
      assert.ok(Math.abs(s.d[1]) < 1e-3, `${trigger}：视线不水平 ${s.d}`);
      assert.ok(Math.abs(Math.abs(s.d[0]) + Math.abs(s.d[2]) - 1) < 1e-3, `${trigger}：视线没沿房间轴向 ${s.d}`);
      const q = s.theta / (Math.PI / 2);
      assert.ok(Math.abs(q - Math.round(q)) < 1e-6, `${trigger}：θ=${s.theta} 不是 π/2 的整数倍`);
      assert.equal(Math.round(q), 0, `${trigger}：θ=0.7 最近的墙面方向是 0`);
    }
  } finally { await b.close(); }
});
