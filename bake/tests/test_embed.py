import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import embed as E

HTML = '<html><body>\n<script>var a=1;</script>\n</body></html>\n'

class TestEmbed(unittest.TestCase):
    def test_insert_then_replace_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'x.html'; p.write_text(HTML, encoding='utf-8')
            payload = {'version': 1, 'textures': {'meta': {}, 'floor_albedo': 'data:image/webp;base64,AAAA'}, 'gi': None}
            E.embed(p, payload); once = p.read_text(encoding='utf-8')
            E.embed(p, payload); twice = p.read_text(encoding='utf-8')
            self.assertEqual(once, twice)
            self.assertEqual(once.count('<script id="bakedData">'), 1)
            self.assertLess(once.index('bakedData'), once.index('</body>'))
            self.assertIn('var a=1;', once)

    def test_block_is_script_safe_json(self):
        block = E.render_block({'version': 1, 'textures': None, 'gi': {'meta': {'s': 'a</b'}, 'atlas': 'x'}})
        body = block[len(E.BEGIN):-len(E.END)]
        self.assertNotIn('</', body)
        js = body.split('window.BAKED = ', 1)[1].rsplit(';', 1)[0]
        self.assertEqual(json.loads(js)['gi']['meta']['s'], 'a</b')

    def test_marker_text_inside_other_script_is_left_alone(self):
        # 回归：模块注释里出现了 <script id="bakedData"> 字样，embed 曾把整段模块代码当成数据块替换掉
        html = ('<html><body>\n<script>\n// 数据在文件末尾 <script id="bakedData">\nvar keep = 42;\n</script>\n'
                '</body></html>\n')
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'x.html'; p.write_text(html, encoding='utf-8')
            payload = {'version': 1, 'textures': None, 'gi': None}
            E.embed(p, payload); E.embed(p, payload)
            out = p.read_text(encoding='utf-8')
            self.assertIn('var keep = 42;', out)
            self.assertEqual(out.count('window.BAKED'), 1)
            self.assertLess(out.index('var keep = 42;'), out.index('window.BAKED'))

if __name__ == '__main__':
    unittest.main()
