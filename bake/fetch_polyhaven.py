#!/usr/bin/env python3
"""下载课桌/椅子用的两套 Poly Haven 实拍木纹（CC0，dl.polyhaven.org）。已存在则跳过。
用 curl 而不是 urllib：python.org 版 Python 在 macOS 上常缺根证书。"""
import json, subprocess
from pathlib import Path

DIR = Path(__file__).resolve().parent / 'assets' / 'polyhaven'
ASSETS = ['ash_veneer', 'plywood']
MAPS = {'Diffuse': 'diff', 'nor_gl': 'nor_gl', 'Rough': 'rough'}

def curl_json(url):
    return json.loads(subprocess.run(['curl', '-fsSL', url], check=True, capture_output=True).stdout)

def main():
    DIR.mkdir(parents=True, exist_ok=True)
    for a in ASSETS:
        files = curl_json(f'https://api.polyhaven.com/files/{a}')
        for key, short in MAPS.items():
            dst = DIR / f'{a}_{short}_2k.jpg'
            if dst.exists() and dst.stat().st_size > 0:
                continue
            url = files[key]['2k']['jpg']['url']
            print('下载', url)
            subprocess.run(['curl', '-fsSL', url, '-o', str(dst)], check=True)
    for p in sorted(DIR.glob('*.jpg')):
        print(f'{p.name:28s} {p.stat().st_size // 1024:6d} KB')

if __name__ == '__main__':
    main()
