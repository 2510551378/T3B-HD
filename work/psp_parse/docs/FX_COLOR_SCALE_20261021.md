# 原版 FX 颜色曲线与百分比缩放恢复

本阶段恢复同一原 rifle/descriptor `10c78` 的 type16 RGBA 与 type7 百分比数值更新，并在生产 C++ core 中复现真实返回内存。证据根为 `out/FX_COLOR_SCALE_20261021/`。这延续前轮 UV 曲线；完整 FX 生命周期和正式 M1 接入仍未完成。

## 实际证据与 VFPU 范围

新增 `reset21_color_v1` 隔离 PPSSPP 采集：精确识别原枪、原 FEP、source records 与 geometry 后，保存21次分派→callback entry→return；type16 的3次 reset 还各保存内部 evaluator 的分派、真实入口和返回。整个采集始终只有一个自有 CPU breakpoint。结束时断点和输入释放、自有进程终止，原 slot0/INI 没有写入。

最终 `color_scale_audit_v3` 将新采集与前轮已成功的 `key9_v4` 交叉审计。先重新验证实际枪对象指针链、243 vertices/VTYPE522、FEP 原 bytes及 relocation、class/parameter binding、原码、三阶段 tick、调用 ABI；随后逐原 opcode 执行对应 scalar MIPS 与 VFPU。支持当前使用的 lv/sv、mtv、vadd/vsub、vscl、vzero、vpfxT、vmin/vmax 和有限值域，遇到未知指令、未保留的读取或越界写入即拒绝。

| 实际操作 | 次数 | 原始 float 分量 |
|---|---:|---:|
| type16 普通 key | 1 | 12 |
| type16 reset | 3 | 36 |
| reset 内部颜色 evaluator | 3 | 36 |
| type7 普通 key | 1 | 8 |
| type7 reset | 3 | 24 |
| 总计 | 11 | 116 |

每个操作都比较完整512-byte有界参数窗口，包含未改写部分；这不是把窗口大小认领为原 allocation size。参考语义来自已固定 SHA 的 PPSSPP v1.20.4 `MIPSIntVFPU.cpp`、`MIPSVFPUUtils` 等5份原始源码，沿用已验证的 VFPU register mapping。

debugger 的 getAllRegs 没有导出 S/T/D prefix controls。对3次颜色 reset，可由紧邻的同节点 type7 无分支尾部 `vzero.s`、随后纯 scalar 的 dispatcher/record finder 确认 prefix 已被消费；对应完整运行时原码和相邻 stop 都保留。对3次内部 evaluator，wrapper 最后的 `vsub` 消费所有 prefix，后续仅存储和间接调用。故这6次入口有原调用链依据确认默认 prefix。其余5个 key/scale 入口的默认 prefix 未直接证明，当前 default-prefix 回放与实际结果相容；不把它们扩大为任意 prefix 的完整 VFPU 语义。

## type16 颜色状态

共享参数块 `+0/+10/+20` 分别为当前 RGBA、base RGBA、velocity RGBA，每组4个 F32。原输入 key 的前32 bytes为 base 与 velocity。

- 普通 key：`08b8f898..08b8f954`，在当前时间分别计算状态和旧 key 的值，将差叠加到新 key；velocity 也保留差值。当前 RGBA 复制新 base，原函数这里不执行 clamp。
- reset：`08b8f9b4..08b8fa60`，在 f13 旧时间累计，再按 f12 新时间重基，随后真实调用 `08b8f954` 求值。
- evaluator：`08b8f954..08b8f9b4`，分别 F32 乘加得到 `base + velocity*time`，再按原 vmin/vmax 限制到 `[0,255]`。

原有限值 vmin/vmax 相等时选 T operand，clamp 的下界因此把负零变为正零。`std::clamp` 会保留输入负零，不能直接替换。实现使用源通道的0–255单位，没有提前归一化到0–1，也没有混入已有 renderer 的 double-alpha 或 blending 规则。

本次 authored RGBA 为 `(128,56,8,48)`，velocity 全0，所以真实样本不含颜色渐变。非零 velocity、不同 key、clamp 和 signed-zero 的覆盖来自明确标为合成的原指令样例，不能称为新增原版动画。

## type7 百分比与缩放数值

参数块前4个 float为转换后的值，后4个为百分比状态。普通 key `08b94968..08b949d0` 对前三个百分比分量执行 `F32(F32(statePercent − previousKey) + currentKey)`，再乘原常数 `0x3c23d70a`（F32 0.01）；转换后第四分量置0，百分比第四分量保留。reset `08b949d0..08b949fc` 把当前前三个转换值分别乘100写回百分比，百分比第四分量置0，前四个转换值保持不变。

新采集第一个 reset 的 Y 百分比从 `248.5345916748047` 变为 `248.53457641601562`，是原往返转换导致的1 ULP变化。不能将这个过程优化成“保持原百分比不变”。实际转换值约为 `(2.0192435,2.4853458,2.5)`，已经包含其他共享 callback 的贡献，并非每帧都应重置为 authored 的 `(2.5,2.5,2.5)`。

## 生产代码与原资源导出

新增生产 `T3BGEEffectColorScale.h/.cpp`，提供颜色的 Change/Wrap/Evaluate 与百分比的 Change/Reset；`ge_effect_color_scale_probe.cpp` 实际调用同一 core。`runtime_color_scale_v2` 使用 g++ C++17/O2、`-ffp-contract=off` 编译执行，11个真实操作的116个原始 float分量逐 bit 相同。scale 传输格式额外补齐的4个零不计入原始分量数量。

另10个明确合成的原 opcode 样例覆盖小数时间、不同 key、非零颜色速度、越界颜色、负零、不同百分比、第四分量保留/置零及舍入变化；5个非法输入实际拒绝。源码快照、编译参数、exe、输入、独立 reference、输出及 SHA 均保留。`negative_evidence_v1` 还将颜色输入 base、缩放返回 W、内部 callback 的 RA 分别改为 SHA 一致的坏证据，3个实际 auditor 调用均在指定 gate 拒绝；原采集文件不改写。

`source_bank_v2/source_color_scale_bank.json` 导出4份原始 payload 的已消费字段：

| 原记录 | source offset | 已解码字段 |
|---|---:|---|
| initial type7 | `116f0` | XYZ percent `(250,250,250)`，12 bytes |
| time-key type7 | `11990` | 同上 |
| initial type16 | `11730` | RGBA `(128,56,8,48)` 与零 velocity，32 bytes |
| time-key type16 | `119d0` | 同上 |

8个真实普通 key/reset 的新旧 operand 与原 payload 逐 byte 核对。原 reset order `[0,1,3,5,6,7,9]`、time-key order `[0,1,2,3,4,5,6,8,9]` 也与实际回调顺序相同。definition2/type23 与 definition3/type7 共用 `+60`，definition4/type24 与 definition5/type16 共用 `+80`。type23/24 的行为尚未恢复；导出保留别名和顺序，不将它们拆为独立状态。

## 当前边界与下一步

原 ISO、slot0、INI 和185个现有 UE包同前基线哈希，见 `source_protection.json`；当前工具快照与 launch-time executed observer/runner分别保存。本阶段没有启动 UE、写入 Content、操作桌面或重试 MSVC/SDK 安装。

这是原属性 core 的独立执行，正式 UE module、默认 M1 绑定和最终画面仍待验证。还没有把 type16 颜色经 parent/material 调制、palette 颜色分支、整数打包一路追到实际 draw 的 GE color/material命令；先前 UV 的 CPU 命令证据不代替这项验证。原前置类23/24、type6随机/旋转参数、其他 FEP branches、单位换算和完整生命周期也继续待恢复。

下一步可追同一 type155 handler 的 `08b60080` 颜色绑定：它含普通 RGBA打包、单色 palette 调制和其他更新分支，不能只把 state RGBA 直接当最终材质。`08c005bc → 08c01998` 的 mode7 路径写55/58/56/57 material命令；需补实际输入、分支来源、palette bytes、DL cursor和返回命令证据后才能接入 M1。
