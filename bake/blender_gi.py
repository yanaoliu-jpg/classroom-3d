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
    p.add_argument('--samples', type=int, default=4096)   # 关掉自适应后 1024 采样仍有 7–11% 探针噪声
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
            for i, w in enumerate(meta.get('windows', [])): B.add_portal(w['center'], w['w'], w['h'], w['normal'], name=f'portal{i}')
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
