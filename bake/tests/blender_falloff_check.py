# blender -b --factory-startup -P bake/tests/blender_falloff_check.py
# 点光源截断衰减：three.js（distance>0）在 1/d² 之外再乘窗函数 saturate(1-(d/R)^4)^2，
# Cycles 侧的 add_point(cutoff=R) 必须给出同一条曲线；cutoff=None 保持纯 1/d²。
import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import bpy
import blender_common as B

bpy.ops.wm.read_factory_settings(use_empty=True)
B.setup_cycles(256)
B.set_world((0, 0, 0), 1.0)
DS = [1.0, 2.0, 3.0, 3.6, 4.5]
ok = True
for R in (4.2, None):
    B.clear_lights()
    for o in [o for o in bpy.data.objects if o.name.startswith('GI_probes')]:
        bpy.data.objects.remove(o, do_unlink=True)
    B.add_point((0, 1.5, 0), 4 * math.pi, cutoff=R, name='p')          # three.js intensity I = 1 cd
    centers = np.array([[d, 1.5, 0] for d in DS])
    ob, img, W, H = B.make_probe_mesh(centers)
    E = B.bake_irradiance(ob, img, W, H, ['DIRECT'], len(DS))[:, 1, :].mean(axis=1)   # −X 面朝向光源
    for d, e in zip(DS, E):
        w = 1.0 if R is None else max(0.0, 1 - (d / R) ** 4) ** 2
        want = w / d ** 2
        good = abs(e - want) <= 0.03 * want + 2e-4
        ok &= good
        print(f'FALLOFF R={R} d={d} E={e:.5f} want={want:.5f} {"ok" if good else "BAD"}', flush=True)
print('FALLOFF', 'OK' if ok else 'FAIL')
sys.exit(0 if ok else 1)
