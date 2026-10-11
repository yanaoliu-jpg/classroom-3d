#!/usr/bin/env python3
"""把 Blender 烘出的原始探针数据修补、编码成运行时图集：bake/out/gi_atlas.png + gi.json"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gi_lib as G

def main(out=HERE / 'out'):
    out = Path(out); raw = out / 'gi_raw'
    info = json.loads((raw / 'bake_info.json').read_text())
    groups = info['groups']
    if groups != G.GROUPS:
        raise SystemExit(f'组不全：{groups}（需要全部 {len(G.GROUPS)} 组，先完整烘焙）')
    vols = G.volumes(); layout = G.atlas_layout(vols)
    valid = np.load(raw / 'valid.npy')
    cells, scales = [], []
    for g in groups:
        E = np.nan_to_num(np.maximum(np.load(raw / f'{g}.npy').astype(np.float64), 0.0))
        E = G.fill_invalid_all(E, valid, vols)
        A = G.pack_atlas(E, vols, layout)
        s = G.robust_scale(A)
        cells.append(G.encode_log(A, s)); scales.append(s)
        print(f'{g:7s} scale={s:.4g} mean={A.mean():.4g}')
    big = G.tile_groups(cells, layout)
    Image.fromarray(big, 'RGB').save(out / 'gi_atlas.png', optimize=True)
    meta = G.runtime_meta(layout, vols, groups, scales, info['sunKeys'],
                          extra=dict(samples=info['samples'], quick=info['quick'], invalid=int((~valid).sum())))
    (out / 'gi.json').write_text(json.dumps(meta, ensure_ascii=False))
    print('gi_atlas.png', (out / 'gi_atlas.png').stat().st_size // 1024, 'KB', big.shape)

if __name__ == '__main__':
    main()
