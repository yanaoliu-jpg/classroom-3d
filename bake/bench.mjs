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
