# 当前交接状态

最新交接验证：2026-10-23。运行包已在全新 clone 中安装、校验并启动，并通过 [GitHub Release](https://github.com/2510551378/T3B-HD/releases/tag/runtime-assets-20261023-v3) 提供下载；正式目标仍为独立 PC 高清重制，当前项目仍在开发。

最新 UE 改进见 [M1 v3](UE_M1_V3.md)：街景/角色共用按序主深度路径，修正 Aya 透体与透明层覆盖；reference/approach_fire 均使用共同循环相位，实际 probe 已跟随所选动作。

## 已有证据

| 项目 | 事实与范围 |
| --- | --- |
| 正式引擎 | Unreal Engine 5.8 / C++；本机已有 5.8.4 的部分诊断运行记录 |
| C 原型 | C/SDL2/OpenGL 2.1，可玩战斗验证；并非正式 UE 产品 |
| Aya | 44 source bones、106 packets、3,456 顶点；35 个直接加权索引有 GE 对应；其余 9 个并非都必须出现在 draw palette |
| 枪械与动作 | 原枪 243 顶点；60 帧同步 Aya/weapon source pair；`approach_fire` 为移动+开火采样，不是完整 locomotion |
| 场景与敌人 | 街景 140 draws / 31,656 顶点 / 81 材质状态；一个 11-bone 原异形；碰撞为可见网格适配，8,551 个三角形 |
| UE Game target | `T3BRemake Win64 Development` 实际完成编译链接，最新 marker probe 代码已包含；见 [构建快照](evidence/ue_game_build_markerprobe_v1.json) |
| UE 最新启动 | 全新 clone + 运行包：Editor-hosted `-game` 成功加载地图，NullRHI probe exit 0；D3D11 离屏运行 31 帧后 exit 0。见 [交接验证](evidence/runtime_bundle_delivery_v2.json)；旧 standalone Game loose-map 失败仍未验证修复 |
| UE probe | Aya/weapon/Twisted 全 60 samples 与 Street 的实际组件 CPU-world 顶点通过独立比较，最大误差小于 0.0001 cm；`weapon_markers.json` 实际生成。见 [CPU 核验](evidence/runtime_bundle_ue_cpu_v2.json)，不代表像素/材质/玩法通过 |
| 工具链 | MSVC 14.44、Windows SDK 10.0.22621.0、.NET Framework 4.8 SDK 已安装；本次 `T3BRemakeEditor Win64 Development` 构建返回成功 |
| 运行包 | 655 个资产 + C exe/SDL2/自有 UE module/交接说明，共 662 个 payload 文件、约 21.8 MiB ZIP；全新 clone 的 C source-spawn 为 4 hits、enemy dead、Overdive 返回通过 |
| 高清化 | 可选 4× atlas 重采样已有原型；缺失纹理细节、脸部/服装重建和完整高清美术尚未完成 |

`docs/evidence/` 是本机历史报告副本，包含当时绝对路径及哈希；报告引用的大文件不在 Git 中。仓库 CI 只验证源码语法和独立 source-data core。

## 接手后优先做

1. **UE 可视验收 / cook**：Editor-hosted 地图和 reference CPU probe 已通过，继续同机位像素/材质检查，再测 cooked standalone Game。当前运行包通过 UE Editor host 启动，不包含 cooked 独立游戏。
2. **继续动作与事件恢复**：probe 已按实际选中的动作输出，static skin/material compatibility gate 已加入。当前循环是共享时间与 120 ms 过渡适配，还需原状态/事件调度。
3. **扩展材质复核**：v3 同机位截图已确认头发/衣料/手臂自遮挡修复；继续原光照、fog/stencil 与更多姿态，不把当前 C face shade 当原版光照。
4. **武器语义与连续动作**：source1/source2 marker 的数值恢复与 source1 的部分视觉 FX 链已有证据，但完整弹道/枪口语义及所有姿态尚未恢复；真实右手 timeline 当前 loaded、未绑定，禁止强行混接不同采集。
5. **玩法与高清制作**：在原版接入可重复验证后迁移 M1，再补原 AI、碰撞/伤害、状态机和高清模型/材质。

## 数据与工具的已知限制

- 当前 source bundle 的 `coordinates.pc_to_ue` 文本仍有旧 `(z,x,y)*100` 描述；实际 core `ToUE` 是 **`(PC.z, -PC.x, PC.y) * 100`**。不要据旧元数据二次变换资产，修复需同时校验相关工具。
- `stage_source_bundle.py` 是早期生成器，重跑可能丢失后加的 FSD/action/marker manifest 字段。先备份 bundle，再扩展生成器与对应 gate。
- 某些验证器读取 manifest 中原机器绝对 provenance 路径；同事迁移后需显式适配路径，不能把找不到旧路径当内容不匹配。
- CLUT 206 signatures / 84 matches / 122 unmatched 来自特定 `frame_*.ppdmp` 采集集合。旧 coverage 检查不能证明所有命名方式和全部 GE captures 已覆盖。
- 原版游戏整体、完整章节、AI、原碰撞/伤害和所有动作尚未解析完成。已有 native GPU 或 UE 诊断图不代表正式 C++ M1 已验收。
- 历史文件中“未安装 SDK”“UE 从未编译”等结论属于当时阶段，优先采用本页及对应终态证据。
