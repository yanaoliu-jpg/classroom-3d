import json, sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi_lib as G

RAW = Path(__file__).resolve().parents[1] / 'out' / 'gi_raw'

class TestGiRaw(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.info = json.loads((RAW / 'bake_info.json').read_text())
        cls.vols = G.volumes(); cls.C = G.all_centers(cls.vols)
        cls.offs, cls.n = G.probe_offsets(cls.vols)
        cls.valid = np.load(RAW / 'valid.npy')
        cls.room = np.arange(cls.n) < cls.offs[1]

    def load(self, g):
        E = np.load(RAW / f'{g}.npy'); self.assertEqual(E.shape, (self.n, 6, 3))
        self.assertTrue(np.isfinite(E).all()); self.assertGreaterEqual(float(E.min()), 0.0)
        return E

    def test_all_groups_present(self):
        self.assertEqual(self.info['groups'], G.GROUPS)

    def test_sky_enters_through_left_windows(self):
        E = self.load('SKY'); C = self.C; mid = (C[:, 1] > 1.0) & (C[:, 1] < 2.1) & self.room & self.valid
        near = E[mid & (C[:, 0] < -5.0), 1].mean()     # -X 面：朝向窗户
        far = E[mid & (C[:, 0] > 5.0), 1].mean()
        self.assertGreater(near, 3 * far)

    def test_corridor_direct_lives_in_corridor(self):
        E = self.load('CORR_D').sum(axis=(1, 2))
        self.assertGreater(E[~self.room].mean(), 10 * E[self.room].mean())

    def test_ceiling_bounce_positive(self):
        E = self.load('CEIL')
        self.assertGreater(E[self.room & self.valid].mean(), 0.0)

    def test_sun_bounce_brightens_ceiling_near_windows(self):
        E = self.load('SUN_1')                         # -60°：晨光低斜入窗
        C = self.C; top = (C[:, 1] > 3.0) & self.room & self.valid
        near = E[top & (C[:, 0] < -4.0), 3].mean()     # -Y 面：朝下看被晒亮的地面
        far = E[top & (C[:, 0] > 4.0), 3].mean()
        self.assertGreater(near, far)

    def test_podium_interior_probes_invalid(self):
        C = self.C
        inside = self.room & (np.abs(C[:, 0]) < 1.3) & (C[:, 2] > -3.15) & (C[:, 2] < -2.45) & (C[:, 1] > 0.2) & (C[:, 1] < 0.9)
        self.assertTrue(inside.any())
        self.assertFalse(self.valid[inside].any())
        self.assertGreater(self.valid.mean(), 0.85)

if __name__ == '__main__':
    unittest.main()
