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
        # 实时点光源的截断距离/衰减指数（three.js distance/decay）：Cycles 侧用同一窗函数（add_point cutoff），
        # 烘焙的间接光与 CORR_D 直射才与实时直射一致；窗函数仿真只对 decay=2（= Cycles 的平方反比）成立
        self.assertAlmostEqual(m['lights']['ceilDistance'], 9.0)
        self.assertAlmostEqual(m['lights']['corrDistance'], 4.2)
        self.assertEqual((m['lights']['ceilDecay'], m['lights']['corrDecay']), (2, 2))
        self.assertRegex(m['fingerprint'], r'^[0-9a-f]{8}$')        # 几何指纹：随烘焙数据一起进 HTML，运行时比对
        self.assertEqual([k['angle'] for k in m['sunKeys']], list(range(-80, 81, 20)))
        for k in m['sunKeys']:
            self.assertLess(k['dir'][1], 0)          # 光从上往下照
            self.assertGreater(k['dir'][0], 0)       # 太阳恒在左窗外(-x)，光朝 +x
        self.assertGreater(m['stats']['meshes'] + m['stats']['instances'], 500)
        self.assertEqual(set(m['views']), {'5', '6', '7', '9', '0'})
        # 左墙三扇朝外的窗（Cycles 天光门户用）：中心 x=-7、z=0/4/8，3.3×2.6m，法线朝室内 +x
        self.assertEqual([round(w['center'][2], 3) for w in m['windows']], [0.0, 4.0, 8.0])
        for w in m['windows']:
            self.assertAlmostEqual(w['center'][0], -7.0); self.assertEqual(w['normal'], [1, 0, 0])
            self.assertAlmostEqual(w['w'], 3.3); self.assertAlmostEqual(w['h'], 2.6)

if __name__ == '__main__':
    unittest.main()
