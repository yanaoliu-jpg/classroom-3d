import subprocess, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parent
BLENDER = Path('/Applications/Blender.app/Contents/MacOS/Blender')

@unittest.skipUnless(BLENDER.exists(), '需要 Blender')
class TestBlenderLights(unittest.TestCase):
    def test_point_light_cutoff_matches_threejs_window(self):
        r = subprocess.run([str(BLENDER), '-b', '--factory-startup', '-P', str(HERE / 'blender_falloff_check.py')],
                           capture_output=True, text=True, timeout=600)
        lines = [l for l in r.stdout.splitlines() if l.startswith('FALLOFF')]
        self.assertIn('FALLOFF OK', lines, '\n'.join(lines) or r.stdout[-2000:] + r.stderr[-2000:])

if __name__ == '__main__':
    unittest.main()
