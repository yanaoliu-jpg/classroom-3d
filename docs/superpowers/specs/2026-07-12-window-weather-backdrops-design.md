# 窗外天气背景 + 取消抗锯齿 — 设计文档

日期:2026-07-12
文件:`classroom_v4_3.html`(单一 HTML,所有贴图程序化 canvas 绘制)

## 目标

左墙 3 扇朝外的窗户外,显示**可切换的天气背景**(晴 / 阴 / 雨 / 雪),程序化静态贴图,"跟真实窗外场景一样"。只更换窗外背景,不改动室内灯光。附带:取消抗锯齿功能。

## 决策记录(brainstorming 结论)

- 画风:**程序化 canvas 绘制**(先做一版看效果;不是照片,半写实、风格化,与项目现有贴图一致,保持单文件自包含)。以后若不够真,再考虑换用户提供的照片。
- 天气种类:**晴天、阴天/多云、雨天、雪天**(4 种)。
- 联动:**只换窗外背景,不联动室内光照**。
- 动画:**静态贴图**(无雨滴下落/云飘/雪落),不掉帧。
- 抗锯齿:**取消**(删 UI 开关 + 固定关闭 MSAA)。

## 现状(已勘查)

- 左墙窗在 `winPositions.forEach` 里逐扇构建(`wx = -RW/2`),右墙高窗朝走廊、不涉及。
- 每扇窗已有 `extBg` 背景板面片(`PlaneGeometry`,朝室内),当前 `visible=false`,材质 `MeshBasicMaterial({color})`,句柄收在 `extMats[]`。当前窗外为空(内景里窗户呈黑)。
- `makeExteriorTex()` 现产出一张纯天空渐变(此前被简化)。
- 已有昼夜压暗机制更新 `extMats[].color`:2 处 —— 静态预设分支(约 `8112-8120`)与连续时间/漂移分支(约 `8543`)。当前颜色值是为"纯色天空 + 过曝"调的很暗的值。
- 抗锯齿:`setAA(on)` 给 `composer.renderTarget1/2` 设 `samples = on?4:0`(约 `8350`);UI 开关 `#aaOn`(约 `350`,默认勾选);初始化 `setAA(document.getElementById('aaOn').checked)`(约 `8365`)。渲染器本身 `antialias:false`,MSAA 只在离屏目标上。

## 设计

### 1. 天气贴图 `makeWeatherTex(kind)`

新增函数,`kind ∈ {'clear','cloudy','rain','snow'}`,返回 `THREE.CanvasTexture`。画布 2048×512 全景宽幅(3 扇窗各取横向一段,连续如真实外景)。构建一次并缓存到 `weatherTex = { clear, cloudy, rain, snow }`。

各天气画法(canvas 2D):
- **clear 晴天**:天顶蓝 → 地平线亮白线性渐变;柔和太阳径向光晕;数朵积云(叠加半透明白色斑块 + 底部灰影);底部远处树线/楼房剪影(低饱和暗色带)。
- **cloudy 阴天/多云**:灰白分层云(多条水平柔和灰带 + 随机云块),无太阳光晕,地平线灰蒙。
- **rain 雨天**:灰蓝暗天渐变;大量细斜线(雨丝,低不透明);朦胧水汽(整体降对比);零星玻璃水痕(小半透明椭圆/竖流)。
- **snow 雪天**:白灰天渐变;散落白色雪点(不同大小圆点);冷蓝白地平线;底部积雪暗示。

纹理属性:`colorSpace=SRGBColorSpace`,`wrapS=RepeatWrapping`,`wrapT=ClampToEdgeWrapping`。

### 2. 重新启用背景板

在 `winPositions.forEach` 内:`extBg.visible = true`;材质改为带 `map`(初始 `weatherTex.clear`);保留 per-window 横向切片(`repeat.x=0.5`、`offset.x=[0,0.25,0.5][wi%3]`)。`extMats` 继续收集这些材质。`extMat.color` 仍作为昼夜亮度乘数(乘在 map 上)。

### 3. 切换逻辑 + UI

- 新增 `setWeather(kind)`:遍历 `extMats`(即这些 `extBg` 背景板材质的集合),把每个材质的 `.map` 换成 `weatherTex[kind]`、置 `map.needsUpdate` 与 `material.needsUpdate`;更新面板按钮的 active 高亮;记录 `currentWeather`。默认 `'clear'`。
- 设置面板新增一栏 `🌤 天气 · Weather`,4 个按钮(晴天/阴天/雨天/雪天),`onclick="setWeather('...')"`,与现有机位/灯光按钮同风格(`aspect-btn`)。
- 天气与时间预设正交,可任意叠加。

### 4. 昼夜跟随(改现有 2 处乘数)

把 `extMats.forEach(em => em.color.setRGB(...))` 两处从"暗纯色值"改为"亮度乘数",让贴图随时间明暗:
- 正午 ≈ 1.0(近白),清晨 ≈ 0.85(略暖),黄昏 ≈ 0.55(偏暖),深夜 ≈ 0.15(冷暗)。
- 连续时间分支(`8543`)用相同曲线按太阳高度/时间插值,保持与静态预设一致。
- 目的:天气贴图按正确亮度显示,深夜不再是刺眼白天窗。

### 5. 取消抗锯齿

- 删除性能栏 `抗锯齿` 那行 UI(`350`)。
- 初始化调用改为 `setAA(false)`(固定关闭 MSAA);保留 `setAA` 函数体无害(或直接内联关闭)。
- 移除对 `#aaOn` 的引用,避免读取已删元素报错。

## 验证

- 无头 Chrome 对 4 种天气各截 1 图,确认贴图出现、切换正常、几何无破面。
- 亮度/真实感/昼夜跟随由用户在真实 Chrome 确认(无头渲染灯光/曝光不可靠,约暗 1.6×)。
- 确认删除抗锯齿开关后无 JS 报错(空场景=有错)。

## 范围外(YAGNI)

雨滴下落 / 云飘 / 雪落动画;雷雨 / 雾 / 晚霞;天气音效;室内光照联动;右墙高窗(朝走廊,不涉及)。
