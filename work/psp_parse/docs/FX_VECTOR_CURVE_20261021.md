# 原版 type6 向量曲线与连续状态推进

本阶段恢复原 rifle／descriptor `10c78` 的 type6 key、wrap 和 vec4 evaluator，新增生产 `T3BGEEffectVectorCurve`。同一程序只载入一次初始状态，先执行已恢复的 type23 modifier，再连续运行原节点的4次普通求值和2次完整回绕；全部7组四个 vec4 状态逐 bit 同原版。不是每步装入新的状态快照。

[连续生产 core 验证](../out/FX_VECTOR_CURVE_20261021/continuous_runtime_v1/verification.json) · [原指令审计](../out/FX_VECTOR_CURVE_20261021/combined_audit_v3/verification.json) · [独立操作与合成样例](../out/FX_VECTOR_CURVE_20261021/runtime_v4/verification.json) · [原 keys](../out/FX_VECTOR_CURVE_20261021/source_bank_v1/source_vector_keys.json) · [保护与源码快照](../out/FX_VECTOR_CURVE_20261021/checkpoint.json)

## 实际采集与绑定

沿用 exact rifle、243 vertices／VTYPE522、FEP／descriptor／definition／虚表与原 opcode 身份检查。新增可选 `FX_PROPERTY_VECTOR_DETAILS=1`，保留完整 type6 wrapper／evaluator、common helper 和 vector add／sub 原码；采集 helper 的 dispatch／entry／return 与 wrap 内 evaluator 的三阶段。

- `reset21_vector_v1`：原7类 reset ×3轮，type6 wrap3次和内部 evaluator3次。
- `key9_vector_random_v1`：9类 key，包含 type6 helper 与 type23／24 的完整随机观察。
- `key9_evaluate6_v1`：上述 key 后，再采6次实际 evaluator，识别出普通调用返回 `08b68ff0` 与回绕内返回 `08b944e4`。
- 最终 `key9_state6_v1`：key 后按实际调用记录 evaluate／evaluate／wrap 两轮，保存完整 wrap 入口的 current／previous record、f12／f13、返回状态。原 state 在这些调用间逐 byte 连续，type23 返回状态与第一次 evaluator 输入相同。

四个隐藏 portable PPSSPP 使用原 slot0／配置副本。始终单个自有 CPU breakpoint，RPC 输入／断点清理，全部进程已停止；最终 session6351／PID95464 exit0。没有桌面操作、guest memory 改写或原存档保存。

## 状态与原运算顺序

type6 参数 offset 为 `20`，也正是前轮确认的 type23 内部目标。64-byte状态依次为 current／base／velocity／acceleration，每组4个 F32。这里只确认数值字段与消费者，没有凭字段位置命名为某个骨骼、Euler角或世界坐标。

| 路径 | 原函数 |
|---|---|
| key wrapper／XYZ helper | `08b943d4..08b94438`／`08b65f48..08b6616c` |
| evaluator | `08b94438..08b9447c` |
| wrap wrapper／XYZ helper | `08b9447c..08b94508`／`08b662e0..08b664e0` |
| add／sub helper | `08bfcff4..08bfd05c` |

每个算术步骤独立 F32 舍入，禁止 FMA。关键区别：

1. evaluator 使用 Horner 顺序：`base + ((acceleration × F32(time × 0.5)) + velocity) × time`。四个 lane 全部计算，不能把 W 固定为0或1，也不能改为另一种乘加展开顺序。
2. key helper 只更新 XYZ，保留 base／velocity／acceleration 的旧 W，随后 wrapper 将全部 base vec4 复制到 current。helper 的 state-value 项确实复用了 previous-key acceleration，而不是 state acceleration；差异由非零 acceleration 的原指令样例覆盖。
3. wrap 在旧时间累计原状态，按 previous／current key 重基 velocity、acceleration，再减去新时间的 carry，最后真实调用 evaluator。carry 中 acceleration 先乘0.5再乘新时间平方，保持原顺序。key base 并不在这里直接覆盖累计状态。

原 record 只消费三个 XYZ vec3，间隔为16 bytes，W padding不当作 key数据。两个确认的原 payload 在 FEP `11690`／`11930`，XYZ均为 base `(0,0,45)`、velocity `(0,0,-40)`、acceleration `(0,0,0)`。当前前缀导出44个已读取 bytes，不认领 allocation size。

## 同一节点的连续生产执行

`ge_effect_vector_chain_probe.cpp` 实际链接当前 modifier 与 vector curve 两份生产 core；transport只给出一次 modifier前状态、实际 VRNDF2 输入、原调用时间与 key operands，没有逐步输入 before-state。

| 原调用 | relative time | wrap old time | current Z | current W |
|---|---:|---:|---:|---:|
| evaluate | 0 | — | 206.5113831 | 1 |
| evaluate | 1 | — | 146.3463135 | 2 |
| wrap | 0 | 2 | 86.1812439 | 1 |
| evaluate | 0 | — | 86.1812439 | 1 |
| evaluate | 1 | — | 26.0161743 | 2 |
| wrap | 0 | 2 | -34.1488953 | 1 |

两次 wrap 的新旧时间直接来自该次原 wrapper 的 f12／f13，key pointers／payload也在入口实测；没有从其他运行借状态或推算旧时间。modifier后状态及6步结果共7×16个 F32、448 bytes，全同原记录。W 的1／2变化是 evaluator 对实际 base／velocity W 的计算结果。

这些时间仍是原 source units。普通 evaluator 中未使用的 f13不能解释为 old time；Node+30 在 wrap callback 内也尚未被后续时钟 writer 改回0。原 source units 与秒的换算、调用调度／帧率与完整生命周期尚未恢复。

## 独立审计与生产 core

最终 `combined_audit_v3` 重做所有原 rifle/FEP/ABI／runtime code检查，并执行13个真实操作：key1、独立 reset capture的 wrap3和 nested evaluate3、同节点连续 evaluate4／wrap2。完整512-byte有界窗口匹配；有内部观察时还比较 helper／evaluator各阶段窗口、SP／RA与所有已初始化 VFPU data lane。

生产 `T3BGEEffectVectorCurve.h/.cpp` 提供 Change／Wrap／Evaluate，有限值、默认入口 prefix 数值域，保持 W 和源 F32 运算顺序。`runtime_v4` 实际 C++17/O2、`-ffp-contract=off`：13个真实操作的208个完整状态分量逐 bit相同，另10个明确合成的原 opcode样例覆盖不同 keys、非零 acceleration、小数／负时间和 signed zero，6个非法输入拒绝。

S／T／D prefix controls 未由 debugger直接导出。wrap内部 evaluator 之前的最后 vsub 消费prefix，后续纯scalar setup不改它；其他入口标为默认prefix回放与实际相容，不外推任意非默认 prefix。连续状态 proof 不等于恢复 VFPU RCX 种子：type23依然显式使用实际观察的随机 vector。

`negative_evidence_v1` 的3份 SHA一致坏证据被指定 gate拒绝：错 wrap old time、modifier→第一次 evaluator 的 current carry断裂、错 wrap输出W。carry错误特意修改会被 evaluator覆盖的输入 current字段；单独最终输出可能不变，仍必须被真正的状态连续性检查发现。

首次 `runtime_v1` 中真实操作通过、合成 wrap不同key样例不符，原因是合成器在原 current／previous指针相同时覆盖了同一块内存；修正为两个显式合成区域后 `runtime_v2`通过，生产算法未因此更改。随后新增连续调用输入，`runtime_v3/v4`分别对应 evaluator-only与完整 state-transition采集，旧来源／输出不覆盖。

## 当前范围

原 ISO、slot0、INI和185个现有UE包SHA保持不变，19个当前工具／生产源码快照保留。没有启动 UE、重试工具链安装或切换默认M1。

当前证明的是同一原节点的连续数值状态，尚未把这条新状态链接到实际 GE matrix writer／最终画面，也不是完整 authored 动作或战斗时间轴。下一步追 type6输出到 handler局部矩阵／GE draw 的实际消费者，再接生产渲染；同时继续调度、秒数与VFPU随机种子。正式 UE构建、PC相机、原伤害／AI／碰撞、高清化和完整可玩M1仍待完成。
