"""探针体积（irradiance volume）的纯数据工具：网格、图集布局、对数编码、坏探针修补。
Blender 内（烘焙）与系统 Python（打包/单测）共用。坐标一律是 three.js 世界坐标（y 向上）。"""
import math
import numpy as np

LAYERS = [0.07, 0.28, 0.51, 0.81, 1.18, 1.55, 2.00, 2.50, 3.00, 3.36]   # 非均匀层高：紧贴地面/椅面/桌面/讲台面上方
FACES = ['+X', '-X', '+Y', '-Y', '+Z', '-Z']
SUN_ANGLES = list(range(-80, 81, 20))
GROUPS = ['SKY', 'CEIL', 'CORR_D', 'CORR_I'] + [f'SUN_{k}' for k in range(len(SUN_ANGLES))]
GROUP_COLS = 4
MAX_REGION_W = 504
LOG_K = 255.0

def volumes():
    return [
        dict(name='classroom', x0=-6.85, x1=6.85, nx=36, z0=-4.85, z1=15.85, nz=53,
             box=[[-7.0, 0.0, -5.0], [7.0, 3.5, 16.0]]),
        dict(name='corridor', x0=7.15, x1=8.75, nx=5, z0=-4.35, z1=21.35, nz=65,
             box=[[7.0, 0.0, -4.5], [8.9, 3.5, 21.5]]),
    ]

def grid_centers(v):
    """(nz*ny*nx, 3)，索引 = (iz*ny + iy)*nx + ix（x 最快）。"""
    xs = np.linspace(v['x0'], v['x1'], v['nx'])
    zs = np.linspace(v['z0'], v['z1'], v['nz'])
    ys = np.asarray(LAYERS, np.float64)
    Z, Y, X = np.meshgrid(zs, ys, xs, indexing='ij')
    return np.stack([X, Y, Z], axis=-1).reshape(-1, 3)

def all_centers(vols):
    return np.concatenate([grid_centers(v) for v in vols], axis=0)

def probe_offsets(vols):
    offs, n = [], 0
    for v in vols:
        offs.append(n)
        n += v['nx'] * len(LAYERS) * v['nz']
    return offs, n

def layer_coord(y, layers=LAYERS):
    """世界 y → 连续层号（与着色器 giLayerCoord、运行时 giLayerCoord 一致）。"""
    if y <= layers[0]:
        return 0.0
    for i in range(len(layers) - 1):
        if y < layers[i + 1]:
            return i + (y - layers[i]) / (layers[i + 1] - layers[i])
    return float(len(layers) - 1)

def atlas_layout(vols, n_groups=len(GROUPS), cols=GROUP_COLS, max_w=MAX_REGION_W):
    """每个体积占图集里的一段区域；区域内按"面 f、z 片 iz"排成 (nx × 层数) 的小格。"""
    ny = len(LAYERS)
    regions, y, W = [], 0, 0
    for v in vols:
        tiles = 6 * v['nz']
        tpr = max(1, min(tiles, max_w // v['nx']))
        rows = math.ceil(tiles / tpr)
        regions.append(dict(x0=0, y0=y, tpr=tpr, tw=v['nx'], th=ny, rows=rows))
        y += rows * ny
        W = max(W, tpr * v['nx'])
    return dict(W=W, H=y, cols=cols, rows=math.ceil(n_groups / cols), regions=regions)

def tile_origin(region, face, iz, nz):
    t = face * nz + iz
    return region['x0'] + (t % region['tpr']) * region['tw'], region['y0'] + (t // region['tpr']) * region['th']

def pack_atlas(E, vols, layout):
    """E: (N,6,3) 全体探针的六面辐照度 → (H, W, 3) 单组图集（行 = 层，列 = x）。"""
    A = np.zeros((layout['H'], layout['W'], 3), np.float32)
    offs, _ = probe_offsets(vols)
    ny = len(LAYERS)
    for v, off, reg in zip(vols, offs, layout['regions']):
        nx, nz = v['nx'], v['nz']
        Ev = E[off: off + nx * ny * nz].reshape(nz, ny, nx, 6, 3)
        for f in range(6):
            for iz in range(nz):
                x, y = tile_origin(reg, f, iz, nz)
                A[y:y + ny, x:x + nx] = Ev[iz, :, :, f, :]
    return A

def unpack_probe(A, vols, layout, vi, ix, iy, iz, face):
    x, y = tile_origin(layout['regions'][vi], face, iz, vols[vi]['nz'])
    return A[y + iy, x + ix]

def encode_log(x, scale):
    r = np.clip(np.asarray(x, np.float64) / scale, 0.0, 1.0)
    return np.round(np.log2(1.0 + LOG_K * r) / math.log2(1.0 + LOG_K) * 255.0).astype(np.uint8)

def decode_log(u8, scale):
    """与着色器 scale * (exp2(8*e) - 1) / 255 完全一致（K=255 → log2(1+K)=8）。"""
    e = np.asarray(u8, np.float64) / 255.0
    return scale * (np.power(1.0 + LOG_K, e) - 1.0) / LOG_K

def robust_scale(A, q=99.98):
    v = float(np.percentile(A, q)) if A.size else 0.0
    return max(v * 1.02, 1e-6)

def fill_invalid(E_grid, valid, max_iter=200):
    """E_grid: (nz,ny,nx,6,3)；valid: (nz,ny,nx)。无效探针用有效六邻居均值逐轮向内填补；孤立无援的置 0。"""
    E = np.array(E_grid, np.float64, copy=True)
    ok = np.array(valid, bool, copy=True)
    for _ in range(max_iter):
        if ok.all():
            break
        acc = np.zeros_like(E)
        cnt = np.zeros(ok.shape, np.float64)
        for axis in range(3):
            for s in (1, -1):
                sh_ok = np.roll(ok, s, axis=axis)
                sh_E = np.roll(E, s, axis=axis)
                edge = [slice(None)] * 3
                edge[axis] = slice(0, 1) if s == 1 else slice(-1, None)
                sh_ok[tuple(edge)] = False                 # 不回绕到对边
                acc += sh_E * sh_ok[..., None, None]
                cnt += sh_ok
        newly = (~ok) & (cnt > 0)
        if not newly.any():
            break
        E[newly] = acc[newly] / cnt[newly][..., None, None]
        ok |= newly
    E[~ok] = 0.0
    return E, ok

def fill_invalid_all(E, valid, vols):
    offs, _ = probe_offsets(vols)
    ny = len(LAYERS)
    out = np.array(E, np.float64, copy=True)
    for v, off in zip(vols, offs):
        n = v['nx'] * ny * v['nz']
        g, _ = fill_invalid(E[off:off + n].reshape(v['nz'], ny, v['nx'], 6, 3),
                            valid[off:off + n].reshape(v['nz'], ny, v['nx']))
        out[off:off + n] = g.reshape(n, 6, 3)
    return out

def smooth_xz(E_grid, passes=1):
    """水平方向（x、z）[1,4,1]/6 平滑，压蒙特卡洛噪声（白噪声标准差约减半）。
    不在 y 方向平滑：非均匀层是故意贴着桌面/椅面分开的，混层会把桌肚的暗漏到桌面上。边界复制边缘值。"""
    E = np.array(E_grid, np.float64, copy=True)
    for _ in range(passes):
        for axis in (0, 2):                                   # (nz, ny, nx, 6, 3) 的 z 轴与 x 轴
            pad = [(0, 0)] * E.ndim; pad[axis] = (1, 1)
            P = np.pad(E, pad, mode='edge')
            sl = lambda a, b: tuple(slice(a, P.shape[axis] - b) if k == axis else slice(None) for k in range(E.ndim))
            E = (P[sl(0, 2)] + 4.0 * P[sl(1, 1)] + P[sl(2, 0)]) / 6.0
    return E

def smooth_all(E, vols):
    offs, _ = probe_offsets(vols)
    ny = len(LAYERS)
    out = np.array(E, np.float64, copy=True)
    for v, off in zip(vols, offs):
        n = v['nx'] * ny * v['nz']
        out[off:off + n] = smooth_xz(E[off:off + n].reshape(v['nz'], ny, v['nx'], 6, 3)).reshape(n, 6, 3)
    return out

def ambient_cube(c6, n):
    n = np.asarray(n, np.float64)
    n2 = n * n
    fx = 0 if n[0] >= 0 else 1
    fy = 2 if n[1] >= 0 else 3
    fz = 4 if n[2] >= 0 else 5
    return n2[0] * np.asarray(c6[fx]) + n2[1] * np.asarray(c6[fy]) + n2[2] * np.asarray(c6[fz])

def tile_groups(cells, layout):
    H, W, C = layout['H'], layout['W'], layout['cols']
    big = np.zeros((layout['rows'] * H, C * W, 3), np.uint8)
    for g, cell in enumerate(cells):
        r, c = divmod(g, C)
        big[r * H:(r + 1) * H, c * W:(c + 1) * W] = cell
    return big

def runtime_meta(layout, vols, groups, scales, sun_dirs, extra=None):
    m = dict(version=1, layers=LAYERS, groups=list(groups), scales=[float(s) for s in scales],
             atlas=dict(W=layout['W'], H=layout['H'], cols=layout['cols'], rows=layout['rows'],
                        regions=layout['regions']),
             volumes=[dict(name=v['name'], x0=v['x0'], x1=v['x1'], nx=v['nx'], z0=v['z0'], z1=v['z1'],
                           nz=v['nz'], box=v['box']) for v in vols],
             sunKeys=[list(map(float, d)) for d in sun_dirs],
             units='E = 辐照度（three.js 物理单位，已乘 π）；对数编码 v = s*(2^(8e)-1)/255')
    if extra:
        m.update(extra)
    return m
