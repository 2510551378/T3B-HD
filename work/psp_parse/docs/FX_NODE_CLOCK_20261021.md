# 原版武器 FX 节点时间推进、回绕与渲染相对时间

本阶段恢复原版数值路径，独立 C++ core 的实际执行通过。证据根为 `out/FX_TIME_SOURCE_20261021/`。这使后续特效时间驱动有了原版算术依据；完整 FX 生命周期、参数曲线和正式 UE/M1 接入仍待完成。

## 实际观察与身份

最终采集 `node_clock8_v6` 使用隔离 PPSSPP v1.20.4、配置和 slot0 副本隐藏运行。在原 dispatcher `08b69d64` 选择 type155/ID19 的实际 callback `08b9a514`，确认原 FEP descriptor `+10c78`、definition index9、原 FEP192 bytes 和完整 rifle 指针链。原枪为3个 source records、243 vertices、VTYPE522；全量 geometry SHA 与前轮一致。

移除选择断点后，仅保留一个写入且值变化时触发的内存断点，监测该节点 `N+30` 的4 bytes。每次保存原 node、parent、descriptor、context、枪对象身份、GPR/FPU 和原指令；代码同时保存 physical/original/decoded/disasm，独立核对固定 module bytes。没有向游戏内存写入值。

最终9个实际写入停止点构成8个完整观察：

| 原 writer | 实际时间变化 | 完整次数 |
|---|---|---:|
| `08b683f8`，`swc1 f12,30(a0)` | `0 → 1`、`1 → 2` | 6 |
| `08b68e4c`，`swc1 f12,30(s0)` | `2 → 0` | 2 |

最后一次待写入 `2 → 0` 没有后续实测值，明确排除。写入结果是在**下一个真实写入停止点**观察；没有把重复的 single-step 停止事件当成指令已执行的证明。advance 的断点实际 PC 是 `08b683f4` 的 COP1 分支，真实 store 在其 delay slot `+4`。

`clock_audit_v6/verification.json` 独立重读全部 bytes，校验单断点所有权、原源码身份、寄存器、有效写入地址、FPU store source、后续真实字段以及 live descriptor 的原始时间区间 `[0,2)`。该节点所观察 effective delta 为1，parent rate 为1；实际动态样本仍只有整数0/1/2。

## 恢复的数值语义

1. 节点推进：原 `08b683e8 add.s` 计算 `F32(nodeTime + effectiveDelta)`，`08b683f8` 写回。实际 FPU22 与 parent `+130` 相同。
2. parent updater 的静态路径 `08b68118..08b68744` 包含 carry `P+134`、有效 delta `P+130` 和两个 node lists `P+180/P+184`。上层 manager `08b68744..08b68840` 的普通路径将全局 delta 乘 `P+1b4`；flags 等路径可改为0。这些静态结构不是完整状态机移植。
3. 回绕函数 `08b68dc0..08b68e6c` 先调用原边界属性更新 `08b689b8` 与 `08b68d78 → 08b68b8c`，然后重新读取节点时间。被恢复的算术从这次重新读取开始。
4. 回绕区间 start/end 是 descriptor `+c/+e` 的 **u16**。原 `trunc.w.s` 取整数，`SUBU` 按 uint32 回绕，然后 signed `DIV/MFHI` 求余；独立保留 `F32(time − F32(integer))`，再按原顺序 F32 加回 start 和 fraction。不能直接换成 `fmod`，也不能略过边界回调后直接宣称完整效果相同。
5. 渲染 dispatcher 的另一条时间参数是 `F32(nodeTime − signedStart)`。start 来自 `N+4c` 指针表当前 definition index 对应 record `+4` 的 **signed S16**；null record 直接保持原 bits。它与 matrix helper 的 f12 scale 参数是不同调用阶段。

`update_static_v1` 保留 updater/manager 原始 bytes 和反汇编。完整 module SHA 为 `b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f`；原 FEP section SHA 为 `97443c71b1c1d644f323c6ff611afb740329cfe11a47a711f39dc59de06ec802`。时间单位尚未证明是秒，不硬编码30 Hz。

## 实际生产 core 与验证

生产 `T3BGEEffectClock.h/.cpp` 提供 `AdvanceOriginalEffectTime`、`WrapOriginalEffectTime` 和 `RelativeOriginalEffectTime`，保持独立 F32 运算，限制到已支持的有限值、有效 u16 区间和 int32 trunc 域。Wrap 输入明确是原边界回调执行之后的时间。

`ge_effect_clock_probe.cpp` 实际调用同一生产 core。`verify_effect_clock_runtime.py` 在 `runtime_clock_v1` 中使用 g++ C++17/O2、`-ffp-contract=off` 编译执行：

- 8个真实观察写入和1个真实 dispatcher 参数，共9项输出 F32 bits 全同。
- 9个小数/负值/极值回绕样例由独立原 opcode interpreter 给出 reference，另4个 signed-start/null-record 样例，合计13项通过。它们明确是合成数值样例，不增加原版姿态/动态覆盖。
- 6个非法输入（截断、尾部多余 bytes、无效区间、未知 operation、非有限值、超出 trunc 域）实际拒绝。
- 源码快照、编译/执行参数、exe、输入、reference、输出及 SHA 全保留。

`negative_evidence_v1` 还实际运行独立 auditor，3个保留一致 SHA 的合成坏证据分别修改后续真实字段、effective delta 寄存器及 parent 字段、live interval，全部在对应独立 gate 被拒绝。原数据没有改写。

## 保留的失败与范围

`node_clock12_v1` 未识别 COP1 delay-slot store；v2 和 `node_clock6_v3` 的 stepInto 返回相同 PC/ticks，未观察到实际写入效果，均保留失败。`node_clock8_v4/v5` 的 successive-write 观察成功，但原 descriptor/完整身份字段分别较窄，最终结论使用 v6，不回填旧数据。

全部隔离采集进程已终止，断点和输入已释放。`source_protection.json` 核对原 ISO、slot0、INI 和185个现有 UE 包与前基线相同；current 工具快照与 launch-time executed observer 分别保留。

正式 UE C++ module 未构建，默认 M1 绑定未替换；未宣称高清美术、伤害/AI/碰撞或可玩验收完成。工具链安装记录仍是 Windows 提权取消、installer 未启动的终态，本阶段没有重试安装。

下一步追踪 `08b689b8`、`08b68b8c` 的实际属性 dispatcher，尤其 `08b68ce4` 的动态 callback，恢复颜色、UV、局部矩阵参数曲线和原 FEP 时间键。随后补齐时钟上层调用的单位与生命周期，再接正式 M1。
