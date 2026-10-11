# bake/ — Cycles 烘焙全局光照 + 材质管线

用 Blender Cycles（Python 驱动、后台运行）把教室的**间接光**和**材质贴图**离线算好，写进
`classroom_v4_3.html` 末尾的 `<script id="bakedData">` 数据块。实时端只做查表与线性叠加，
直射光（太阳、吊顶灯、走廊灯）仍是实时的。设计与决策见
`docs/superpowers/specs/2026-10-11-cycles-baked-gi-materials-design.md`（校准结果在第 9 节）。

## 一键重烘

```bash
bake/run_all.sh          # 完整：约 20 分钟（GI 4096 采样约 13 分钟；首次另加 ~2.5 分钟 Metal 内核编译）
bake/run_all.sh --quick  # 64 采样快速版，几分钟，只用于验证流程（画面会有噪点）
```

跑完 HTML 已更新，直接打开即可。缺数据块或解码失败时页面自动回退到改前画面。

**什么时候必须重烘**：改了房间几何（墙、窗洞、门、讲台、课桌位置）、灯位、点光源的
`distance`/`decay`、太阳轨迹公式、主要材质的反照率（影响反弹光颜色）之后。
只改灯的**强度/颜色**、预设、天气、时间轴不需要重烘——这些只改运行时权重。

烘焙数据里存了几何指纹（受光网格的包围盒 + 灯位 + 截断距离，5cm 精度）。页面加载时若控制台出现
`[GI] 烘焙数据与当前几何不一致…`，说明改过房间/家具/灯位而没重烘——画面仍能用，但间接光可能漏光或有黑斑，跑一遍 `run_all.sh` 即可。

## 依赖

- Blender 5.2（`/Applications/Blender.app`）、Google Chrome（无头模式，导出/截图/测试用）
- Node ≥ 22（用内置 WebSocket / fetch，无 npm 依赖；GLTFExporter 由 `vendor/node_modules` 里的 esbuild 打包）
- Python 3 + numpy + Pillow

## 文件

| 文件 | 职责 |
|---|---|
| `cdp.mjs` | 无依赖 CDP 小工具：启动无头 Chrome、导航、执行 JS、取画布 PNG |
| `three-global.cjs`、`exporter-entry.mjs`、`build_exporter.mjs` | 把 GLTFExporter 打包成使用页面 `window.THREE` 的 IIFE |
| `export_in_page.js` | 在页面内执行：筛真实几何、展开实例、导出 GLB、收集元数据（灯位/截断距离/窗洞/太阳关键帧/机位） |
| `export_scene.mjs` | 导出入口：`out/scene.glb` + `out/scene_meta.json` |
| `fetch_polyhaven.py` | 下载两套木纹原图（已存在则跳过） |
| `blender_floor.py` | Blender：倒角瓷砖几何 → 烘焙法线/AO |
| `tex_lib.py`、`pack_textures.py` | numpy 程序化贴图（墙漆/吸音板/地砖反照率与粗糙度）、木纹调色、WebP 输出 |
| `embed.py` | 把贴图与 GI 数据写入 HTML 末尾数据块（幂等，整块替换） |
| `gi_lib.py` | 探针网格、图集布局、对数编码、坏探针修补、水平平滑（Blender 与系统 Python 共用） |
| `blender_common.py`、`blender_gi.py` | Blender：导入、灯光分组、探针、逐组 Cycles 烘焙 |
| `pack_gi.py` | 原始探针 → `out/gi_atlas.png` + `out/gi.json` |
| `capture_views.mjs`、`blender_reference.py`、`compare.py` | 同机位截图 / Cycles 参考图 / 三联图与偏差统计（校准用） |
| `bench.mjs` | 帧率基准（改前 vs 改后） |
| `run_all.sh`、`README.md` | 一键重烘 + 本说明 |
| `tests/*` | 单测与集成测试 |

生成物都在 `out/`（git 忽略）；Poly Haven 原图在 `assets/polyhaven/`（git 忽略）。

## 光照分组与单位约定

13 组，每组按"单位强度、白光"烘一份，运行时乘当前强度×颜色相加（`giComputeWeights`）：
`SKY`（均匀天空 L=1，直接+间接，窗洞放 Cycles 门户降噪）、`CEIL`（12 盏吊顶灯，仅间接）、
`CORR_D`/`CORR_I`（8 盏走廊灯，直接/间接；相机进走廊时 `CORR_D` 让位给实时走廊灯）、
`SUN_0…8`（太阳 −80°…80° 每 20°，仅间接，按方位插值）。

| three.js | Blender | 说明 |
|---|---|---|
| `DirectionalLight.intensity = E` | Sun `strength = E` | |
| `PointLight.intensity = I`，`distance = R`，`decay = 2` | Point `power = 4π·I` + `add_point(cutoff=R)` | three.js 在 1/d² 外再乘 `saturate(1-(d/R)^4)^2`；Cycles 用灯光节点（Light Path → Ray Length）复现，误差 ≤0.6% |
| 辐照度 E | Cycles 漫反射通道 × π | 探针读数 = E/π |
| 坐标 (x, y, z) | (x, −z, y) | glTF 导入自动换算 |

天光绝对尺度 `GI_SKY_SCALE = 4/π`（HTML 里），由参考图校准得出。

## 校准 / 对比

```bash
node bake/capture_views.mjs                     # 18 个 case 的 改后/改前 截图 + 相机与灯光状态 → out/views/
blender -b --factory-startup -P bake/blender_reference.py [-- --only noon_7,noon_5]   # 同机位同灯光 Cycles 参考图
python3 bake/compare.py                         # 三联图 → docs/superpowers/compare/cyclesgi_*.png + 偏差表
node bake/capture_views.mjs --tonemap agx && python3 bake/compare.py --agx   # ACES | AgX 对比图
node bake/capture_views.mjs --only after --tune '{"skyScale":1.27,"moon":0}'  # 经 __GI.tune 试参数
node bake/bench.mjs <html> <out.json>          # 帧率
```

`__GI.tune({skyScale, fluoroGlow, corrGlass, contact, moon, winPatch, floorFx})` 只在校准时经 CDP 调用，
不进 UI、不存档；各开关只"关"不"开"（恢复页面自己的可见性）。

## 测试

```bash
python3 -m unittest discover -s bake/tests -p 'test_*.py'   # 含一个调 Blender 的截断衰减测试（无 Blender 时跳过）
node --test bake/tests/*.test.mjs                            # 无头 Chrome 运行时集成测试
```

## 许可

木纹原图来自 Poly Haven（`ash_veneer`、`plywood`，2K），**CC0**，可自由使用、无需署名。
