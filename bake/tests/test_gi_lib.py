import sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi_lib as G

class TestGrid(unittest.TestCase):
    def test_index_order_x_fastest(self):
        v = G.volumes()[0]; c = G.grid_centers(v); ny = len(G.LAYERS)
        self.assertEqual(len(c), v['nx'] * ny * v['nz'])
        dx = c[1] - c[0]
        self.assertGreater(dx[0], 0); self.assertAlmostEqual(dx[1], 0); self.assertAlmostEqual(dx[2], 0)
        self.assertAlmostEqual(c[v['nx']][1], G.LAYERS[1])                 # 下一行 = 下一层
        self.assertGreater(c[v['nx'] * ny][2], c[0][2])                    # 下一片 = z 增加

    def test_volumes_inside_walls(self):
        for v in G.volumes():
            (bx0, by0, bz0), (bx1, by1, bz1) = v['box']
            self.assertTrue(bx0 < v['x0'] < v['x1'] < bx1)
            self.assertTrue(bz0 < v['z0'] < v['z1'] < bz1)
            self.assertTrue(by0 < G.LAYERS[0] and G.LAYERS[-1] < by1)

    def test_layer_coord(self):
        self.assertEqual(G.layer_coord(-1.0), 0.0)
        self.assertEqual(G.layer_coord(G.LAYERS[3]), 3.0)
        mid = (G.LAYERS[3] + G.LAYERS[4]) / 2
        self.assertAlmostEqual(G.layer_coord(mid), 3.5)
        self.assertEqual(G.layer_coord(9.0), float(len(G.LAYERS) - 1))

class TestAtlas(unittest.TestCase):
    def test_layout_no_overlap_and_fits(self):
        vols = G.volumes(); L = G.atlas_layout(vols)
        self.assertLessEqual(L['W'], 504)
        self.assertLessEqual(L['W'] * L['cols'], 2048); self.assertLessEqual(L['H'] * L['rows'], 2048)
        used = np.zeros((L['H'], L['W']), np.int32)
        for v, reg in zip(vols, L['regions']):
            for f in range(6):
                for iz in range(v['nz']):
                    x, y = G.tile_origin(reg, f, iz, v['nz'])
                    used[y:y + reg['th'], x:x + reg['tw']] += 1
        self.assertEqual(int(used.max()), 1)

    def test_pack_unpack_roundtrip(self):
        vols = G.volumes(); L = G.atlas_layout(vols); _, n = G.probe_offsets(vols)
        E = np.random.default_rng(0).random((n, 6, 3)).astype(np.float32)
        A = G.pack_atlas(E, vols, L); offs, _ = G.probe_offsets(vols); ny = len(G.LAYERS)
        for vi, (ix, iy, iz, f) in [(0, (0, 0, 0, 0)), (0, (35, 9, 52, 5)), (1, (4, 3, 64, 2)), (1, (0, 9, 0, 3))]:
            v = vols[vi]; idx = offs[vi] + (iz * ny + iy) * v['nx'] + ix
            self.assertTrue(np.allclose(G.unpack_probe(A, vols, L, vi, ix, iy, iz, f), E[idx, f]))

class TestCodec(unittest.TestCase):
    def test_log_roundtrip_relative_error(self):
        s = 7.0; x = s * np.logspace(-2, 0, 200)
        y = G.decode_log(G.encode_log(x, s), s)
        self.assertLess(float(np.max(np.abs(y - x) / x)), 0.03)
        self.assertEqual(int(G.encode_log(np.array([0.0]), s)[0]), 0)
        self.assertEqual(int(G.encode_log(np.array([2 * s]), s)[0]), 255)   # 超范围截断
        self.assertAlmostEqual(float(G.decode_log(np.array([255]), s)[0]), s)

class TestFill(unittest.TestCase):
    def test_fill_invalid_from_neighbours(self):
        E = np.full((6, 5, 7, 6, 3), 5.0); valid = np.ones((6, 5, 7), bool)
        valid[2:4, 1:3, 2:5] = False; E[~valid] = 999.0
        out, ok = G.fill_invalid(E, valid)
        self.assertTrue(ok.all()); self.assertTrue(np.allclose(out, 5.0))

    def test_no_valid_neighbours_becomes_zero(self):
        E = np.full((2, 2, 2, 6, 3), 3.0); valid = np.zeros((2, 2, 2), bool)
        out, ok = G.fill_invalid(E, valid)
        self.assertFalse(ok.any()); self.assertTrue(np.all(out == 0))

class TestAmbientCube(unittest.TestCase):
    def test_axis_and_diagonal(self):
        c6 = np.array([[1, 0, 0], [2, 0, 0], [3, 0, 0], [4, 0, 0], [5, 0, 0], [6, 0, 0]], float)
        self.assertEqual(G.ambient_cube(c6, [0, -1, 0])[0], 4)
        n = np.array([1, 1, 0]) / np.sqrt(2)
        self.assertAlmostEqual(G.ambient_cube(c6, n)[0], 0.5 * 1 + 0.5 * 3)

if __name__ == '__main__':
    unittest.main()
