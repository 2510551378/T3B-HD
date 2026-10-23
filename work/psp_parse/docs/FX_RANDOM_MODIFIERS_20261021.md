# 原版 type23／24 内部目标与随机扰动恢复

本阶段恢复所选原枪 descriptor `10c78` 的两类随机 modifier，纠正了仅按 callback argument offset 判断目标的解释。新增生产 `T3BGEEffectModifiers`，真实执行与原返回状态一致。正式 UE、完整动作／FX 时钟和可玩 M1 尚未完成。

[真实指令审计](../out/FX_RANDOM_MODIFIERS_20261021/audit_v1/verification.json) · [生产 core 执行](../out/FX_RANDOM_MODIFIERS_20261021/runtime_v2/verification.json) · [原资源绑定](../out/FX_RANDOM_MODIFIERS_20261021/source_bank_v2/source_modifiers.json) · [完整 checkpoint](../out/FX_RANDOM_MODIFIERS_20261021/checkpoint.json)

## 实际目标：参数 offset 不等于内部写入目标

原 definition2/type23 的 declared parameter offset 是 `+60`，definition4/type24 为 `+80`。此前记录这些 ABI 参数和别名是准确的，但不能据此把 type23 认定为百分比缩放 modifier、把 type24 认定为颜色 modifier。

两者的 key callback 会读取 context `+90` 的 node、context `+94` 的 active definition，再用 active definition `+4` 的 index 查询 `+8` 指向的 u16 offset table。实际目标为 `node + 60 + table[index]`，独立于传入 a3 的 declared parameter address。

| 原 class | 完整入口范围 | 传入参数 offset | 本 descriptor 的内部目标 offset |
|---|---|---:|---:|
| type23 | `08bb8cbc..08bb9048` | `60` | `20` |
| type24 | `08bb94fc..08bb98e4` | `80` | `60` |

这里 offset 均为十六进制、相对 node 的 parameter-window base。原 header、实际 table index／u16 值和 FEP relocation 逐 byte 核对，目标寄存器 t9／s1 也由实际 loop stop 确认。内部 `+20` 属于此前 type6 的三分量状态区，`+60` 是已恢复的百分比／转换值区。三分量的具体空间／角度语义仍不凭字段位置命名。

## 实际采集

扩展既有 `trace_fx_property_callbacks.js` 的可选 `FX_PROPERTY_RANDOM_DETAILS=1`；默认采集路径保持。隐藏 portable PPSSPP 使用原 slot0／INI 副本，通过 debugger RPC 操作输入与单个自有 breakpoint，没有桌面自动操作。

最终 `key9_random_v2` 完成原 9 类 key callback；对 type23／24 额外采集：原 target lookup、static byte tables、vector cache／constants、每 channel loop、随机值生成后、写入前 stack、写入后窗口，以及每次标量 RNG 的真实 entry／return、seed pointer／seed。始终单个自有 breakpoint，结束释放输入／断点并停止自有进程（PID 97244，session 73200 exit0）。

type23 实际启用 channel0／1，mode 都为0，channel2 关闭；观察到两组原 `vrndf2.t` 输出。type24 实际仅 channel0 开启、mode2、独立 XYZ，共调用3次标量 helper。

## 两种随机来源

type23 使用 VFPU `vrndf2.t`，结果位于 `[2,4)`。原 cache 本次为 `(3,3,3)`，计算 `F32(F32(random − center) × amplitude)`，再叠加目标区对应的三分量，并将该 vec4 的 W 设为1。它不会在这里重新求值当前三分量。

mode1／2 先将 amplitude 乘0.5；**两个原 type23 分支最后都执行 vsub**，即再减 half-amplitude。不可照搬 type24 的 mode1 正偏移行为。该差异由固定原指令的合成路径检查发现，生产实现已按原码修正。真实样本仍只覆盖 mode0。

VFPU RCX 随机种子控制尚未导出。生产 type23 API 显式接受已观察的 VRNDF2 vector，不替换为宿主随机数，也不宣称恢复了 VFPU PRNG 的种子推进。原指令 oracle 从 VRND 后真实输出继续重放；该指令会消费 prefix，后续向量算术逐 checkpoint 核对。初始 prefix controls 仍不是 debugger 直接导出的数据。

type24 调用原 `08afc000..08afc034`。它通过 `08c37594` 指针找到对象，更新其 `+58` seed：

```
seed = (seed * 1103515245 + 12345) mod 2^32
return seed & 0x7fffffff
```

新实测链为 `bf8665f8 → 551b2ad1 → b2431936 → 8e046037`；后两次返回值分别屏蔽为 `32431936`、`0e046037`。原始 seed 保留全部32 bits，不能每步先截为31 bits。

整数返回先按原 cvt.s.w 转 F32，再依次乘 `2^-31`、2、amplitude，逐步 F32 舍入后减 amplitude。mode1／2 使用 half-amplitude，并分别再加／减 half；其他 byte mode 走原 symmetric 分支。独立轴标志关闭时只调用一次 RNG，并把 X 生成值用于三轴；开启时依次生成 XYZ，零 amplitude 的轴也消耗 RNG。

type24 将结果加到内部目标对应 vec4，W 设1；对 channel0 还将百分比 XYZ 乘原 F32 `0.01`，转换后 W 设0。当前真实转换值由 `(2.5,2.5,2.5)` 变为 `(2.1648917198,1.8926726580,2.5)`，percent 为 `(216.4891663,189.2672729,250,1)`。

这只证明给定原 seed 与相同调用顺序的 helper／callback 行为；其他调用者如何推进同一对象的 seed 尚未全部跟踪，不能给每个节点随意新建独立 seed。

## 原指令与生产实现验证

`analyze_fx_random_modifiers.py` 先复用完整原 rifle／FEP／9 callback ABI 审计，再核对所有新 sidecar 身份和 target lookup。`replay_fx_random_modifiers.py` 按实际原 MIPS／COP1／VFPU words 逐条执行，未知 opcode／未保留读取／越界写入拒绝。

- type23：162条原指令；type24：201条。完整512-byte有界参数窗口与真实返回相同，中间每个 loop／ready／advanced 的参数和 VFPU data、生成 vector、标量 seed／返回值也匹配。
- VFPU debugger scalar register encoding 显式转换为已固定的 physical layout；没有把 debugger 数组下标直接当 vector lane。
- 原 quad load 会读旧 stack W lane，使用生成算术之前第一 loop stop 保留的 stack input；其后原 vone／vzero 按原码覆盖 W，没有把中间未知值默认为0。
- 生产 `T3BGEEffectModifiers.h/.cpp` 实际 C++17/O2、`-ffp-contract=off` 执行：2个真实 callback 的64-byte目标各自逐 bit 相同，共32个目标 float 分量；type24 seed 同原。目标窗口大小不认领为原 allocation size。
- 另14个明确合成的原 opcode cases 覆盖 mode0／1／2／255、三 channel、独立／共用轴、全关闭；它们不增加真实原版样本覆盖。6个非法接口输入实际拒绝。
- `negative_evidence_v2` 的3份 SHA 一致坏证据（scalar seed、VRNDF2 vector、内部 target）在指定原始数据／中间值 gate 拒绝。

生产 API 位于 UE module，保留 source 单位，使用显式 mutable seed／observed vector 输入并在成功后原子更新目标。当前仍是独立执行，未接成完整 authored property scheduler 或切换默认 M1。

## 失败记录和保护

`key9_random_v1` 的 debugger capture exit0，但 RNG 多次调用复用了文件名；最终审计确认旧 sidecar hash 不符，因此不接受其完整 RNG 链。修正名称加入 call ordinal 后重新采集 v2，v1及实际 executed JS保留。两个自有 emulator 均已停止，原输入文件未改。

首次 offline oracle 把同一 VRND PC 的两次输出存成一个值，已改为按 PC 消费有序观察；还补齐生成前 stack W 输入与原 vzero。旧代码／失败说明保留。首次生产 runtime_v1 对 synthetic type23 mode1 不符，按原 vsub 修正，runtime_v2 通过。首次 negative finalizer 的错误样本已被更早的 generated-vector gate 正确拒绝，但测试预期了较晚的 VFPU error label；修正标签，新建 v2目录，未覆盖 v1。

原 ISO、slot0、INI 和185个既有 UE package SHA 全部保持一致。当前12份工具／生产源码已冻结；未启动 UE或重试UAC安装。

后续优先把内部 target lookup 与这些 modifier 接入原属性顺序／时间状态，继续 type6 求值、VFPU RCX seed与原单位／秒数关系。完整角色动作、PC相机、命名手骨／枪口、AI／原碰撞／伤害、高清化和可玩 M1 仍待完成。
