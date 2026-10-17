#!/bin/zsh
# 一键重新生成全部烘焙数据并写入 classroom_v4_3.html。
# 用法：bake/run_all.sh          （完整：约 20 分钟，其中 GI 4096 采样约 13 分钟；首次另加 ~2.5 分钟 Metal 内核编译）
#       bake/run_all.sh --quick  （64 采样快速版，几分钟，用于验证流程）
set -euo pipefail
cd "$(dirname "$0")/.."
BL=/Applications/Blender.app/Contents/MacOS/Blender
QUICK=()
[[ "${1:-}" == "--quick" ]] && QUICK=(--quick)
node bake/build_exporter.mjs
python3 bake/fetch_polyhaven.py
$BL -b --factory-startup -P bake/blender_floor.py
python3 bake/pack_textures.py
python3 bake/embed.py                       # 先写贴图：导出时反照率要用新贴图
node bake/export_scene.mjs
$BL -b --factory-startup -P bake/blender_gi.py -- "${QUICK[@]}"
python3 bake/pack_gi.py
python3 bake/embed.py
ls -la classroom_v4_3.html
