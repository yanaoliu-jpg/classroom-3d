import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { HTML } from './helpers.mjs';

const src = readFileSync(HTML, 'utf8').match(/\/\/ ==GI-PURE-BEGIN==[^\n]*\n([\s\S]*?)\/\/ ==GI-PURE-END==/);
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

// 终审：GLSL ES 允许除法有 2.5 ULP 误差，D3D（Windows 上的 ANGLE）常把 x/y 算成 x*rcp(y)。
// 用浮点 mod/floor(x/y) 求图集格子坐标时，tpr=14/100 的整倍数会差一格（读到区域外/错一行 → 地面出现错光的横带）。
// 这类误差在本机 GPU 上复现不了，只能锁住写法：格子坐标必须用整数运算。
test('GI 图集与合成通道的格子寻址用整数运算（不依赖浮点除法精度）', () => {
  const html = readFileSync(HTML, 'utf8');
  const giTex = html.match(/vec3 giTex\([\s\S]*?\n\}/);
  assert.ok(giTex, '找不到 giTex');
  assert.ok(!/\bmod\s*\(/.test(giTex[0]) && !/floor\s*\(\s*tile\s*\//.test(giTex[0]), giTex[0]);
  assert.match(giTex[0], /%/);
  const comb = html.match(/uniform sampler2D groups;[\s\S]*?gl_FragColor/);
  assert.ok(comb, '找不到合成着色器');
  assert.ok(!/\bmod\s*\(/.test(comb[0]) && !/floor\s*\(\s*float\s*\(\s*g\s*\)\s*\//.test(comb[0]), comb[0]);
});
