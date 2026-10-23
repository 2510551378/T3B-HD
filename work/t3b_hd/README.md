> GitHub 协作入口：[../../README.md](../../README.md)，当前状态见 [../../docs/CURRENT_STATUS.md](../../docs/CURRENT_STATUS.md)。下文保留各阶段历史记录；本机数据路径不随 Git 发布。

# The 3rd Birthday HD Remaster

这是《寄生前夜：第三次生日》（ULJM-05798）的独立 PC 高清重制工程。

正式重制引擎已选定 **Unreal Engine 5（UE5）**，迁移基线为 UE 5.8 稳定系列。当前目录的可运行程序仍是 C + SDL2 + OpenGL 2.1 验证原型；正式 UE 工程源码及 source replay 已建立于 `../t3b_unreal/`，尚未通过真实 UE 编译与运行。选型依据、工程边界和迁移验收见 [ENGINE_DECISION.md](docs/ENGINE_DECISION.md)。

## 范围

- 目标平台：Windows PC
- 目标分辨率：1920×1080 起步，支持无窗口/窗口模式
- 目标帧率：60 FPS；战斗和过场逻辑与渲染解耦
- 第一阶段：纽约战区的可玩垂直切片
- 原版 ISO 仅作为用户本地研究输入；重制运行时不依赖 PSP 模拟器

## 当前资源状态

资源解析位于 `../psp_parse/`：

- `3rd.pkg`、436 个 `pack` 容器已完成容器级解析
- 91 个环境几何容器已导出 OBJ
- 6,195 张 4bpp 贴图已导出 PNG
- 42 个 PSMF 视频已定位边界
- 原版 Aya 完整 draw 表已恢复：106 packets、3,456 条顶点/UV、1,152 三角形和显式 source-index 权重。
- `aya_source_skin.bin` 已替换几何分区/pivot 变形，加载 44 根 source bones、真实 affine 矩阵和平移；当前播放 12 个有原始 ticks 的稀疏姿态样本。
- `assets/materials/original_aya/` 保存按逐 draw 证据恢复的原版 256×256 CLUT8 atlas，保留 alpha、UV 和 RGB doubling 状态。
- `aya_source_weapon.bin` 是确认后的真实枪械：243 顶点、81 三角形、独立 64×64 材质，以及与 Aya 同帧的 12 组相对 WORLD 变换。
- 旧 `aya_weapon_runtime.obj` 已确认是 Aya 身体 packet86，已停用。旧 source36/手工握把偏移不参与新的角色/武器绘制。
- 正式 fire clip 已换成拉开距离后采集的 60 帧 Aya/weapon source，保留原始时间与逐帧 WORLD；aim 仍为 3 个稳定样本，记录末尾保持。
- 原版异形已接入：11 source bones、28 packets、1800 顶点、600 三角形、60 帧动作和原版 256² RGBA atlas。枪口射线检测其同帧变形后的实际网格。
- 默认街景已换成 `assets/scenes/original_street/`：140 个原版 draw、10552 三角形、81 组渲染状态和 73 张原版 RGBA 纹理，保留原始 UV、顶点颜色和相对位置。
- 原始 EBOOT.BIN 是加密 PRX；RAM 提取的 module 已用于 MIPS 静态字段与运行时交叉验证。

当前贴图是准确恢复的原版分辨率资源；高清细节重建尚未完成。矩阵重放也尚未等同于恢复全部原版动作、状态机与章节。

`aya_true_right_hand_timeline.csv` 现已始终加载并记录 provenance（24 帧、source bone 36、draw 1037、palette slot 12）。source-pair 渲染路径仍保持同次 Aya/weapon capture 的变换，报告中的 `timeline_loaded=1 / timeline_used=0 / timeline_bound=0` 是有意保守的边界，直到同一 capture 坐标 join 被证明。

## 工程原则

1. 不修改原 ISO；所有重制资产进入本工程自己的 `assets/`。
2. 原版素材只做本地研究和兼容验证；可发行版本使用重建或获授权资产。
3. 先锁定一段可玩的战斗，再扩展章节和过场。
4. 画面升级优先顺序：角色剪影与材质、场景光照、后处理、HUD 可读性、视频输出。
5. 先保证锁定射击、Overdive、掩体和 Twisted 敌人循环，再做完整装备和章节系统。

## 目录约定

```
work/t3b_hd/
├─ README.md
├─ REMASTER_PLAN.md
├─ assets/          # 重制运行时资产，不直接覆盖原解析目录
├─ src/             # PC 运行时
├─ tools/           # OBJ/PNG/PSMF 转换与验证工具
├─ docs/            # 关卡、战斗和资源规格
└─ build/           # 本地构建产物
```

## M1 运行

### 当前运行时回归（2026-10-21）

本机实际运行 `--test-original-scene --original-spawn`、`--test-ranged`、`--test-source-spawn` 和 `--inspect-aya` 均 exit 0。原版街景加载 140 draws / 31,656 vertices / 10,552 triangles；Aya 使用 44 source bones、1,152 runtime triangles；真实武器 81 triangles；远距与原版 spawn 均完成 4 次真实网格命中击杀，并验证 Overdive 进入/返回。冻结报告与 1920×1080 Aya/武器截图见 `build/m1_runtime_validation_20261021/verification.json`。

该报告只证明 C/SDL2 原型的 M1 slice；正式 UE5、原版 AI/碰撞/状态机和 HD 材质仍未验收。

在 `work/t3b_hd/` 下执行：

```powershell
mingw32-make -f Makefile.win
.\t3b_hd.exe
```

也可以指定另一个已导出的 OBJ：

```powershell
.\t3b_hd.exe ..\psp_parse\out\meshes\pack_0x4c3ca800.obj --legacy-scene
```

操作：`W/A/S/D` 移动/转向，`R` 锁定或解除锁定，`SPACE` 射击，`F` Overdive，`Esc` 退出。

当前可见 HUD：艾雅生命条、Twisted 生命条、锁定准星和射击火线。默认优先加载 `assets/scenes/original_street/original_street.bin` 与 `original_street_materials.txt`；正常游戏使用同帧原版 WORLD 推导的初始位置。`--legacy-scene` 可显式使用旧 OBJ 路径。
默认 PC 碰撞适配使用原街景中 8,551 个可确认无透明孔的实体三角形；子弹与锁定 LOS 采用最近静态表面，移动使用道路覆盖和 capsule–triangle 距离。722 个 cutout 三角形等被保守排除。原始碰撞、事件、AI、fog 和 stencil 尚未恢复；`--legacy-collision` 可复现旧四柱碰撞。
当前优先加载 `assets/models/aya_source_skin.bin` 与 `aya_source_weapon.bin`，通过 `src/aya_source_skin.h` 保留 packet、权重和矩阵执行 CPU skinning。`aya_original_runtime.obj` 仅作旧路径回退；`.rig` 文件不是新运行时的数据源。

姿态时间使用存档 CoreTiming 中实测的 333 MHz 将 ticks 转换成秒。reference 仍为 12 个稀疏样本；正式 fire 为约 1.9686 秒的 60 个连续样本，最后一个样本保持，完整后坐循环尚未恢复。枪口特效使用真实枪管端几何候选，共用武器变换；武器三骨骼中的 source1 在枪管端点附近，但其原版 consumer 尚待确认。

自动回归：

```powershell
.\t3b_hd.exe assets\scene\nyc_block_uv.obj --test
.\t3b_hd.exe --test-held-close
.\t3b_hd.exe --test-ranged
.\t3b_hd.exe --test-source-spawn
.\t3b_hd.exe --test-original-scene --original-spawn
Get-Content .\build\m1_test_result.txt
```

`--test` 是离散点射与 Overdive 用例，尚有近身姿态下未完成击杀的情况；`--test-held-close` 与 `--test-ranged` 分别检查近距与远距持续开火。两者已通过四次真实网格命中击杀，命中与墙体距离另由独立 Python 算法复算。`--test-original-scene` 检查完整场景渲染与逐顶点导入，不自动射击。

新资源统计写入 `build/m1_source_skin_result.txt`。角度/玩家 LOS 命中回退已经移除，实际使用枪口射线与原版异形变形网格。原版 spawn 已在主 exe 的 `--test-source-spawn` 中实测 4 次真实网格命中击杀；独立射线与移动几何验证报告为 `AYA_M1_SOURCE_SPAWN_PRIMARY_RAY_VERIFICATION.json`、`ORIGINAL_SCENE_COLLISION_C_RUNTIME_VERIFICATION.json`，全场景/异形 C 数值证据为 `ORIGINAL_SCENE_SOURCE_COLLISION_C_RUNTIME_VERIFICATION.json` 与 `ORIGINAL_ACTOR_SOURCE_SPAWN_C_RUNTIME_VERIFICATION.json`，均位于 `../psp_parse/out/`。动作/武器与限制见 `docs/M1_ORIGINAL_ACTOR_FIRE60_20261020.md`，原街景格式与原 GE 验证见 `../psp_parse/docs/ORIGINAL_STREET_EXPORT_20261020.md`。

角色检查截图：

```powershell
.\t3b_hd.exe build\empty_scene.obj --inspect-aya
```

输出 `build/m1_inspect_aya_a.ppm` 与 `m1_inspect_aya_b.ppm`；`--preview` 保留战斗侧视截图。角色检查会隐藏敌人并关闭自动射击。

本轮接入和已知边界：`docs/M1_ORIGINAL_SOURCE_SKIN_20261020.md`。
## 可选 HD sampling 路径

`--hd-sampling` 使用独立 1024² Aya atlas 与 256² weapon atlas，保留原 UV/mesh/骨骼/枪口逻辑；默认不启用。验证见 `build/hd_sampling_verification.json`。它提升采样分辨率，不等于恢复原始缺失纹理细节。

### HD sampling 启动

可直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_m1_hd_sampling.ps1 -TestSourceSpawn
powershell -ExecutionPolicy Bypass -File .\run_m1_hd_sampling.ps1 -Preview
```

资产与 hash 见 `build/m1_hd_sampling_package_v1.json`。这是 C/SDL2 可选路径，不是正式 UE5 版本。

HD A/B 预览见 `build/m1_hd_sampling_ab.png`，像素差异集中在 Aya/weapon 区域；统计见 `build/m1_hd_sampling_ab.json`。


## M1 交付索引

当前可运行验证、SourceData 资产身份、HD sampling 资源和明确未完成项统一见：
`build/M1_DELIVERY_INDEX_20261021.json`。

索引中的状态是 `active`：C/SDL2 M1 slice 已可复现，UE5 正式构建、原版 gameplay collision/AI/state machine、同一采集中的手部 timeline binding，以及真正的高清细节重建仍需后续证据。


右手 timeline 的只读来源比对见 `build/true_hand_timeline_clip_comparison_v1.json`。24 帧 hand/mount/muzzle 记录与现有 60 帧 Aya T3BSKN2 source clips 没有 direct matrix match，当前 source-pair runtime 继续保持 `timeline_bound=0`，避免跨采集混用。



### approach_fire source pair

ssets/models/aya_source_clips.txt 现在还加载一组 60 帧 pproach_fire Aya/weapon source pair。只有移动键与开火同时成立时才选择它；它来自已校验的 approach-plus-fire capture，不被命名为通用 strafe 或完整 locomotion。资产/状态机证据见 uild/m1_source_clip_check.txt。



可用的 pproach_fire source pair 已接入 M1：移动键与开火同时成立时播放 60 帧 approach-plus-fire capture。验证目录为 uild/approach_fire_validation_20261021/；它不代表通用 strafe 或完整移动状态机。



### 原版材质匹配增量

全量已保存 PPSSPP frame capture 的 CLUT/TEXTURE0 匹配见 ../psp_parse/out/RUNTIME_CLUT_PACK_MATCH_20261021.json。当前 206 个 runtime payload signatures 中 84 个已找到 type-8 pack 命中，新增3个 CLUT 子序列命中；剩余122个仍未命中，默认M1材质绑定保持不变。



Aya source coverage audit 见 ../psp_parse/out/AYA_SOURCE_BONE_COVERAGE_20261021.json。dense aim/fire manifest 各有60个 source frames，但完整 GE dump 只有2帧，仍覆盖35/44 source indices；缺失骨骼没有被占位映射。



SEDB 结构 inventory 已生成：../psp_parse/out/SEDB_STRUCTURE_INVENTORY_20261021.json。它只保留原始容器、offset region 和有限浮点候选，不改变场景碰撞 adapter，也不声称恢复实体语义。



3rd.fsd 已补充结构 inventory：../psp_parse/out/3RD_FSD_STRUCTURE_INVENTORY_20261021.json。当前只锁定记录数量、stride、tag 和 sentinel，未恢复记录编码或关卡语义。



SourceData 现在包含只读 FSD index probe：../t3b_unreal/Validation/fsd_index_probe_v1.json。它验证原始 3rd.fsd 的记录布局，但不宣称恢复关卡实体或碰撞语义。



approach_fire Aya/weapon source pair 已同步到 SourceData，identity 见 ../t3b_unreal/Validation/action_clip_source_bundle_v1.json。它只表示移动+开火 capture，不代表通用 locomotion。

