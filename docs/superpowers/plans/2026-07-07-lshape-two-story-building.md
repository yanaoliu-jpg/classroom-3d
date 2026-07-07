# L 形双层楼改造 实现计划

> **For agentic workers:** 本计划在单文件 `classroom_v4_3.html` 上执行。无单元测试框架；每个任务的验证 = ①`node --check`（提取 app 脚本语法检查）②headless Chrome 截图并肉眼核对几何/光影。步骤用 `- [ ]` 跟踪。

**Goal:** 把单层单教室场景改造成 L 形双层楼：横翼 A 二层放现有教室/走廊/办公室，竖翼 B 一层放报告厅，其余毛坯，机位切换导航。

**Architecture:** 方案 A「抬楼」——现有教室套收进一个组整体升到二层，围绕它新建 L 形外壳、双层楼板与报告厅。最大限度不动已精调的光影。

**Tech Stack:** Three.js r164（单文件 `classroom_v4_3.html`），EffectComposer 后处理管线（已有），headless Chrome 截图验证。

**依赖:** 报告厅**内部**布置依赖 image6（尚未成功上传）；阶段 3 只做外壳，内部待图。

---

## 通用验证流程（每个任务结尾都用）

- 语法：`END=$(awk 'NR>=4655 && /^<\/script>$/{print NR; exit}' classroom_v4_3.html); sed -n "4655,$((END-1))p" classroom_v4_3.html > /tmp/app.js && node --check /tmp/app.js`
- 视觉：headless 截图（`--headless=new --disable-gpu --no-sandbox --virtual-time-budget=6000 --screenshot=...`，需要看外观时用 `--force-device-scale-factor=2`、临时改 body 背景色或切机位），然后 Read 截图核对。
- 每个任务通过后 commit（分支已在 `fix/winwall-...`，非 main，可直接 commit）。

---

## 阶段 1 — L 形外壳 + 双层楼板

### Task 1: 楼层常量 + 外壳辅助函数
**Files:** Modify `classroom_v4_3.html`（在现有 `RW/RD/RH` 常量定义附近，约 line 328 区）

- [ ] 定义楼层体系常量：`FLOOR_LIFT = 3.85`（二层抬升量）、`SLAB_T = 0.35`（楼板厚）、`L1_Y0=0, L1_Y1=3.5, L2_Y0=3.85, L2_Y1=7.35`。
- [ ] 定义两翼地脚印常量：横翼 A `WA_X=[-7,9], WA_Z=[-5,25]`；竖翼 B `WB_X=[-23,-7], WB_Z=[-5,13]`（草案值，image6 到位后可调）。
- [ ] 写一个辅助 `function addShellBox(cx,cy,cz,w,h,d,mat)` 或复用现有建盒模式，用于快速造毛坯墙/板。材质用中性混凝土灰（参照现有外墙材质）。
- [ ] 验证：`node --check` 通过。Commit：`feat(bldg): 楼层常量与外壳辅助`。

### Task 2: 横翼 A 一层毛坯壳
**Files:** Modify `classroom_v4_3.html`

- [ ] 在横翼 A 地脚印建一层毛坯：地面（`Y=0`）、四周外墙（`Y[0,3.5]`）、顶（即层间楼板底面）。无门窗内部（毛坯）。
- [ ] receiveShadow/castShadow 按外壳需要设置，避免漏光（参照现有走廊 receiveShadow 修复经验）。
- [ ] 验证：headless 截图（切"整栋外观"角度或临时相机）核对一层壳成立、无破面。Commit：`feat(bldg): 横翼A一层毛坯壳`。

### Task 3: 横翼 A 层间楼板 + 二层地面
**Files:** Modify `classroom_v4_3.html`

- [ ] 建层间楼板（`Y[3.5,3.85]`）铺满横翼 A 地脚印；其上表面 `Y=3.85` 作为二层地面基准（教室组将坐落于此）。
- [ ] 二层外墙（`Y[3.85,7.35]`）——注意西墙要给教室窗留洞（阶段 2 教室自带窗，外壳西墙对应位置需开口，不遮挡阳光）。可先建实墙，阶段 2 再按教室窗位开洞。
- [ ] 验证：`node --check` + 截图核对楼板/二层墙位置。Commit：`feat(bldg): 横翼A楼板+二层墙`。

### Task 4: 竖翼 B 双层外壳
**Files:** Modify `classroom_v4_3.html`

- [ ] 在竖翼 B 地脚印建：一层四墙+地+顶（一层将放报告厅）、层间楼板、二层毛坯壳。
- [ ] 竖翼 B 的 +X 边（x=-7）与横翼 A 左墙相接处**留通道洞**（供机位/连通，具体门在 Task 11）。
- [ ] 验证：截图核对 L 形两翼相接、双层成立。Commit：`feat(bldg): 竖翼B双层外壳`。

### Task 5: 屋顶 + 整栋外观验证
**Files:** Modify `classroom_v4_3.html`

- [ ] 两翼加屋顶面，封顶。
- [ ] 验证：headless 截图从"L 形俯瞰/外观"角度（临时相机 or 直接改 CAM 之一），Read 图确认整栋 L 形双层外观正确、两翼比例与 image3 一致。Commit：`feat(bldg): 屋顶+整栋外观`。

---

## 阶段 2 — 教室套抬到二层

### Task 6: 审计教室/走廊/办公室的所有 scene.add
**Files:** 只读 `classroom_v4_3.html`

- [ ] grep 出所有 `scene.add(` 及相关对象，分类：教室核心（墙/地/顶/窗/黑板/家具）、走廊、办公室、以及**不该迁移的**（太阳光、天空、光球、粒子、体积光等全局项）。
- [ ] 产出一份"迁移清单"（哪些进 `wingAUpper` 组，哪些留全局）。记录在计划执行笔记里。
- [ ] 无代码改动；本任务是安全网，防止把全局光/相机误抬升。

### Task 7: 建 wingAUpper 组，迁入教室核心并抬升
**Files:** Modify `classroom_v4_3.html`

- [ ] 新建 `const wingAUpper = new THREE.Group(); wingAUpper.position.y = FLOOR_LIFT; scene.add(wingAUpper);`（放在场景创建后、教室构建前的合适位置）。
- [ ] 把 Task 6 清单里的教室核心对象的 `scene.add(x)` 改为 `wingAUpper.add(x)`（分批小步，每批 `node --check`+截图）。
- [ ] 验证：截图确认教室整体升到二层、内部结构完整无错位。Commit：`feat(bldg): 教室核心抬到二层`。

### Task 8: 迁入走廊与办公室
**Files:** Modify `classroom_v4_3.html`

- [ ] 走廊相关对象迁入 `wingAUpper`。
- [ ] 办公室相关对象迁入 `wingAUpper`。
- [ ] 验证：截图确认走廊/办公室随教室升到二层、与教室对齐、连通关系保持。Commit：`feat(bldg): 走廊办公室抬到二层`。

### Task 9: 阴影范围 + 世界坐标依赖校正
**Files:** Modify `classroom_v4_3.html`

- [ ] 方向光阴影相机的覆盖范围上移/扩大，覆盖二层教室（现有 `shadowMap.autoUpdate=false`，改完 `shadowMap.needsUpdate=true` 触发一次）。
- [ ] 校正依赖世界坐标的项：光球拖拽落点、CAM_VIEWS 机位（教师/后前等原教室机位的 `panY` 等需 +FLOOR_LIFT 或改指二层）、dust/sunbeam 若锚在教室也需上移。
- [ ] 验证：截图确认二层教室光影正常（窗光斑、桌椅阴影、走廊光）、切原教室机位落在二层。Commit：`feat(bldg): 二层光影与机位校正`。

### Task 10: 二层完整性回归验证
**Files:** 只读

- [ ] headless 多角度截图核对：二层教室与迁移前逐项对齐（窗/黑板/桌椅/走廊/办公室/光影）。
- [ ] 复测 FPS/动态分辨率/画幅未回归（本会话既有功能）。无回归则进入阶段 3。

---

## 阶段 3 — 报告厅（竖翼 B 一层）

### Task 11: 报告厅外壳 + 门 + 连通口
**Files:** Modify `classroom_v4_3.html`

- [ ] 在竖翼 B 一层建报告厅外壳：四墙/地/顶（复用竖翼 B Task 4 的壳，或在其内做内墙面）、入口门、与横翼 A 相接处的连通口。
- [ ] 基础室内照明（吸顶灯板，参照现有天花板灯做法），保证机位进去不是全黑。
- [ ] **内部布置（舞台/讲台/座椅阵列）留待 image6**——本任务只交付外壳+照明。座椅阵列届时用 InstancedMesh。
- [ ] 验证：截图确认报告厅外壳成立、有基础照明、可从连通口望入。Commit：`feat(bldg): 报告厅外壳+照明(内部待image6)`。

---

## 阶段 4 — 机位导航

### Task 12: 新增机位 + 面板按钮
**Files:** Modify `classroom_v4_3.html`（`CAM_VIEWS` 定义区、keydown 处理、设置面板 HTML）

- [ ] 在 `CAM_VIEWS` 增加机位：`报告厅`（竖翼 B 一层内）、`二层教室`、`二层办公室`、`整栋外观/L形俯瞰`。给每个合适的 `theta/phi/camR/panX/panY/panZ/fov`。
- [ ] 绑定数字键（沿用现有 5–8 之外的键位，如 9/0，或在设置面板加"机位"按钮组）。
- [ ] 设置面板加对应按钮（复用 `.aspect-btn`/`.q-btn` 样式模式）。
- [ ] 验证：截图逐个机位确认取景正确（报告厅看得到内部、外观看得到整栋 L 形）。Commit：`feat(bldg): 机位导航`。

---

## 阶段 5 — 性能收尾

### Task 13: 性能守护 + 合批
**Files:** Modify `classroom_v4_3.html`

- [ ] 报告厅座椅（image6 内部到位后）用 InstancedMesh 合批，控制 drawcall。
- [ ] 复测：headless + 真机（用户）FPS、动态分辨率、画幅、抗锯齿均不回归（瓶颈仍为 fill-rate，见记忆 classroom-perf-resolution-bottleneck）。
- [ ] Commit：`perf(bldg): 座椅合批与性能回归验证`。

---

## Self-Review 记录
- **Spec 覆盖**：阶段 1–5 与 spec 六节一一对应；报告厅内部依赖 image6 已在 Task 11 隔离。
- **无占位**：几何用草案坐标常量（image6 到位后微调，已注明）；验证命令具体。
- **命名一致**：`FLOOR_LIFT`、`wingAUpper`、`WA_*/WB_*` 全程统一。
