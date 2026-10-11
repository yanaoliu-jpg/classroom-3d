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
  // ArrayBuffer → base64，按 1MB 分块交给 Node：实测 ≥4MB 的 CDP 消息永远收不到（WebSocket 上限）
  const bytes = new Uint8Array(glb);
  const CH = 1024 * 1024, chunks = [];
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
