# 当前交接状态

这是首次 GitHub 整理时的状态快照；继承的验证报告日期为 2026-10-21。正式目标为独立 PC 高清重制，当前项目仍在开发。

## 已有证据

| 项目 | 事实与范围 |
| --- | --- |
| 正式引擎 | Unreal Engine 5.8 / C++；本机已有 5.8.4 的部分诊断运行记录 |
| C 原型 | C/SDL2/OpenGL 2.1，可玩战斗验证；并非正式 UE 产品 |
| Aya | 44 source bones、106 packets、3,456 顶点；35 个直接加权索引有 GE 对应；其余 9 个并非都必须出现在 draw palette |
| 枪械与动作 | 原枪 243 顶点；60 帧同步 Aya/weapon source pair；`approach_fire` 为移动+开火采样，不是完整 locomotion |
| 场景与敌人 | 街景 140 draws / 31,656 顶点 / 81 材质状态；一个 11-bone 原异形；碰撞为可见网格适配，8,551 个三角形 |
| UE Game target | `T3BRemake Win64 Development` 实际完成编译链接，最新 marker probe 代码已包含；见 [构建快照](evidence/ue_game_build_markerprobe_v1.json) |
| UE 最新启动 | loose-map Game target 启动 exit 3，`FBufferReader` 断言；未产出 `weapon_markers.json`，见 [失败快照](evidence/ue_game_runtime_smoke_v1.json) |
| 工具链 | MSVC 14.44、Windows SDK 10.0.22621.0 已安装；.NET Framework 4.8 Developer Pack 日志最终 exit 0，NETFXSDK 已注册；之后尚未重新验证 Editor target |
| 高清化 | 可选 4× atlas 重采样已有原型；缺失纹理细节、脸部/服装重建和完整高清美术尚未完成 |

`docs/evidence/` 是本机历史报告副本，包含当时绝对路径及哈希；报告引用的大文件不在 Git 中。仓库 CI 只验证源码语法和独立 source-data core。

## 接手后优先做

1. **UE Editor / cook / probe**：在英文短路径构建 `T3BRemakeEditor`，用已交接的 Content 启动地图，得到真实 `T3B.Replay.Probe` 输出后再测 cooked Game。成功标准是实际地图加载、退出码与 probe 文件核验，不是仅编译。
2. **修正 probe 的 clip 一致性**：检查 `T3BReplayWorld.cpp` 中 `WriteSourceProbe()` 使用 reference `Actor.Skin`、`ApplyReplay()` 使用选中 action clip 的潜在不一致；补齐 action pair 与 reference 几何/材质兼容验证。默认仍为 `reference`。
3. **原材质视觉复核**：同相机、同帧检查 Aya 的身体/衣物、透明主深度、逐 draw CLUT。普通 UE translucent 不等价于原版 alpha blend + main depth write。
4. **武器语义与连续动作**：source1/source2 marker 的数值恢复与 source1 的部分视觉 FX 链已有证据，但完整弹道/枪口语义及所有姿态尚未恢复；真实右手 timeline 当前 loaded、未绑定，禁止强行混接不同采集。
5. **玩法与高清制作**：在原版接入可重复验证后迁移 M1，再补原 AI、碰撞/伤害、状态机和高清模型/材质。

## 数据与工具的已知限制

- 当前 source bundle 的 `coordinates.pc_to_ue` 文本仍有旧 `(z,x,y)*100` 描述；实际 core `ToUE` 是 **`(PC.z, -PC.x, PC.y) * 100`**。不要据旧元数据二次变换资产，修复需同时校验相关工具。
- `stage_source_bundle.py` 是早期生成器，重跑可能丢失后加的 FSD/action/marker manifest 字段。先备份 bundle，再扩展生成器与对应 gate。
- 某些验证器读取 manifest 中原机器绝对 provenance 路径；同事迁移后需显式适配路径，不能把找不到旧路径当内容不匹配。
- CLUT 206 signatures / 84 matches / 122 unmatched 来自特定 `frame_*.ppdmp` 采集集合。旧 coverage 检查不能证明所有命名方式和全部 GE captures 已覆盖。
- 原版游戏整体、完整章节、AI、原碰撞/伤害和所有动作尚未解析完成。已有 native GPU 或 UE 诊断图不代表正式 C++ M1 已验收。
- 历史文件中“未安装 SDK”“UE 从未编译”等结论属于当时阶段，优先采用本页及对应终态证据。
