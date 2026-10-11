"""程序化贴图工具（numpy）：四方连续噪声、法线、色彩空间、墙漆/吸音板/地砖生成、木纹调色。
约定：所有图像数组"行 0 = 图像顶部 = 纹理 v=1"（three.js 读图片时 flipY=true）。"""
import numpy as np

def periodic_noise(n, beta, seed, fmin=1.0, fmax=None):
    """四方连续 1/f^beta 噪声（FFT 合成，天然无缝），归一化到 [0,1]。fmin/fmax 以"每张贴图的周期数"计。"""
    rng = np.random.default_rng(seed)
    white = rng.standard_normal((n, n))
    fy = np.fft.fftfreq(n)[:, None] * n
    fx = np.fft.fftfreq(n)[None, :] * n
    f = np.sqrt(fx ** 2 + fy ** 2)
    m = f >= fmin
    if fmax is not None:
        m &= f <= fmax
    amp = np.zeros_like(f)
    amp[m] = f[m] ** (-beta / 2.0)
    out = np.real(np.fft.ifft2(np.fft.fft2(white) * amp))
    out -= out.min()
    out /= max(out.max(), 1e-12)
    return out

def gaussian_blur_periodic(img, sigma):
    n0, n1 = img.shape
    fy = np.fft.fftfreq(n0)[:, None]
    fx = np.fft.fftfreq(n1)[None, :]
    k = np.exp(-2.0 * (np.pi ** 2) * (sigma ** 2) * (fx ** 2 + fy ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(img) * k))

def normal_from_height(h, strength):
    """高度图 → OpenGL 切线空间法线 RGB∈[0,1]（绿 = +v = 图像上方）。周期边界。"""
    h = np.asarray(h, np.float64)
    dhdu = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5
    dhdrow = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * 0.5
    dhdv = -dhdrow                         # 行号向下增加，v 向上增加
    nx, ny, nz = -dhdu * strength, -dhdv * strength, np.ones_like(h)
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx * inv, ny * inv, nz * inv], -1) * 0.5 + 0.5

def linear_to_srgb(x):
    x = np.clip(np.asarray(x, np.float64), 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)

def srgb_to_linear(x):
    x = np.clip(np.asarray(x, np.float64), 0, 1)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))

def seam_ratio(img):
    """接缝检查：首尾行/列的跳变 ÷ 内部相邻行/列的平均跳变。≈1 无缝；≫1 有接缝。"""
    a = np.asarray(img, np.float64)
    inner_c = np.mean(np.abs(np.diff(a, axis=1))); edge_c = np.mean(np.abs(a[:, 0] - a[:, -1]))
    inner_r = np.mean(np.abs(np.diff(a, axis=0))); edge_r = np.mean(np.abs(a[0] - a[-1]))
    return max(edge_c / max(inner_c, 1e-12), edge_r / max(inner_r, 1e-12))

def make_wall(n=1024, seed=11):
    """乳胶漆墙面：反照率是均值 0.97、±2% 的低频斑驳（乘在原墙色上，不改墙色）；法线是滚筒橘皮微纹。"""
    mottle = periodic_noise(n, 3.0, seed, fmin=1, fmax=24)
    alb = 0.97 + (mottle - 0.5) * 0.04
    stipple = periodic_noise(n, 1.2, seed + 1, fmin=40) * 0.7 + periodic_noise(n, 2.5, seed + 2, fmin=8, fmax=80) * 0.3
    return np.repeat(alb[..., None], 3, -1), normal_from_height(stipple, strength=1.2)

def make_ceiling_tile(n=1024, seed=21, boards=2):
    """矿棉吸音板（一张贴图 = 一块吊顶面板）：2×2 小板 V 形分缝 + 蠕虫状裂纹 + 针孔。反照率是乘在原色上的明暗。"""
    rng = np.random.default_rng(seed)
    y, x = (np.mgrid[0:n, 0:n] + 0.5) / n
    cx = (x * boards) % 1.0; cy = (y * boards) % 1.0
    edge = np.minimum(np.minimum(cx, 1 - cx), np.minimum(cy, 1 - cy)) / boards
    groove = np.clip(edge / 0.004, 0, 1)                        # 0=缝里 1=板面
    r = periodic_noise(n, 2.2, seed + 1, fmin=6, fmax=160)
    ridge = 1 - np.abs(r - 0.5) * 2
    fiss = np.clip((ridge - 0.86) / 0.1, 0, 1)                  # 裂纹
    holes = np.zeros((n, n))
    pts = (rng.random((int(n * n / 120), 2)) * n).astype(int)
    holes[pts[:, 1] % n, pts[:, 0] % n] = 1.0
    pits = gaussian_blur_periodic(holes, 1.1)
    pits /= max(pits.max(), 1e-12)                              # 针孔
    fine = periodic_noise(n, 1.0, seed + 2, fmin=60)
    height = 0.55 * groove - 0.35 * fiss - 0.6 * pits + 0.05 * fine
    # 对比度刻意压低：吊顶在多数机位占大片画面，针孔/裂纹太显会读成噪点（实拍矿棉板远看几乎是平的）
    alb = 0.95 - 0.06 * fiss - 0.14 * pits - 0.10 * (1 - groove) + 0.02 * (fine - 0.5)
    return np.repeat(np.clip(alb, 0, 1)[..., None], 3, -1), normal_from_height(height, strength=4.0)

def make_floor(ao, n=2048, seed=31, tiles=4, gap_m=0.003, tile_m=0.6):
    """600mm 米白抛光瓷砖（4×4 块/张）：反照率 sRGB + 粗糙度。ao 为 Blender 烘焙的 AO（行0=顶，同尺寸）。"""
    rng = np.random.default_rng(seed)
    y, x = (np.mgrid[0:n, 0:n] + 0.5) / n
    tx = np.floor(x * tiles).astype(int) % tiles
    ty = np.floor(y * tiles).astype(int) % tiles
    fx = (x * tiles) % 1.0; fy = (y * tiles) % 1.0
    half_gap = gap_m / tile_m / 2.0
    grout = np.minimum(np.minimum(fx, 1 - fx), np.minimum(fy, 1 - fy)) < half_gap
    tone = rng.normal(0, 0.025, (tiles, tiles))[ty, tx]          # 每块砖 ±2.5% 色差
    mott = periodic_noise(n, 2.6, seed + 1, fmin=2, fmax=60) - 0.5
    speck = periodic_noise(n, 0.3, seed + 2, fmin=300) - 0.5
    base = np.array([0.80, 0.78, 0.74])
    lum = 1 + tone + mott * 0.05 + speck * 0.03
    alb = base[None, None, :] * lum[..., None]
    alb = np.where(grout[..., None], np.array([0.55, 0.53, 0.50]), alb)
    alb = alb * (0.65 + 0.35 * np.asarray(ao))[..., None]
    wear = periodic_noise(n, 2.0, seed + 3, fmin=1, fmax=12)
    rough = np.where(grout, 0.88, 0.28 + 0.14 * wear ** 2 + (speck + 0.5) * 0.03)
    return np.clip(alb, 0, 1), np.clip(rough, 0, 1)

def grade_to_mean(img_srgb, target_srgb):
    """逐通道在线性空间缩放，使平均色等于目标（保留木纹明暗对比）。"""
    lin = srgb_to_linear(img_srgb)
    tgt = srgb_to_linear(np.asarray(target_srgb, np.float64))
    for _ in range(12):            # 提亮会把最亮的木纹截到 1 → 均值偏低；迭代补偿到目标
        lin = np.clip(lin * (tgt / np.maximum(lin.mean(axis=(0, 1)), 1e-6))[None, None, :], 0, 1)
    return linear_to_srgb(lin)
