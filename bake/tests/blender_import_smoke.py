# blender -b --factory-startup -P bake/tests/blender_import_smoke.py
import sys
from pathlib import Path
import bpy
from mathutils import Vector

OUT = Path(__file__).resolve().parents[1] / 'out'
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(OUT / 'scene.glb'))
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
mn = Vector((1e9, 1e9, 1e9)); mx = Vector((-1e9, -1e9, -1e9))
for o in meshes:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        mn = Vector(map(min, mn, w)); mx = Vector(map(max, mx, w))
culled = sum(1 for m in bpy.data.materials if m.use_backface_culling)
print('SMOKE meshes', len(meshes), 'bbox', tuple(round(v, 2) for v in mn), tuple(round(v, 2) for v in mx),
      'single-sided mats', culled, '/', len(bpy.data.materials))
# three(x,y,z) → blender(x,-z,y)：教室 x∈[-7,7]、走廊到 x=8.9、层高 3.5（屋顶到 3.9）
ok = len(meshes) > 500 and mn.x <= -7.0 and mx.x >= 8.8 and mx.z >= 3.4
print('SMOKE', 'OK' if ok else 'FAIL')
sys.exit(0 if ok else 1)
