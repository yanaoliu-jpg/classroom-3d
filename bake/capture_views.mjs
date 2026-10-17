// 用法：node bake/capture_views.mjs [--tune '{"skyScale":0.5}'] [--only after] [--tonemap agx]
// --tonemap agx：只拍改后、存 <case>_after_agx.png（spec 4.4-6：出一组 AgX 对比给用户选，不擅自切换）
// 为每个 case 拍 改后/改前 画布，并导出相机与灯光状态（供 blender_reference.py 渲参考图）
import { writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { launch, fileUrl } from './cdp.mjs';
import { HTML, OUT } from './tests/helpers.mjs';

const args = process.argv.slice(2);
const tune = args.includes('--tune') ? args[args.indexOf('--tune') + 1] : null;
const only = args.includes('--only') ? args[args.indexOf('--only') + 1] : null;
const agx = args.includes('--tonemap') && args[args.indexOf('--tonemap') + 1] === 'agx';
const VIEWS = join(OUT, 'views'); mkdirSync(VIEWS, { recursive: true });
const CORR = "{fov:70, theta:Math.PI, phi:0.02, camR:0.6, panX:7.95, panZ:4.0, panY:0.1, name:'走廊'}";
const CASES = [];
for (const p of ['morning', 'noon', 'dusk', 'night']) for (const v of ['5', '6', '7', '9']) CASES.push({ id: `${p}_${v}`, preset: p, view: `CAM_VIEWS['${v}']` });
CASES.push({ id: 'night_corr', preset: 'night', view: CORR }, { id: 'noon_corr', preset: 'noon', view: CORR });

// distance：three.js 截断距离，参考图里用同一窗函数（blender_common.add_point cutoff）
const STATE = `(() => {
  const d = new THREE.Vector3().subVectors(mainLight.target.position, mainLight.position).normalize();
  const w = __GI.lastWeights || new Float32Array(39);
  return {
    camera: { position: camera.position.toArray(), quaternion: camera.quaternion.toArray(), fov: camera.fov, aspect: camera.aspect },
    exposure: renderer.toneMappingExposure,
    sky: [w[0], w[1], w[2]],
    sun: { dir: [d.x, d.y, d.z], intensity: mainLight.intensity, color: mainLight.color.toArray() },
    ceil: { positions: fluoroLights.map(l => l.getWorldPosition(new THREE.Vector3()).toArray()), intensity: fluoroLights[0].intensity, color: ceilColor.toArray(), distance: fluoroLights[0].distance },
    corr: { positions: corrLampLights.map(l => l.getWorldPosition(new THREE.Vector3()).toArray()), intensity: corrLampLights[0].intensity, color: corrLampLights[0].color.toArray(), distance: corrLampLights[0].distance },
  }; })()`;

async function run(path, tag) {
  const b = await launch();
  try {
    await b.goto(fileUrl(path));
    await b.waitFor("!window.__GI || (__GI.status !== 'pending' && __GI.texStatus !== 'pending')");
    if (tune && tag === 'after') await b.evaluate(`__GI.tune(${tune})`);
    if (agx) await b.evaluate('renderer.toneMapping = THREE.AgXToneMapping; true');   // OutputPass 自动切换
    for (const c of CASES) {
      await b.evaluate(`applyPreset('${c.preset}'); applyView(${c.view}); true`);
      await new Promise(r => setTimeout(r, 3500));          // 等吊顶灯/走廊灯/半球光的平滑过渡收敛
      await b.canvasPNG(join(VIEWS, `${c.id}_${tag}${agx ? '_agx' : ''}.png`));
      if (tag === 'after' && !agx) writeFileSync(join(VIEWS, `${c.id}.json`), JSON.stringify(await b.evaluate(STATE)));
    }
  } finally { await b.close(); }
}
if (only !== 'before') await run(HTML, 'after');
if (only !== 'after' && !agx) await run(join(OUT, 'before.html'), 'before');
console.log('ok', CASES.length, 'cases');
