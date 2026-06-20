# classroom_v4_3 实时光影自然化（第一轮）— 设计 spec

- 日期：2026-06-20
- 目标文件：`classroom_v4_3.html`（单文件、约 816KB、内联 Three.js r128）
- 状态：已通过设计评审，待 spec 评审

## 1. 背景与现状

`classroom_v4_3.html` 不是用 HTML/CSS/SVG 画的，而是把 **Three.js r128（WebGL）整个内联**的全 3D 实时渲染器：

- 几何体：`BoxGeometry ×126`、`Mesh ×114`、PBR `MeshStandardMaterial ×59`、`PlaneGeometry ×48` 等
- 灯光（13 盏）：`DirectionalLight ×2`（`mainLight` 太阳 / `moonLight`）、`PointLight ×3`、`SpotLight ×4`、`HemisphereLight ×1`、`AmbientLight ×1`
- 已开启：`PCFSoftShadowMap`、`ACESFilmicToneMapping`、`toneMappingExposure=0.50`（作者精调以防爆白）、`outputEncoding=sRGBEncoding`、`PMREM` 环境贴图（IBL）、`FogExp2`、灰尘粒子（`Points`）
- 程序化纹理：`CanvasTexture ×17`
- “窗光”实现：`mainLight`（`DirectionalLight`，强度 1.8）穿过墙上用 `ShapeGeometry` 挖的窗洞照入；**窗平面上没有真正的面光源**。
- 渲染：直接 `renderer.render()`，**无后处理管线**（只内联了 THREE core，无 `EffectComposer`/AO）。

### 问题诊断
“不自然”的主因不是 HTML，而是**缺少间接光（GI / 反弹）**与真正的面光源：
- 没有地面→天花板→墙的回弹补光（现在用 `Hemisphere`/`Ambient` 平涂近似）。
- 窗户=大面光源，但现在用 `DirectionalLight` 近似，缺少面光的柔和过渡。
- 缺少随位置变化的接触变暗（AO）。

## 2. 决策（已与用户确认）

| 决策点 | 选择 |
|---|---|
| 技术基座 | **升级 Three.js r128 → `three@0.164.1`**（保留 `useLegacyLights` 以分离迁移风险），接受重新平衡风险 |
| 打包/依赖 | **保持单文件、离线可用**：esbuild 把 three+addons 打成单 IIFE 内联（替代 importmap/blob） |
| 第一轮范围 | **迁移 + 窗户 RectAreaLight + GTAO + 假反弹补光 + 接地阴影** |
| 验收红线 | **物理自然优先，允许整体色调/亮度改变**，高自由度重新打光 |

## 3. 架构与打包

- 基座 pin **`three@0.164.1`**（最后一个仍保留 `useLegacyLights` 的版本，r165 移除）。理由：用它在迁移第一步先维持旧灯光行为，把“颜色管理迁移”和“灯光物理化”两个风险源分离；GTAOPass/OutputPass/RectAreaLightUniformsLib 在该版本全可用。`WebGLRenderer` 走 WebGL2。
- **单文件离线方案（改用 esbuild IIFE，而非 importmap/blob）**：用 esbuild 把 `three` + 所需 addons 打成**单个 IIFE 包**，在脚本里 `Object.assign(THREE, {addons...}); window.THREE = THREE;`，内联进 html **替换原 r128 压缩块**。
  - 理由：app 代码用全局 `THREE` 且依赖大量全局变量/函数（`theta`/`renderer`/`applyPreset`/`DBG`…，harness 与调试工具靠它们）。IIFE 是经典脚本、同步执行、设好全局后 app 经典脚本照常运行——**app 代码几乎不动**，彻底绕开 ESM 模块作用域与 `file://` 下的 import 限制。比 importmap/blob 更简单、无相对导入解析问题。
- 需打包的 addons：`RectAreaLightUniformsLib`、`EffectComposer`、`RenderPass`、`GTAOPass`、`OutputPass`。
- `vendor/` 仅为构建用（esbuild + three 源），不进交付物；交付仍是单个 html。
- 保留 `renderer.preserveDrawingBuffer=true`（headless 截图依赖）。
- 体积预期增大到约 1–1.5MB（IIFE 包）—— 已接受。

## 4. 迁移：破坏性变更处理（本轮最大风险面）

| 旧 (r128) | 新 (r17x) | 处理 |
|---|---|---|
| `outputEncoding=sRGBEncoding` | `outputColorSpace=SRGBColorSpace` | 改写 |
| 灯光非物理（`physicallyCorrectLights` 默认关） | **默认物理单位**（`useLegacyLights` 已移除） | **13 盏灯全部按物理单位重标定**（方向光/点光/聚光强度含义全变） |
| `sRGBEncoding` 贴图 | `texture.colorSpace=SRGBColorSpace` | 17 个 `CanvasTexture` + 其它颜色贴图逐个标 colorSpace；法线/粗糙度等数据贴图保持线性 |
| 默认无 ColorManagement | **默认开 ColorManagement** | 颜色重新解释，配合重打光一并吸收 |
| 直接 `renderer.render()` | 走 `EffectComposer` | `RenderPass → GTAOPass → OutputPass`；**ACES 色调映射移到 OutputPass**，避免双重 tonemap |

## 5. 四个光影特性

1. **窗户面光源**
   - `RectAreaLightUniformsLib.init()` 后启用。
   - 在左墙窗 + 右墙高窗（`WIN_CZ` / `RWIN_W` / `WIN_YB`–`WIN_YT`）各放一块朝室内的 `RectAreaLight` 做柔和面光。
   - `RectAreaLight` 不投影 → **保留一盏 `DirectionalLight`** 专门负责清晰阳光斜射 + 阴影。两者分工：方向光给“硬阳光 + 阴影”，面光给“柔和窗光填充”。

2. **GTAO**
   - `EffectComposer` 中加 `GTAOPass`，按房间尺度（`RW×RD`）调 radius/scale。
   - 提供半分辨率档位（性能开关），默认值在计划阶段确定。

3. **假反弹补光**
   - 重调现有 `HemisphereLight` / `AmbientLight`。
   - 增加 1–2 盏低强度补光：吸取地面暖色（向上填充）与窗口冷色，模拟地面→天花板回弹。

4. **接地阴影**
   - GTAO 提供大部分接触变暗。
   - 收紧 shadow-map 偏移（bias / normalBias）让物体与地面接触更实。
   - 高级 contact-shadow buffer（从下方渲染到贴图）**留到下一轮**。

## 6. 验证与步骤序列（对冲“变量多、难定位”）

每步用 headless 渲染 + URL-hash 固定相机出 before/after 截图对比：

0. **基线**：当前 r128 在固定相机角度的截图集。
1. **仅迁移**：切到 r17x + `EffectComposer`（RenderPass→OutputPass，ACES 移到 OutputPass），修全部破坏性 API，**先尽量复刻现状** —— 确认迁移没搞坏画面。
2. **加 GTAO**：插入 `GTAOPass` 并调参。
3. **窗户 RectAreaLight**：`RectAreaLightUniformsLib` + 各窗面光，保留方向光做阳光/阴影。
4. **假反弹补光**：重调 Hemisphere/Ambient + 新增回弹补光。
5. **接地阴影**：收紧 shadow-map 偏移。
6. **最终重平衡**：按“物理自然”整体收一遍曝光/灯光。

## 7. 范围外（本轮不做）

- 真·实时 GI（SSGI / irradiance volume / 路径追踪）。
- 烘焙 lightMap。
- 高级 contact-shadow buffer。
- 拆分多文件 / 引入构建工具（保持单文件）。

## 8. 风险与缓解

- **r128→r17x 迁移破坏画面**：分步序列，步骤 1 先以“复刻现状”为目标隔离迁移风险。
- **物理单位灯光全部失真**：步骤 1 集中重标定 13 盏灯并用截图比对。
- **EffectComposer 双重 tonemap / 色彩偏差**：ACES 统一放到 OutputPass，移除 renderer 上的重复设置。
- **单文件 ESM 在 `file://` 不运行**：用内联 module script + blob importmap 方案验证可行后再继续。
- **GTAO 性能**：提供半分辨率档位与开关。

## 9. 验收标准

- 单文件、双击离线运行。
- 步骤 1 截图与基线在“构图/可读性”上无明显倒退（迁移无破坏）。
- 最终版相对基线：窗光更柔、接触阴影更自然、整体光影更接近物理（允许色调/亮度变化）。
- 固定相机 before/after 截图集作为客观对比证据。
