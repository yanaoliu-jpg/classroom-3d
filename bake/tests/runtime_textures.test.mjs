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
