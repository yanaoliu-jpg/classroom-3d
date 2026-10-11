import sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tex_lib as X

class TestTexLib(unittest.TestCase):
    def test_periodic_noise_is_seamless(self):
        n = X.periodic_noise(256, 2.0, seed=1, fmin=2, fmax=40)
        self.assertEqual(n.shape, (256, 256))
        self.assertAlmostEqual(float(n.min()), 0.0, places=6)
        self.assertAlmostEqual(float(n.max()), 1.0, places=6)
        self.assertLess(X.seam_ratio(n), 1.6)

    def test_seam_ratio_detects_seam(self):
        ramp = np.tile(np.linspace(0, 1, 256), (256, 1))      # 左黑右白 → 首尾强跳变
        self.assertGreater(X.seam_ratio(ramp), 20)

    def test_normal_orientation(self):
        # 高度向右(+u)升高 → 法线朝 -u 倾斜（红 < 0.5）
        h = np.tile(np.sin(np.linspace(0, 2 * np.pi, 64, endpoint=False)), (64, 1))
        n = X.normal_from_height(h, 4.0)
        col = 16                                              # sin 上升段
        self.assertLess(n[10, col, 0], 0.5)
        # 高度向图像上方(行号变小 = +v)升高 → 法线朝 -v 倾斜（绿 < 0.5）
        hv = np.tile(np.cos(np.linspace(0, 2 * np.pi, 64, endpoint=False))[:, None], (1, 64))
        nv = X.normal_from_height(hv, 4.0)
        row = 16                                              # cos 在此处随行号增加而下降 → 向上(行号减小)升高
        self.assertLess(nv[row, 10, 1], 0.5)
        self.assertTrue(np.all(n[..., 2] > 0.5))

    def test_srgb_roundtrip(self):
        x = np.linspace(0, 1, 101)
        self.assertLess(np.abs(X.srgb_to_linear(X.linear_to_srgb(x)) - x).max(), 1e-9)

    def test_wall_is_subtle_and_seamless(self):
        a, n = X.make_wall(256, seed=3)
        self.assertEqual(a.shape, (256, 256, 3))
        self.assertLess(abs(float(a.mean()) - 0.97), 0.01)
        self.assertLess(float(a.max() - a.min()), 0.08)
        self.assertGreater(float((n[..., 2] * 2 - 1).mean()), 0.97)   # 法线几乎朝外：只是微纹
        self.assertLess(X.seam_ratio(n[..., 0]), 1.6)

    def test_floor_grout_darker_and_tiles_shiny(self):
        # 必须用实际分辨率 2048：3mm 缝在 512px（4.7mm/像素）下不到一个像素宽
        ao = np.ones((2048, 2048))
        alb, rough = X.make_floor(ao, n=2048, seed=5)
        lum = alb.mean(-1)
        grout = lum[0, :].mean()                 # 第 0 行正好落在缝上（半缝在贴图边沿）
        tile = lum[256, 256]
        self.assertLess(grout, tile * 0.85)
        self.assertGreater(rough[0, 5], 0.8)     # 缝哑
        self.assertLess(rough[256, 256], 0.5)    # 砖面光
        self.assertLess(X.seam_ratio(lum), 1.6)

    def test_grade_to_mean(self):
        img = np.random.default_rng(0).random((64, 64, 3))
        g = X.grade_to_mean(img, [0.70, 0.54, 0.36])
        lin_mean = X.srgb_to_linear(g).mean(axis=(0, 1))
        self.assertTrue(np.allclose(lin_mean, X.srgb_to_linear(np.array([0.70, 0.54, 0.36])), atol=0.01))

if __name__ == '__main__':
    unittest.main()
