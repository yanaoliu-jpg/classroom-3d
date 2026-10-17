#!/usr/bin/env python3
"""参考图色调映射（与 three.js ACESFilmic 逐式一致）+ 分格亮度偏差 + 三联图。
用法：python3 bake/compare.py   （读 bake/out/views/，写 docs/superpowers/compare/cyclesgi_*.png）
      python3 bake/compare.py --agx   （ACES | AgX 并排对比图 tonemap_aces_vs_agx.png）"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
HERE = Path(__file__).resolve().parent
VIEWS = HERE / 'out' / 'views'
DOCS = HERE.parent / 'docs' / 'superpowers' / 'compare'

IN = np.array([[0.59719, 0.35458, 0.04823], [0.07600, 0.90834, 0.01566], [0.02840, 0.13383, 0.83777]])
OUTM = np.array([[1.60475, -0.53108, -0.07367], [-0.10208, 1.10813, -0.00605], [-0.00327, -0.07276, 1.07602]])

def aces_srgb(lin, exposure):
    """three.js r164 ACESFilmicToneMapping + sRGB OETF；lin: (H,W,3) 线性 → uint8"""
    c = np.asarray(lin, np.float64) * (exposure / 0.6)
    c = c @ IN.T
    a = c * (c + 0.0245786) - 0.000090537
    b = c * (0.983729 * c + 0.4329510) + 0.238081
    c = np.clip((a / b) @ OUTM.T, 0, 1)
    s = np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - 0.055)
    return (np.clip(s, 0, 1) * 255 + 0.5).astype(np.uint8)

def _lum(img):
    x = np.asarray(img, np.float64) / 255.0
    lin = np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
    return lin @ np.array([0.2126, 0.7152, 0.0722])

def grid_log_error(a, b, gx=8, gy=6, floor=2 / 255):
    """8×6 分格平均线性亮度的 |log(a/b)| 中位数（两边都太暗的格子不计）。0 = 一致。"""
    la, lb = _lum(a), _lum(b)
    H, W = la.shape
    errs = []
    for j in range(gy):
        for i in range(gx):
            sa = la[j * H // gy:(j + 1) * H // gy, i * W // gx:(i + 1) * W // gx].mean()
            sb = lb[j * H // gy:(j + 1) * H // gy, i * W // gx:(i + 1) * W // gx].mean()
            if sa > floor and sb > floor:
                errs.append(abs(np.log(sa / sb)))
    return float(np.median(errs)) if errs else 0.0

def _font(size=16):
    # PIL 默认字体没有中文字形（标签会变成方框）→ 优先用系统中文字体
    for p in ('/System/Library/Fonts/Hiragino Sans GB.ttc', '/System/Library/Fonts/STHeiti Medium.ttc', '/Library/Fonts/Arial Unicode.ttf'):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()

def triptych(imgs, labels, path):
    w, h = imgs[0].size
    out = Image.new('RGB', (w * len(imgs), h + 28), (12, 12, 14))
    d = ImageDraw.Draw(out); f = _font()
    for i, (im, lb) in enumerate(zip(imgs, labels)):
        out.paste(im, (i * w, 28)); d.text((i * w + 10, 5), lb, fill=(230, 230, 230), font=f)
    out.save(path)

AGX_CASES = ('morning_5', 'noon_5', 'dusk_5', 'night_5', 'noon_7', 'noon_corr')

def agx_sheet(cases=AGX_CASES):
    """spec 4.4-6：同一画面 ACES（现用）| AgX 并排给用户选，不擅自切换。需先 node bake/capture_views.mjs --tonemap agx"""
    pairs = [(VIEWS / f'{c}_after.png', VIEWS / f'{c}_after_agx.png', c) for c in cases]
    pairs = [p for p in pairs if p[0].exists() and p[1].exists()]
    if not pairs:
        return None
    w, h = Image.open(pairs[0][0]).size
    out = Image.new('RGB', (w * 2, (h + 28) * len(pairs)), (12, 12, 14))
    d = ImageDraw.Draw(out); f = _font()
    for i, (a, b, c) in enumerate(pairs):
        y = i * (h + 28)
        out.paste(Image.open(a).convert('RGB'), (0, y + 28)); out.paste(Image.open(b).convert('RGB'), (w, y + 28))
        d.text((10, y + 5), f'{c}  ACES（现用）', fill=(230, 230, 230), font=f)
        d.text((w + 10, y + 5), f'{c}  AgX（Blender 默认）', fill=(230, 230, 230), font=f)
    DOCS.mkdir(parents=True, exist_ok=True)
    path = DOCS / 'tonemap_aces_vs_agx.png'
    out.save(path)
    return path

def main():
    if '--agx' in sys.argv:
        print(agx_sheet() or '没有 *_after_agx.png：先运行 node bake/capture_views.mjs --tonemap agx')
        return
    DOCS.mkdir(parents=True, exist_ok=True)
    rows = []
    for js in sorted(VIEWS.glob('*.json')):
        case = js.stem; st = json.loads(js.read_text())
        ref_npy = VIEWS / f'{case}_ref.npy'
        if not ref_npy.exists():
            continue
        after = Image.open(VIEWS / f'{case}_after.png').convert('RGB')
        before = Image.open(VIEWS / f'{case}_before.png').convert('RGB').resize(after.size)
        ref = Image.fromarray(aces_srgb(np.load(ref_npy), st['exposure'])).resize(after.size)
        ea, eb = grid_log_error(np.asarray(after), np.asarray(ref)), grid_log_error(np.asarray(before), np.asarray(ref))
        rows.append((case, eb, ea))
        triptych([before, after, ref], [f'改前  偏差 {eb:.3f}', f'改后  偏差 {ea:.3f}', 'Cycles 参考（同机位同灯光）'],
                 DOCS / f'cyclesgi_{case}.png')
    print(f'{"case":24s} {"改前":>8s} {"改后":>8s}')
    for c, eb, ea in rows:
        print(f'{c:24s} {eb:8.3f} {ea:8.3f} {"✔" if ea < eb else "✘"}')
    if rows:
        print(f'改后更接近参考：{sum(ea < eb for _, eb, ea in rows)}/{len(rows)}')

if __name__ == '__main__':
    main()
