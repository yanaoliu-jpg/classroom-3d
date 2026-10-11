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
