"""Blender 侧公用：Cycles/GPU 设置、世界、导入、坐标换算。只在 Blender 里 import。"""
import math, time
import bpy
import numpy as np
from mathutils import Vector

def three_to_bl(p):
    """three (x,y,z) → blender (x,-z,y)"""
    p = np.asarray(p, np.float64)
    return np.stack([p[..., 0], -p[..., 2], p[..., 1]], -1)

def setup_cycles(samples):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'METAL'
    prefs.get_devices()
    for d in prefs.devices:
        d.use = (d.type != 'CPU')
    sc.cycles.device = 'GPU'
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = False   # 自适应采样会让暗探针早早停采 → 相邻探针噪声大、插值出斑块（实测二阶差分中位 24–127%）
    sc.cycles.use_denoising = False
    sc.cycles.max_bounces = 8
    sc.cycles.diffuse_bounces = 6
    sc.cycles.glossy_bounces = 2
    sc.cycles.transmission_bounces = 2
    sc.cycles.transparent_max_bounces = 4
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.sample_clamp_indirect = 10.0
    return sc

def world_bg():
    sc = bpy.context.scene
    if sc.world is None:
        sc.world = bpy.data.worlds.new('World')
    w = sc.world
    try:
        w.use_nodes = True          # 5.x 已弃用但仍可用；6.0 移除后此句无害跳过
    except Exception:
        pass
    nt = w.node_tree
    bg = nt.nodes.get('Background')
    if bg is None:
        bg = nt.nodes.new('ShaderNodeBackground')
        out = nt.nodes.get('World Output') or nt.nodes.new('ShaderNodeOutputWorld')
        nt.links.new(bg.outputs[0], out.inputs[0])
    return bg

def set_world(rgb, strength=1.0):
    bg = world_bg()
    bg.inputs['Color'].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
    bg.inputs['Strength'].default_value = strength

def new_material(name):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    return m

def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [o for o in bpy.data.objects if o not in before and o.type == 'MESH']

def kill_emission(objs):
    """所有自发光置 0：灯由点光源/天空代表，避免重复计光（导出时已去掉，这里兜底）。"""
    seen = set()
    for o in objs:
        for slot in o.material_slots:
            m = slot.material
            if not m or m in seen or not m.node_tree:
                continue
            seen.add(m)
            for n in m.node_tree.nodes:
                if n.type == 'BSDF_PRINCIPLED' and 'Emission Strength' in n.inputs:
                    n.inputs['Emission Strength'].default_value = 0.0
                elif n.type == 'EMISSION':
                    n.inputs['Strength'].default_value = 0.0

def add_ground(size=400.0, albedo=0.25, z=-0.02):
    """室外地面：天光/阳光经它反射进窗（真实采光里天花板的亮主要来自这里）。"""
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, z))
    g = bpy.context.active_object
    g.name = 'GI_ground'
    m = new_material('GI_ground')
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (albedo, albedo, albedo, 1)
    b.inputs['Roughness'].default_value = 1.0
    g.data.materials.append(m)
    return g

def clear_lights():
    for o in [o for o in bpy.data.objects if o.type == 'LIGHT']:
        bpy.data.objects.remove(o, do_unlink=True)

def _cutoff_window(L, R):
    """three.js 点光源 distance=R 时在 1/d² 之外再乘 saturate(1-(d/R)^4)^2（r164 getDistanceAttenuation）。
    Cycles 灯光着色器里 Light Path 的 Ray Length = 着色点到光源采样点的距离 → 用节点算同一窗函数乘到发光强度上。"""
    L.use_nodes = True
    nt = L.node_tree
    em = next(n for n in nt.nodes if n.type == 'EMISSION')
    lp = nt.nodes.new('ShaderNodeLightPath')
    def op(kind, a, b, clamp=False):
        m = nt.nodes.new('ShaderNodeMath'); m.operation = kind; m.use_clamp = clamp
        for i, v in enumerate((a, b)):
            if isinstance(v, (int, float)): m.inputs[i].default_value = v
            else: nt.links.new(v, m.inputs[i])
        return m.outputs[0]
    x4 = op('POWER', op('DIVIDE', lp.outputs['Ray Length'], R), 4.0)
    nt.links.new(op('POWER', op('SUBTRACT', 1.0, x4, clamp=True), 2.0), em.inputs['Strength'])

def add_point(pos_three, power, radius=0.05, color=(1, 1, 1), name='pt', cutoff=None):
    L = bpy.data.lights.new(name, 'POINT')
    L.energy = power; L.shadow_soft_size = radius; L.color = color
    if cutoff:
        _cutoff_window(L, cutoff)
    o = bpy.data.objects.new(name, L)
    o.location = Vector(three_to_bl(pos_three).tolist())
    bpy.context.collection.objects.link(o)
    return o

def add_sun(dir_three, strength=1.0, color=(1, 1, 1), angle_deg=0.53, name='sun'):
    L = bpy.data.lights.new(name, 'SUN')
    L.energy = strength; L.color = color; L.angle = math.radians(angle_deg)
    o = bpy.data.objects.new(name, L)
    d = Vector(three_to_bl(dir_three).tolist()).normalized()
    o.rotation_mode = 'QUATERNION'
    o.rotation_quaternion = d.to_track_quat('-Z', 'Y')     # 太阳沿自身 -Z 照射
    bpy.context.collection.objects.link(o)
    return o

PROBE_VIS_OFF = ('visible_camera', 'visible_diffuse', 'visible_glossy', 'visible_transmission', 'visible_shadow')
FACE_NORMALS_BL = [(1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1), (0, -1, 0), (0, 1, 0)]   # three +X,-X,+Y,-Y,+Z,-Z

def make_probe_mesh(centers_three, size=0.004, name='GI_probes'):
    """每个探针 6 个朝外小方面；第 i 个探针第 k 面 → 图集第 6i+k 个像素（UV 只覆盖该像素中心）。"""
    C = three_to_bl(centers_three)
    n = len(C); nt = 6 * n
    W = int(math.ceil(math.sqrt(nt))); H = int(math.ceil(nt / W))
    h = size / 2.0
    N = np.array(FACE_NORMALS_BL, np.float64)
    A = np.where(np.abs(N[:, 2:3]) < 0.5, np.array([[0.0, 0.0, 1.0]]), np.array([[1.0, 0.0, 0.0]]))
    U = np.cross(N, A); U /= np.linalg.norm(U, axis=1, keepdims=True)
    Wv = np.cross(N, U)                                          # U × Wv = N → 下列角点顺序从外看为逆时针
    corners = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]], np.float64)
    off = corners[None, :, 0, None] * U[:, None, :] + corners[None, :, 1, None] * Wv[:, None, :]   # (6,4,3)
    V = (C[:, None, None, :] + N[None, :, None, :] * h + off[None] * h).reshape(-1, 3)
    faces = np.arange(nt * 4).reshape(nt, 4)
    me = bpy.data.meshes.new(name)
    me.from_pydata(V.tolist(), [], faces.tolist())
    uv = me.uv_layers.new(name='UVMap')
    t = np.arange(nt)
    uc = (t % W + 0.5) / W; vc = (t // W + 0.5) / H
    uvs = np.empty((nt, 4, 2), np.float32)
    uvs[:, :, 0] = uc[:, None] + corners[None, :, 0] * (0.3 / W)
    uvs[:, :, 1] = vc[:, None] + corners[None, :, 1] * (0.3 / H)
    uv.data.foreach_set('uv', uvs.ravel())
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    for a in PROBE_VIS_OFF:
        setattr(ob, a, False)
    ob.visible_volume_scatter = True        # 六项全关会被 Cycles 剔除 → 烘出全 0（可行性实验实测）
    img = bpy.data.images.new(name + '_img', width=W, height=H, float_buffer=True, alpha=True)
    img.colorspace_settings.name = 'Non-Color'
    mat = new_material(name + '_mat')
    b = mat.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (1, 1, 1, 1)
    b.inputs['Roughness'].default_value = 1.0
    for nm in ('Specular IOR Level', 'Specular'):
        if nm in b.inputs:
            b.inputs[nm].default_value = 0.0
    tex = mat.node_tree.nodes.new('ShaderNodeTexImage'); tex.image = img; mat.node_tree.nodes.active = tex
    me.materials.append(mat)
    return ob, img, W, H

def _double_sided(ob, poly_index):
    try:
        m = ob.material_slots[ob.data.polygons[poly_index].material_index].material
        return m is not None and not m.use_backface_culling     # glTF 导入：doubleSided → 不剔除背面
    except Exception:
        return False

DIRS14 = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1),
          (1, 1, 1), (1, 1, -1), (1, -1, 1), (1, -1, -1), (-1, 1, 1), (-1, 1, -1), (-1, -1, 1), (-1, -1, -1)]

def probe_validity(centers_three, max_dist=0.45):
    """探针若在 0.45m 内任一方向打到单面几何的背面 → 它在桌子/讲台/柜机内部 → 无效。必须在建探针网格之前调用。"""
    sc = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    dirs = [Vector(d).normalized() for d in DIRS14]
    C = three_to_bl(centers_three)
    valid = np.ones(len(C), bool)
    for i, c in enumerate(C):
        o = Vector(c.tolist())
        for d in dirs:
            hit, loc, nrm, idx, ob, _ = sc.ray_cast(dg, o, d, distance=max_dist)
            if hit and nrm.dot(d) > 0 and not _double_sided(ob, idx):
                valid[i] = False
                break
    return valid

def bake_irradiance(ob, img, W, H, passes, n_probes):
    """返回 (n_probes, 6, 3) 辐照度 E = π × Cycles 漫反射通道（可行性实验已验证）。"""
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    t0 = time.time()
    bpy.ops.object.bake(type='DIFFUSE', pass_filter=set(passes), margin=0, use_clear=True, target='IMAGE_TEXTURES')
    px = np.array(img.pixels[:], dtype=np.float32).reshape(H * W, 4)[: 6 * n_probes, :3]
    print(f'  烘焙 {sorted(passes)} {time.time() - t0:.1f}s', flush=True)
    return (px * math.pi).reshape(n_probes, 6, 3)

def add_portal(center_three, w, h, normal_three, name='portal'):
    """Cycles 天光门户：放在窗洞里的面光源标记，引导天空采样穿过窗户（只影响采样效率，不增减能量）。
    实测：室内探针天光噪声中位数 6.6% → 4.6%，均值不变。"""
    L = bpy.data.lights.new(name, 'AREA')
    L.shape = 'RECTANGLE'; L.size = w; L.size_y = h
    L.cycles.is_portal = True
    o = bpy.data.objects.new(name, L)
    o.location = Vector(three_to_bl(center_three).tolist())
    o.rotation_mode = 'QUATERNION'
    o.rotation_quaternion = Vector(three_to_bl(normal_three).tolist()).to_track_quat('-Z', 'Z')   # 面光源沿自身 -Z 朝向室内
    bpy.context.collection.objects.link(o)
    return o
