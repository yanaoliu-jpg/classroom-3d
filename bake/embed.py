#!/usr/bin/env python3
"""把 bake/out 里的贴图与 GI 数据整块写进 HTML 末尾的 <script id="bakedData">。可重复执行，结果一致。"""
import base64, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / 'out'
BEGIN = '<script id="bakedData">'
END = '</script>'
MIME = {'.webp': 'image/webp', '.png': 'image/png'}

def data_uri(p):
    return f'data:{MIME[p.suffix]};base64,' + base64.b64encode(p.read_bytes()).decode()

def build_payload(out=OUT):
    payload = {'version': 1, 'textures': None, 'gi': None}
    tj = out / 'tex' / 'tex.json'
    if tj.exists():
        meta = json.loads(tj.read_text())
        tex = {'meta': meta}
        for kind, d in meta.items():
            for slot in ('albedo', 'normal', 'rough'):
                if slot in d:
                    tex[f'{kind}_{slot}'] = data_uri(out / 'tex' / d[slot])
        payload['textures'] = tex
    gj = out / 'gi.json'
    if gj.exists():
        payload['gi'] = {'meta': json.loads(gj.read_text()), 'atlas': data_uri(out / 'gi_atlas.png')}
    return payload

def render_block(payload):
    js = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    return (BEGIN + '\n// 由 bake/embed.py 生成，勿手改。重新生成：bake/run_all.sh\nwindow.BAKED = '
            + js + ';\n' + END)

def embed(html_path, payload):
    html_path = Path(html_path)
    s = html_path.read_text(encoding='utf-8')
    block = render_block(payload)
    # 只认"独占一行开头"的标签，且取最后一个：别的脚本注释里可能出现同样字样（曾因此把整段模块代码替换掉）
    i = s.rfind('\n' + BEGIN)
    if i >= 0:
        i += 1
        j = s.find(END, i)
        s = s[:i] + block + s[j + len(END):]
    else:
        k = s.rfind('</body>')
        s = s[:k] + block + '\n' + s[k:]
    tmp = html_path.with_suffix('.tmp')
    tmp.write_text(s, encoding='utf-8')
    tmp.replace(html_path)
    return len(block)

if __name__ == '__main__':
    html = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'classroom_v4_3.html'
    n = embed(html, build_payload())
    print(f'bakedData 写入 {html.name}：{n / 1e6:.2f} MB')
