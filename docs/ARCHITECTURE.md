# 模块与约束

## 数据流

原版 ISO/运行时 RAM/GE（本地私有）→ `psp_parse` 的提取、匹配及同帧核验 → 自定义 source binaries/材质绑定 → C 原型与 UE source-data core → UE replay、GE pass、后续 gameplay。

原版证据与增强资源需分别保留；重采样不能覆盖原纹理。身份快照为 `docs/runtime_asset_manifest.json`，具体采集 provenance 保留在本地报告。

## 代码入口

| 模块 | 入口与职责 |
| --- | --- |
| C 战斗切片 | `work/t3b_hd/src/m1_main.c`：输入、越肩镜头、锁定/射击、Overdive、运行时检查 |
| C 资源/碰撞 | `aya_source_skin.h`、`original_actor_runtime.h`、`original_scene_runtime.h` 及 `combat_*.h`：source skinning、场景、射线和碰撞适配 |
| UE 默认流程 | `T3BReplayGameMode` 启动 `T3BReplayWorld`；配置地图为 `/Game/T3B/Maps/M1_SourceReplay` |
| UE 独立 core | `T3BSourceData`：格式拒绝检查、保留 source affine 矩阵、蒙皮、PC/UE 坐标转换 |
| 动作对 | `T3BActionClip`：Aya/weapon 同步 source pair，`T3B.Replay.ActionClip reference/approach_fire` |
| 原 GE 渲染 | `T3BGEReplayActor`、`T3BGESceneReplayActor` 与 `Shaders/`：按序原 draw、scene、shader；正式 Editor/RDG 运行待验证 |
| 武器/FX | `T3BGEWeaponMarkers`、`T3BGEOriginalMatrix`、`T3BGEEffect*`：已恢复的 marker、矩阵及属性数值；不等于完整原游戏调度 |
| 工具 | `work/t3b_unreal/Tools/`：独立 C++ probes、native D3D11 reference、UE Python 导入/诊断；原版采集在 `psp_parse/tools/` |

UE 文件位于 `work/t3b_unreal/Source/T3BRemake/Private` / `Public`；部分 core 故意不依赖 UE，便于逐位验证。

## 不变量

- 不把任意 affine source 矩阵拆成 `FTransform`；不要自动丢弃 shear、reflection 或 bind compensation。
- 不重新归一化已量化 source 权重；保持原有 draw 顺序、UV、RGBA 和对应 CLUT 状态。
- `ToPC` 处理 source units/floor/actor transform；`ToUE = (PC.z, -PC.x, PC.y) * 100`。场景已存 PC units 的位置不能重复缩放。
- source sample time 只代表已存时间线。保持首尾 clamp，不凭空推断循环、原时钟秒数或完整状态机。
- CPU 浮点验证禁止 FMA/fast-math；独立 GCC 构建用 `-ffp-contract=off`。
- 同帧关联需来自同一捕获：不能凭空间相近将另一采集的右手、枪械矩阵与 muzzle 轨迹拼接。
- 匿名 source index 在有直接证据前保持匿名；数值通过、语义命名和画面通过分别记录。
