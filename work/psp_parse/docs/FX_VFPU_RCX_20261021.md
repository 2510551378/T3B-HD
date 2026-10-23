# PPSSPP VFPU RCX 随机算法恢复

本阶段恢复了 PPSSPP v1.20.4 的 `vrnd_init`／`vrnd_generate` 算法，并加入生产 `T3BGEVfpuRandom`。这恢复的是确定性算法和 RCX 状态布局；本节点在原版运行时的 RCX 初值仍未采到，因此没有替换 type23 的实际观察 VRNDF2 输入。

[生产算法验证](../out/FX_RANDOM_MODIFIERS_20261021/vfpu_runtime_v5/verification.json) · [原 type23 随机边界](FX_RANDOM_MODIFIERS_20261021.md) · [PPSSPP 固定源码](../raw/ppsspp_v1.20.4_vfpu_reference/MIPSVFPUUtils.cpp)

实现严格保留原算法：

- 默认 RCX：`[1,2,4,8,0,0,0,0]`。
- seeded init：每个 RCX word 使用 seed 的低／高 16-bit 与 4-bit nibble，并保留 `0x3F800000` 的 1.0 mask。
- generator 从 8 个 RCX words 解包 A/B/C/D/E；A 使用 `69069*A+1`，B 使用经典 xorshift，C/D 使用 Pell-like 更新，E 使用原 64-bit carry 表达式；再按原 nibble／half 位置回写 RCX。
- VRNDI 返回完整 generator word；VRNDF1／VRNDF2 只替换指数／mantissa 的对应范围，保持原 bits。

独立 probe 用 6 个 seed／kind case、48 次生成调用逐 bit 比较 production C++ 与 Python reference，全部通过；非法范围和输入边界由已有 probe 约束。实现源码快照和 binary SHA 保留在 `vfpu_runtime_v5`。

`ApplyOriginalType23ModifiersFromRCX` 已接入 modifier core 的可选路径：它按原 channel 顺序消费每个启用 channel 的三个 VRNDF2 输出，再调用已验证的 type23 算术。固定 synthetic seed `0x12345678`、6 个生成 vector 的 bridge 实测通过；该路径只有在调用者明确提供 RCX 状态时才启用，默认仍使用实际观察 vector。

这个算法不能反推出游戏节点的初始 RCX。前轮 type23 证据只保存了 VRNDF2 执行后的实际向量，并确认其 `[2,4)` 范围；S/T/D prefix 与 RCX 控制寄存器不在 PPSSPP `cpu.getAllRegs` 输出中。本阶段没有把宿主随机数或默认 RCX 当作原版节点状态。

正式 UE module、原版 seed 采集、完整 type23 PRNG 时间线、动作／矩阵 join 和 M1 仍未完成。原 ISO、slot0、INI 与 185 个 UE packages 保持原 SHA。
