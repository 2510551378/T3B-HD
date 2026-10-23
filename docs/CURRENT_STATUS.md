# 当前交接状态

更新：2026-10-23。最新实现为 [UE M1 v4 战斗切片](UE_M1_V4.md)；[v4 Release 目标](https://github.com/2510551378/T3B-HD/releases/tag/runtime-assets-20261023-v4)等待运行包交付验证与上传。正式目标仍是独立 PC 高清重制，当前使用 UE Editor-hosted 开发工程。

## 已有证据

| 项目 | 事实与范围 |
| --- | --- |
| 引擎与工具链 | UE 5.8.4 / CL 58902052 / module BuildId `55116800`；MSVC 14.44、Windows SDK 10.0.22621.0、.NET Framework 4.8 SDK；Editor target 实际编译通过 |
| Aya / 武器 | 44 source bones、106 packets、3,456 Aya 顶点；原枪 243 顶点；60 帧同步 pair；reference / approach_fire 共用相位及 120 ms PC 循环过渡 |
| 材质 | 街景和角色共用按序主深度路径，修正 Aya 透体和异形覆盖；原 CLUT、UV 和 alpha 保留；原版完整光照/fog/stencil 尚未复现 |
| 场景与敌人 | 街景 140 draws / 31,656 顶点 / 81 材质状态；一个 11-bone 原版 Twisted；8,551 个可见网格三角形用于碰撞适配 |
| 玩家与射击 | WASD / Shift、越肩相机遮挡、锁定、真实枪口方向准星；场景与实际 posed enemy 三角形做同一有限射线的最近命中选择，墙体优先阻挡 |
| 战斗规则 | 敌人追击 55 cm/s、近战 20 damage；双方 100 HP；每发 25 damage、30 发弹夹、射击间隔 0.22 s、装填 1.2 s；受击反馈、死亡和重启 |
| Overdive | PC 镜头适配：0.32 s 进入、1 s 停留、0.32 s 返回、3 s 冷却；尚无原版宿主/意识转移系统 |
| 实际 UE 验证 | 最终模块 NullRHI 和 D3D11 严格战斗检查均 14 项通过；D3D11 记录 4 shots / 4 hits / enemy HP 0、Overdive 1 次返回；外侧 Overdive 截图已目视确认无穿躯体 |
| 独立源码检查 | 57 source-data + 29 动作 + 41 碰撞，共 127 项；CI 不替代 UE 构建或画面检查 |
| 运行资产 | 655 个原资产；Release 另含 C exe / SDL2 / 自有 UE module，未包含 UE 引擎；v4 冷 clone 交付验证与公开发布仍在进行 |
| 高清化 | 原版资源已接入；可选 4× atlas 重采样仅为原型；脸部、服装细节重建和完整高清美术尚未完成 |

v3 的材质与连续动作证据保留在 [历史报告](UE_M1_V3.md)，其修复已包含于 v4。旧运行包的冷 clone 交付记录见 [v2 delivery](evidence/runtime_bundle_delivery_v2.json)，不能据此推断 v4 已完成相同验证。`docs/evidence/` 是本机报告副本，部分大文件和绝对路径仅在原机器存在。

## 启动与操作

安装匹配的运行包后，`scripts/run_unreal.ps1 -Game` 进入战斗；`-Game -ReplayOnly` 保留原 Spectator 与 source probe 路径。运行包尚未 cooked，需要 UE Editor host。

- WASD 移动，Shift 跑，Mouse 调整观察方向。
- RMB / Tab 锁定，LMB 连续射击，R 装填，Backspace 重启。
- E 触发锁定目标的 Overdive 镜头；Esc 释放鼠标，单击重新捕获。

准星投影实际原枪管射线。Mouse 上下当前只调整镜头，不改变已恢复源动作的枪管 pitch；锁定只校准水平 yaw。碰撞、敌人行为、伤害、死亡表现和 Overdive 为 PC M1 规则，未冒充原版格式恢复结果。

## 接手后优先做

1. 完成 v4 冷 clone 安装及发布包验收，再测试 cooked standalone Game。
2. 恢复更多 idle / strafe / 受击 / 倒地动作及原状态/事件调度；当前 approach_fire 不是完整 locomotion。
3. 继续原版光照、fog/stencil 和更多姿态的材质复核，再推进高清模型/贴图。
4. 恢复真实武器 socket / muzzle 语义及 pitch 控制；真实右手 timeline 当前 loaded、未绑定，不混接不同采集。
5. 扩展原碰撞、AI、伤害和章节解析，逐步替换 PC 适配规则。

## 数据与工具限制

- source bundle 的 `coordinates.pc_to_ue` 文本仍有旧描述；实际 core `ToUE` 是 **`(PC.z, -PC.x, PC.y) * 100`**。不要据旧元数据二次变换资产。
- `stage_source_bundle.py` 是早期生成器，重跑可能丢失后加的 FSD/action/marker manifest 字段；先备份并扩展对应 gate。
- 某些验证器读取原机器绝对 provenance 路径，迁移后须显式适配路径。
- CLUT 206 signatures / 84 matches / 122 unmatched 来自特定采集集合，不能代表全部 GE captures。
- 历史记录中的“未安装 SDK”“UE 从未编译”“尚未移植战斗”属于当时阶段，以本页及最新证据为准。
