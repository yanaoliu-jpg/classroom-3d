"""按 capture_views 导出的相机与灯光状态渲染 Cycles 参考图（线性，存 .npy）。
用法：blender -b --factory-startup -P bake/blender_reference.py -- [--samples 256] [--only noon_7[,noon_5,…]]"""
import sys, json, math, argparse
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import bpy
from mathutils import Quaternion, Vector
import blender_common as B

def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser(); ap.add_argument('--samples', type=int, default=256); ap.add_argument('--only', default='')
    a = ap.parse_args(argv)
    out = HERE / 'out'; views = out / 'views'
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = B.setup_cycles(a.samples)
    sc.cycles.use_denoising = True
    sc.view_settings.view_transform = 'Standard'          # 线性输出，色调映射在 compare.py 里按 three.js 做
    sc.render.resolution_x, sc.render.resolution_y = 960, 540
    sc.render.image_settings.file_format = 'OPEN_EXR'
    objs = B.import_glb(out / 'scene.glb'); B.kill_emission(objs); B.add_ground()
    cam_data = bpy.data.cameras.new('cam'); cam = bpy.data.objects.new('cam', cam_data)
    bpy.context.collection.objects.link(cam); sc.camera = cam
    only = set(a.only.split(',')) if a.only else None       # 逗号分隔多个 case：一次导入场景渲多张
    for js in sorted(views.glob('*.json')):
        case = js.stem
        if only and case not in only:
            continue
        st = json.loads(js.read_text())
        B.clear_lights()
        B.set_world(st['sky'], 1.0)                                       # 均匀天空亮度 = 运行时 SKY 组权重
        if st['sun']['intensity'] > 0 and st['sun']['dir'][1] < 0:
            B.add_sun(st['sun']['dir'], st['sun']['intensity'], tuple(st['sun']['color']))
        for i, p in enumerate(st['ceil']['positions']):
            if st['ceil']['intensity'] > 0:
                B.add_point(p, 4 * math.pi * st['ceil']['intensity'], color=tuple(st['ceil']['color']), name=f'c{i}',
                            cutoff=st['ceil'].get('distance'))
        for i, p in enumerate(st['corr']['positions']):
            if st['corr']['intensity'] > 0:
                B.add_point(p, 4 * math.pi * st['corr']['intensity'], color=tuple(st['corr']['color']), name=f'r{i}',
                            cutoff=st['corr'].get('distance'))
        c = st['camera']
        cam.location = Vector(B.three_to_bl(c['position']).tolist())
        qx, qy, qz, qw = c['quaternion']
        # three → blender：先转到 Z 向上坐标系（绕 X 轴 +90°），相机朝向约定两者相同（看向自身 -Z）
        cam.rotation_mode = 'QUATERNION'
        cam.rotation_quaternion = Quaternion((math.cos(math.pi / 4), math.sin(math.pi / 4), 0, 0)) @ Quaternion((qw, qx, qy, qz))
        cam_data.sensor_fit = 'VERTICAL'; cam_data.angle_y = math.radians(c['fov'])
        cam_data.clip_start, cam_data.clip_end = 0.3, 80
        sc.render.resolution_y = int(round(960 / c['aspect']))
        exr = views / f'{case}_ref.exr'
        sc.render.filepath = str(exr)
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(str(exr))
        px = np.array(img.pixels[:], np.float32).reshape(img.size[1], img.size[0], 4)[::-1, :, :3]
        np.save(views / f'{case}_ref.npy', px); bpy.data.images.remove(img)
        print('REF', case, px.shape, float(px.mean()), flush=True)

main()
