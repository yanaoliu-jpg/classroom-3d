import json, struct, unittest
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'out'

class TestExport(unittest.TestCase):
    def test_glb_header(self):
        b = (OUT / 'scene.glb').read_bytes()
        magic, ver, length = struct.unpack('<4sII', b[:12])
        self.assertEqual(magic, b'glTF')
        self.assertEqual(ver, 2)
        self.assertEqual(length, len(b))

    def test_meta(self):
        m = json.loads((OUT / 'scene_meta.json').read_text())
        self.assertEqual(len(m['lights']['ceil']), 12)
        self.assertEqual(len(m['lights']['corr']), 8)
        self.assertEqual([k['angle'] for k in m['sunKeys']], list(range(-80, 81, 20)))
        for k in m['sunKeys']:
            self.assertLess(k['dir'][1], 0)          # 光从上往下照
            self.assertGreater(k['dir'][0], 0)       # 太阳恒在左窗外(-x)，光朝 +x
        self.assertGreater(m['stats']['meshes'] + m['stats']['instances'], 500)
        self.assertEqual(set(m['views']), {'5', '6', '7', '9', '0'})

if __name__ == '__main__':
    unittest.main()
