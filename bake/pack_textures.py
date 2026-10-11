#!/usr/bin/env python3
"""生成运行时贴图：地砖（Blender 法线/AO + numpy 反照率/粗糙度）、墙漆、吸音板、两套木纹 → bake/out/tex/*.webp + tex.json"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tex_lib as X

OUT = HERE / 'out' / 'tex'; RAW = HERE / 'out' / 'tex_raw'; PH = HERE / 'assets' / 'polyhaven'
# 旧地砖的平均线性反照率（0xaaa69b × 旧 floorTex 均值），新地砖用 tint 对齐它，避免强阳光下"死白"回潮
OLD_FLOOR_ALBEDO = np.array([0.204, 0.187, 0.146])
WOOD_TARGET = {'ash': [0.70, 0.54, 0.36], 'plywood': [0.68, 0.52, 0.35]}   # 暖蜂蜜色，降饱和（sRGB 均值）

def u8(a):
    return (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)

def save(arr01, name, q):
    if arr01.ndim == 2:
        arr01 = np.repeat(arr01[..., None], 3, -1)
    Image.fromarray(u8(arr01), 'RGB').save(OUT / name, 'WEBP', quality=q, method=6)
    return name

def load_jpg(path, size):
    im = Image.open(path).convert('RGB').resize((size, size), Image.LANCZOS)
    return np.asarray(im, np.float64) / 255.0

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {}
    # 地砖
    ao = np.load(RAW / 'floor_ao.npy'); nrm = np.load(RAW / 'floor_normal.npy')
    alb, rough = X.make_floor(ao, n=ao.shape[0])
    tint = OLD_FLOOR_ALBEDO / X.srgb_to_linear(alb).mean(axis=(0, 1))
    meta['floor'] = dict(albedo=save(alb, 'floor_albedo.webp', 90), normal=save(nrm, 'floor_normal.webp', 92),
                         rough=save(rough, 'floor_rough.webp', 85), size=2.4, tint=[round(float(t), 4) for t in tint])
    # 墙漆
    wa, wn = X.make_wall(1024)
    meta['wall'] = dict(albedo=save(wa, 'wall_albedo.webp', 90), normal=save(wn, 'wall_normal.webp', 92), size=2.0)
    # 吸音板
    ca, cn = X.make_ceiling_tile(1024)
    meta['ceilTile'] = dict(albedo=save(ca, 'ceil_albedo.webp', 90), normal=save(cn, 'ceil_normal.webp', 92))
    # 木纹（Poly Haven）：调色 + 粗糙度按清漆面重映射
    for kind, src, size in [('ash', 'ash_veneer', 1.0), ('plywood', 'plywood', 0.5)]:
        d = load_jpg(PH / f'{src}_diff_2k.jpg', 1024)
        n = load_jpg(PH / f'{src}_nor_gl_2k.jpg', 1024)
        r = load_jpg(PH / f'{src}_rough_2k.jpg', 1024)[..., 0]
        meta[kind] = dict(albedo=save(X.grade_to_mean(d, WOOD_TARGET[kind]), f'{kind}_albedo.webp', 88),
                          normal=save(n, f'{kind}_normal.webp', 90),
                          rough=save(0.32 + 0.25 * r, f'{kind}_rough.webp', 85), size=size)
    (OUT / 'tex.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    total = sum(p.stat().st_size for p in OUT.glob('*.webp'))
    print(f'TEX {len(list(OUT.glob("*.webp")))} 张 WebP，共 {total / 1e6:.2f} MB；地砖 tint={meta["floor"]["tint"]}')

if __name__ == '__main__':
    main()
