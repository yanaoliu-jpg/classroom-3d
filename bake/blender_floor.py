"""地砖：在 Blender 里用真实倒角几何建 4×4 块 600mm 瓷砖（3mm 缝、1.5mm 倒角、±0.3mm 高差），
Cycles 烘焙到平面得到切线空间法线 + AO。网格居中排布 → 贴图四方连续。
用法：blender -b --factory-startup -P bake/blender_floor.py -- [--res 2048]"""
import sys, random, argparse
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import bpy
import blender_common as B

def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser(); ap.add_argument('--res', type=int, default=2048)
    a = ap.parse_args(argv)
    out = HERE / 'out' / 'tex_raw'; out.mkdir(parents=True, exist_ok=True)
    N, T, GAP, BEV, TH = 4, 0.6, 0.003, 0.0015, 0.010
    S = N * T
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = B.setup_cycles(64)
    B.set_world((1, 1, 1), 1.0)
    sc.world.light_settings.distance = 0.01            # AO 只看 1cm 内（缝/倒角尺度）
    rng = random.Random(7)
    high = []
    for i in range(N):
        for j in range(N):
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-S / 2 + T / 2 + i * T, -S / 2 + T / 2 + j * T,
                                                                -TH / 2 + rng.uniform(-0.0003, 0.0003)))
            ob = bpy.context.active_object
            ob.scale = (T - GAP, T - GAP, TH)
            ob.rotation_euler = (rng.uniform(-4e-4, 4e-4), rng.uniform(-4e-4, 4e-4), 0.0)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
            mod = ob.modifiers.new('bev', 'BEVEL'); mod.width = BEV; mod.segments = 3
            high.append(ob)
    bpy.ops.mesh.primitive_plane_add(size=S + 0.2, location=(0, 0, -0.0015))    # 缝底（勾缝剂面）
    high.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_plane_add(size=S, location=(0, 0, 0.002))            # 烘焙目标：UV 0..1 ↔ [-S/2, S/2]
    low = bpy.context.active_object
    mat = B.new_material('bake')
    tex = mat.node_tree.nodes.new('ShaderNodeTexImage'); mat.node_tree.nodes.active = tex
    low.data.materials.append(mat)

    def bake(kind, **kw):
        img = bpy.data.images.new(kind, a.res, a.res, float_buffer=True)
        img.colorspace_settings.name = 'Non-Color'
        tex.image = img
        bpy.ops.object.select_all(action='DESELECT')
        for o in high:
            o.select_set(True)
        low.select_set(True); bpy.context.view_layer.objects.active = low
        bpy.ops.object.bake(type=kind, use_selected_to_active=True, cage_extrusion=0.01,
                            max_ray_distance=0.02, margin=0, use_clear=True, **kw)
        px = np.array(img.pixels[:], np.float32).reshape(a.res, a.res, 4)
        return np.flipud(px)       # Blender 像素行0=底部 → 统一成行0=顶部（与图片文件一致）

    nrm = bake('NORMAL', normal_space='TANGENT')[..., :3]
    ao = bake('AO')[..., 0]
    np.save(out / 'floor_normal.npy', nrm.astype(np.float32))
    np.save(out / 'floor_ao.npy', ao.astype(np.float32))
    print('FLOOR normal mean', nrm.reshape(-1, 3).mean(0).round(3), 'ao min/mean', float(ao.min()), float(ao.mean()))

main()
