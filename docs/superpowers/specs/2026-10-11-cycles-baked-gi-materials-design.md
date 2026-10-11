# Cycles 烘焙全局光照 + 材质升级 — 设计文档

日期：2026-10-11
分支：`feat/cycles-baked-gi`
文件：`classroom_v4_3.html`（单文件 three.js r164）+ 新增 `bake/` 离线工具目录

---

## 1. 目标与成功标准

**目标**：用 Blender Cycles（Python 驱动、后台运行）把教室的光照与材质"离线算好"，回灌进实时模拟器，
让实时画面在质感上向 Cycles 路径追踪参考图靠拢。

**成功标准**

| # | 标准 | 怎么验 |
|---|---|---|
| S1 | 同机位下，实时画面比改前更接近 Cycles 参考图 | 三联图（改前 / 改后 / 参考）+ 分区域亮度偏差（天花板近窗/远窗、墙面、桌下地面、走廊） |
| S2 | 帧率 ≥ 改前 | `性能优化计划.md` 里的 readPixels 强制同步计时；4 预设 × 5 机位 + 监控墙 |
| S3 | 交互全部保留 | 预设、时间轴、天气、三组灯光滑块、机位、监控墙、R 报告工具、URL 复现链接 |
| S4 | 仍是单个 HTML 直接打开 | 离线数据内嵌；缺数据时自动回退到改前画面 |
| S5 | 不用任何补帧手段 | 无动态分辨率 / 运动模糊 / TAA / 帧生成（项目铁律） |

**非目标**：不重做几何与布局；不做"离线出片"功能（参考图只用于校准）；不做反射探针（列为后续）；不改 UI。

---

## 2. 现状诊断（改前截图：`docs/superpowers/baselines/cyclesgi_before__*.png`）

| 问题 | 严重度 | 根因 |
|---|---|---|
| 没有全局光照 | ★★★ | 阳光光斑不反弹；墙角/桌下无自然明暗过渡，暗部是均匀灰褐。现以 7 盏"GI 近似"聚光灯 + 半球光 + 环境光假补 —— 空间分布错误（角落和窗边一样亮），且占帧时间（灯数是本项目性能瓶颈） |
| 材质 | ★★☆ | `mkTex` 用正弦叠加当噪声：木纹是规则橙色条纹，饱和度过高；地砖/墙/顶 128–512px，重复感强。地砖实际是 0.29×0.46m 长方形（8 格贴图 ×repeat 6 铺 14×22m）。吊顶矿棉板无纹理 |
| 假贴片 | ★☆☆ | 灯具周围白色梯形光晕（`fluoroGlows`）、桌下径向渐变接触阴影、走廊面自发光（`corrGlowMats`）—— 平面感 |
| 几何 | — | 圆角盒、弯管桌椅已做，不是瓶颈 |

---

## 3. 决策记录

### D1 探针体积（irradiance volume），不用 lightmap
- 场景是运行时程序化生成的，1100+ 网格且大量 `InstancedMesh`：lightmap 需要逐实例唯一 UV、按网格序号映射回去，脆弱且数据量大（每组一套 2K 图）。
- 探针体积按**世界坐标**采样：不需要 UV、对 InstancedMesh 天然有效、改几何不会"错位"（最多变得不准，可重烘）。
- 代价：只表达低频间接光（0.4m 量级）。小尺度接触遮蔽继续由 GTAO + 接触阴影负责。

### D2 基底用"环境立方体"（ambient cube，±X ±Y ±Z 六面辐照度）
- 教室表面绝大多数轴对齐（墙/地/顶/桌面），环境立方体对轴对齐法线是**精确**的，对斜面平滑过渡。
- 求值：`E(n) = n.x²·C(±x) + n.y²·C(±y) + n.z²·C(±z)`（按法线分量符号选面）。

### D3 用 Cycles 烘焙"不可见探针小立方体"得到每面辐照度（已做可行性实验，结论如下）
- 每个探针 = 6 个朝外小方面，每面的 UV 只覆盖图集里一个像素中心；DIFFUSE 烘焙（direct/indirect，不含 color）一次得到全部探针。
- 可见性：探针对 camera/diffuse/glossy/transmission/shadow 全部不可见（**必须保留 volume_scatter 一项开着**，六项全关会被 Cycles 剔除 → 烘出全 0）。实测相邻探针互不遮挡。
- 实测读数：均匀天空 L=1 → 每面 1.000（理论 1）。即 **Cycles 漫反射通道 = E/π，运行时辐照度 E = π × 读数**。

### D4 单位换算（实验实测）
| three.js | Blender | 实测 |
|---|---|---|
| `DirectionalLight.intensity = E` | Sun `strength = E` | 0.31831 = 1/π ✔ |
| `PointLight/SpotLight.intensity = I`（E=I/d²） | Point/Spot `power = 4π·I` | 误差 0.2% ✔ |
| 自发光 `emissive × emissiveIntensity` | Emission strength 同值 | 直接对应 |
| 坐标 | Blender (x,y,z) = three (x, −z, y) | glTF 导入自动换算 |

### D5 光源分组 + 运行时线性叠加
光照对强度是线性的。每组按"单位强度、白光"烘一份，运行时乘以当前强度与颜色后相加：

| 组 | 烘焙内容 | 运行时权重（RGB） |
|---|---|---|
| `SKY` | 均匀天空 L=1（含室外地面反射）· 直接+间接 | 天空亮度 × 天空色（复用现有 skyLevel / 天气 wxFillMul / 灰化 / 夜间月色曲线） |
| `CEIL` | 12 盏吊顶点光源 · **仅间接** | `ceilLevel × CEIL_PERLIGHT × ceilColor` |
| `CORR_D` | 8 盏走廊点光源 · 直接 | 相机在教室：`corrLevel × 色`；相机在走廊：0（此时实时走廊灯接管直射） |
| `CORR_I` | 8 盏走廊点光源 · 间接 | `corrLevel × 色` |
| `SUN_k` (k=1..9) | 太阳 −80°…80° 每 20° · **仅间接** | 按当前太阳方向在相邻两帧间线性插值 × `mainLight.intensity × mainLight.color` |

- `SKY` 权重的统一定义：时间轴模式用 `dayPhase`，静态预设用现有 `PRESET_SKY_PHASE[预设]`（含 custom=0.34），
  两者走同一条 `skyLevel / sunHeight / warmK` 曲线（即现有时间轴里驱动半球光的那条），再乘天气的 `wxFillMul` 与灰化 `wxHemiGrey`；
  夜间收敛到暗蓝月色。绝对尺度先按"整体亮度与改前接近"定标，再看参考图微调。
- 天气、时间轴、预设、滑块只改权重（uniform），**不触发着色器重编**。
- 太阳关键帧按静态 `sync()` 的轨迹公式生成；时间轴模式的轨迹与之仰角略有差别，间接光是低频的，按方位插值即可。

### D6 只替换"间接光"，直射保持实时
- 太阳直射 + 阴影、吊顶灯直射（含高光）保持实时：锐利、跟手、零延迟。
- 在教室/走廊体积**内**：烘焙辐照度替换 半球光 + 环境光 + 环境贴图漫射（IBL 镜面反射保留）。体积**外**（室外视角 `0` 机位）保持原样。
- 内外判定用"沿法线外推 2cm 的点是否在体积内"——单面双面墙的室内面/室外面因此各走各的。

### D7 拆掉 11 盏假补光（仅在烘焙数据加载成功时）
窗光填充 `windowFills`×3、天花板反弹 `ceilBounce`×3、地面反弹 `floorBounce`×1、走廊高窗聚光 `winSpot`、门玻璃聚光 ×2、高窗面光源 `rWin`（RectAreaLight，最贵灯型）。
它们模拟的东西全部由 `SKY` / `SUN_k` / `CORR_*` 组物理地给出。灯数变化发生在加载期，不涉及运行时切换；
`warmUpShaderVariants` 预热的两种组合照常成立。

### D8 材质来源
| 部位 | 来源 | 说明 |
|---|---|---|
| 课桌面 | Poly Haven `ash_veneer`（CC0） | 实拍木纹，调成暖蜂蜜色、降饱和 |
| 椅面/椅背 | Poly Haven `plywood`（CC0） | 弯曲胶合板 |
| 地砖 | Blender 程序化 | 600×600 米白抛光瓷砖：每块色差、3mm 砖缝、抛光+磨损粗糙度；改成正方形砖 |
| 墙面 | Blender 程序化 | 乳胶漆滚涂微纹理（法线为主，反照率近乎均匀） |
| 吊顶板 | Blender 程序化 | 矿棉吸音板：针孔 + 裂纹 |
- 全部四方连续（程序化用 4D 噪声映射到环面保证无缝），WebP 内嵌。原始下载文件不进 git。
- GI 烘焙在新材质之后进行，反照率（影响反弹色）以新材质为准。

### D9 单文件
烘焙数据（GI 图集 + 贴图）写进 HTML **末尾**一个独立的 `<script id="bakedData">` 块，由 `bake/embed.py` 整块替换。
上方代码保持可读；缺这个块或解码失败 → 回退到改前画面（不打补丁、不拆灯、用旧贴图）。

---

## 4. 架构

### 4.1 离线管线（`bake/`，`bake/run_all.sh` 一键重跑）

```
classroom_v4_3.html
   │ ① export_scene.mjs   Node + CDP 驱动无头 Chrome（无 npm 依赖，用 Node 内置 WebSocket）
   │                      注入 GLTFExporter IIFE（vendor 里 esbuild 打包，只存在于工具中）
   ▼
bake/out/scene.glb + scene_meta.json   （真实几何 + 灯位/窗洞/机位/分组元数据）
   │ ② blender_textures.py  程序化材质 + Poly Haven 原图 → 四方连续 WebP
   │ ③ blender_gi.py        导入 → 材质/灯光分组 → 探针 → 逐组 Cycles 烘焙 → 坏探针修补 → 编码
   │ ④ blender_reference.py 同机位同灯光 Cycles 参考图（校准用）
   ▼
bake/out/gi.json + gi_*.png + tex_*.webp
   │ ⑤ embed.py  写入 HTML 末尾 <script id="bakedData">
   ▼
classroom_v4_3.html
```

**导出过滤规则**：只导出 `MeshStandardMaterial` 网格；跳过 `MeshBasicMaterial`（全是假贴片/光晕/标记）、
Points/Sprite/Line、不可见对象、透明度 < 0.5 的玻璃；`InstancedMesh` 展开成普通网格；
窗外遮光体保留（它们塑造阳光入射）。灯具自发光面在 Cycles 中置 0（灯由点光源代表，避免重复计光）。

### 4.2 探针网格

| 体积 | x | z | 水平间距 | 探针数 |
|---|---|---|---|---|
| 教室 | [−6.85, 6.85]（离墙内缩 0.15） | [−4.85, 15.85] | ≈0.4m | 36 × 53 × 10 层 |
| 走廊 | [7.15, 8.75] | [−4.35, 21.35] | ≈0.4m | 5 × 65 × 10 层 |

- **垂直 10 层非均匀**，层面紧贴主要水平面上方：地面、椅面（0.46）、桌面（0.76）、讲台面（≈1.14）、窗台（0.65）……
  这样桌面像素只会采到桌面**上方**的探针，避免把桌肚里的黑"漏"到桌面上。
  初始层高表 `[0.07, 0.28, 0.51, 0.81, 1.18, 1.55, 2.00, 2.50, 3.00, 3.36]`（吊顶板在 3.444）；
  实施时用参考图核对桌面/椅面/讲台面，必要时微调后重烘。
- 坏探针（落在桌子/讲台/柜机内部）：Blender `scene.ray_cast` 多方向检测背面命中 → 标记无效 → 用有效邻居迭代填补。
- 合计约 2.2 万探针 × 6 面 ≈ 13.4 万像素/组。

### 4.3 数据格式
- 每组一张 RGB8 PNG，对数编码 `enc = log2(1 + v/s·k) / log2(1+k)`（每组自带尺度 s，k≈256），相对精度 ~1–2%。
- `gi.json`：体积参数、层高表、图集布局、组列表与尺度、太阳关键帧角度、单位约定、几何指纹（用于提示"数据过期"）。

### 4.4 运行时

1. **解码**：base64 → Image → canvas → `DataTexture`（各组纵向堆叠成一张）。
2. **GPU 合成**：一个全屏 ShaderMaterial 把 `Σ 权重_g × decode(组_g)` 画进一张 HalfFloat 图集。
   仅在权重变化超过阈值时执行（静态时 0 开销；时间轴播放时每帧一次，约 13 万像素 × 13 次采样，可忽略）。
3. **着色器补丁**：`MeshStandardMaterial.prototype.onBeforeCompile`（覆盖全部 PBR 材质，含 InstancedMesh；
   缓存键对所有材质相同 → 不增加程序数量）。在 `lights_fragment_begin` 的半球光块之后：
   由视空间位置/法线换算世界坐标 → 判定体积 → 按法线符号选 3 面 × 2 层 = 6 次双线性采样 → 环境立方体求值 →
   `irradiance = mix(旧值, 烘焙值, 体积内)`；`lights_fragment_maps` 中体积内的 IBL 漫射置 0。
4. **权重接线**：在现有逻辑写完灯光状态之后（`applyWeatherLighting` 之后）统一计算 13 个权重。
   相机进出走廊时由现有 `applyCorridorLayer()` 一并切换 `CORR_D` 权重。
5. **假效果逐个评估**（对照参考图，冗余的仅在 GI 生效时关闭）：`fluoroGlows`、`corrGlowMats` 自发光、
   接触阴影、`floorMirror/floorHighlight`、窗光斑/光柱贴片、`moonLight`、`ceilFill/ceilBoost` 等补偿逻辑。
6. **色调映射**：保持 ACES；同时出一组 AgX 对比给用户选（Blender 默认即 AgX），不擅自切换。

---

## 5. 验证

- **基准截图**：4 预设 × 机位 5/6/7/9 + 走廊内一个机位，改前已存 `cyclesgi_before__*.png`。
- **参考图**：`blender_reference.py` 用导出的相机矩阵与 fov、与实时相同的灯光状态渲染 EXR，
  在 Python 里套用与 three.js 相同的色调映射与曝光后存 PNG，保证可比。
- **三联图**：改前 / 改后 / 参考，存 `docs/superpowers/compare/cyclesgi_*.png`。
- **数值**：分区域平均亮度（天花板近窗/远窗、侧墙、桌下地面、走廊）与参考图之比，改后应比改前更接近 1。
- **帧率**：readPixels 强制同步计时，4 预设 × 5 机位 + 监控墙，记录到 `性能优化计划.md`。
- **回退**：删掉数据块 → 画面与改前逐像素一致（meanAbs = 0）。
- **交互回归**：时间轴全天推移、四种天气、三组灯开关/亮度、走廊进出、监控墙、R 报告、URL 复现链接。

---

## 6. 风险与对策

| 风险 | 对策 |
|---|---|
| 探针漏光 / 漏暗（薄板两侧、桌面） | 非均匀层高贴合水平面；采样点沿法线外推；坏探针修补；体积离墙内缩；以参考图逐机位检查 |
| GLTFExporter / Blender 导入不完整（实例、纹理 repeat） | 导出前展开 InstancedMesh；repeat 走 KHR_texture_transform；不行则改为自定义 JSON 导出（几何+材质参数） |
| 两条太阳轨迹不一致 | 关键帧按方位插值；间接光低频，误差可接受；参考图核对晨/午/暮 |
| 首次 Metal 内核编译慢（实测 144s） | 仅首次；之后秒级 |
| 文件变大（≈1.3MB → 8–9MB） | 数据块置于文件末尾；WebP；GI 图降噪后再编码以提高压缩率 |
| 改灯数 → 着色器重编卡顿 | 拆灯发生在加载期；预热逻辑不变 |
| 烘焙数据与几何不同步 | `gi.json` 存几何指纹，不一致时控制台警告；`run_all.sh` 一键重烘 |

---

## 7. 文件清单

- 新增 `bake/`：`run_all.sh`、`export_scene.mjs`、`exporter-entry.mjs`（打包 GLTFExporter）、`blender_common.py`、
  `blender_textures.py`、`blender_gi.py`、`blender_reference.py`、`embed.py`、`README.md`
- `bake/out/`、`bake/assets/polyhaven/`（原始下载）加入 `.gitignore`
- 修改 `classroom_v4_3.html`：贴图接入、GI 解码/合成/着色器补丁、权重接线、拆灯、末尾数据块
- 更新 `项目记录.md`、`性能优化计划.md`

## 8. 后续（不在本次范围）
- 反射探针：Cycles 全景 → PMREM，让抛光地砖反射出真实窗户与灯具。
- 室外视角（`0` 机位）的外墙/地面烘焙。
