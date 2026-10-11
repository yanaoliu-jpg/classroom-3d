import sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare as C

class TestCompare(unittest.TestCase):
    def test_aces_matches_threejs_reference_points(self):
        # three.js ACESFilmicToneMapping(exposure=1)：0 → 0；极亮 → 接近白
        out = C.aces_srgb(np.array([[[0.0, 0.0, 0.0], [100.0, 100.0, 100.0]]]), 1.0)
        self.assertEqual(out[0, 0].tolist(), [0, 0, 0])
        self.assertTrue(np.all(out[0, 1] >= 250))
        mid = C.aces_srgb(np.array([[[0.18, 0.18, 0.18]]]), 1.0)[0, 0, 0]
        self.assertTrue(100 < mid < 160)

    def test_grid_log_error_zero_for_identical(self):
        a = (np.random.default_rng(0).random((90, 160, 3)) * 255).astype(np.uint8)
        self.assertAlmostEqual(C.grid_log_error(a, a), 0.0)
        self.assertGreater(C.grid_log_error(a, (a * 0.5).astype(np.uint8)), 0.5)

    def test_agx_sheet_pairs_aces_and_agx_side_by_side(self):
        import tempfile
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            for c, v in (('noon_5', 100), ('dusk_5', 50)):
                Image.new('RGB', (64, 36), (v, v, v)).save(t / f'{c}_after.png')
                Image.new('RGB', (64, 36), (v + 40, v, v)).save(t / f'{c}_after_agx.png')
            Image.new('RGB', (64, 36)).save(t / 'night_5_after.png')          # 缺 AgX 版的 case 跳过
            old = C.VIEWS, C.DOCS
            C.VIEWS, C.DOCS = t, t
            try:
                path = C.agx_sheet(['noon_5', 'dusk_5', 'night_5'])
            finally:
                C.VIEWS, C.DOCS = old
            im = np.asarray(Image.open(path).convert('RGB'))
            self.assertEqual(im.shape, (2 * (36 + 28), 128, 3))
            self.assertEqual(im[28 + 10, 10].tolist(), [100, 100, 100])         # 左 ACES
            self.assertEqual(im[28 + 10, 64 + 10].tolist(), [140, 100, 100])    # 右 AgX

if __name__ == '__main__':
    unittest.main()
