import json, sys, tempfile, unittest
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi_lib as G
import pack_gi

class TestPackGi(unittest.TestCase):
    def test_pack_synthetic(self):
        vols = G.volumes(); _, n = G.probe_offsets(vols)
        with tempfile.TemporaryDirectory() as d:
            out = Path(d); raw = out / 'gi_raw'; raw.mkdir()
            valid = np.ones(n, bool); valid[100:140] = False
            for gi, g in enumerate(G.GROUPS):
                E = np.full((n, 6, 3), float(gi + 1), np.float32); E[100:140] = 1e6   # 坏探针里是垃圾值
                np.save(raw / f'{g}.npy', E)
            np.save(raw / 'valid.npy', valid)
            (raw / 'bake_info.json').write_text(json.dumps(dict(groups=G.GROUPS, samples=8, quick=True, n_probes=n,
                                                                sunKeys=[[1, -1, 0]] * 9)))
            pack_gi.main(out)
            meta = json.loads((out / 'gi.json').read_text())
            big = np.asarray(Image.open(out / 'gi_atlas.png').convert('RGB'))
            L = meta['atlas']
            self.assertEqual(big.shape, (L['rows'] * L['H'], L['cols'] * L['W'], 3))
            for gi in [0, 5, 12]:
                r, c = divmod(gi, L['cols'])
                cell = big[r * L['H']:(r + 1) * L['H'], c * L['W']:(c + 1) * L['W']]
                v = G.decode_log(cell[3, 3, 0], meta['scales'][gi])
                self.assertAlmostEqual(float(v), gi + 1, delta=(gi + 1) * 0.03)   # 坏探针已被邻居填补，不是 1e6
            self.assertEqual(meta['groups'], G.GROUPS)
            self.assertEqual(meta['invalid'], 40)

if __name__ == '__main__':
    unittest.main()
