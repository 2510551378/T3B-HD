# 原版武器视觉 FX 的完整 inline PRIM 窗口与生产几何解码

本轮补齐前轮每个 handler 仅首 PRIM 的缺口。当前默认observer的174个离线Mock回归通过；可选full-handler分支的证据来自下面的实际采集和独立审计。证据根为 `out/WEAPON_FULL_HANDLER_GE_20261021/`；原 ISO、slot0、INI 和185个已有 UE 资源包保持原哈希，模拟器均为独立副本、隐藏运行，原配置未改写。

## 实际数据与原结构

`trace_weapon_marker_ge_emit.js` 的可选 full-handler 模式在 callback-return 暂停点读取首 emitter cursor 到当前 DL cursor 的有界命令窗口。要求相同 DL context、单调 cursor、最多0x20000 bytes，保留原 uncached alias 和实际 memory.read 地址。每个 inline PRIM 都读取实际 vertices；不使用“相邻 draw 属于同资源”的猜测。

type155 还保存原对象指针、header、group、draw header 与 inner draw records。`analyze_weapon_full_handler_ge.py` 直接从固定 ULJM05798 module 的13条原 opcode核对字段来源，重新解码指针链和命令 words，不信任采样器提供的 count/label。

原 `08b5ee28` 的指令是 `26730044 addiu s3,s3,0x44`，group stride 确认为0x44。最初采集器曾假设0x38，已修正。`aimfire12_v1` 和 `strafefire16_v1` 实际都是单 group，只保存到使用字段+0x34，故0x38 bytes足以验证这些字段，但不能叫完整 group record；旧 producer 和 raw 数据均保留。`strafefire16_v2` 使用正确0x44 stride，保存完整 group。独立审计对原跨度与完整性分别标记；未将旧错误假设覆盖成成功的通用格式。

已实测的 type155 层级：

- object+0 → header；header+18为 group count，+1c为 group pointer。
- group stride44；group+1c为 draw-header count，+20为16-byte draw-header数组。
- draw header +0为 VTYPE，+4为 material index，+8为 inner count，+c为16-byte inner-record数组。
- inner record +0为 primitive，+8为 vertex count，+c为 vertex pointer；+4仍按 opaque word保留。

采集器没有用这些声明代替执行证据：每条实际 CPU PRIM 的格式/primitive/count/VADDR 必须与原 inner record 一致，首条 record 还必须等于原发射调用保留的 s3 指针。

## 全部子 draw 的 CPU/GE 对齐

在前轮验证过的首 draw（vertices+完整VIEW+原枪WORLD+主相机VIEW）锚点之后，逐条核对整个 CPU 命令窗口与 GE 中连续 PRIM。每个子 draw 的原 bytes、VTYPE、primitive/count、VIEW 都必须一致；窗口内已写的受支持 scalar raster state 也逐项对照。每条匹配保留实际 WORLD/VIEW/PROJECTION、CLUT、texture SHA 和材质参数，合并目录为 `full_visual_FX_subdraw_bindings.json`。当前type155路径中的 `08b5e3a8` 是inner-record循环调用PRIM emitter，不能只凭命中该PC将它认领为BONE矩阵写入。

| 采集与独立结果 | handler | CPU实际 PRIM | 精确对应 GE PRIM | 对应 GE帧 |
|---|---:|---:|---:|---:|
| aimfire12_v1 → full_correlation_v1 | 12 | 36 | 12 | 1 |
| strafefire16_v2 → strafe_full_correlation_v2 | 16 | 48 | 24 | 2 |

每个观察到的四-handler组合均为：type152/ID15的两个独立 handler各1个四顶点 draw；type155/ID18 的1个 handler包含14和15顶点两个 draw；type155/ID19 的1个 handler包含8个四顶点 draw。ID18的15顶点 companion 以及ID19的后7个 draw 现在都有原对象→实际CPU命令→GE的证据，不再只凭同原点推断。

共36个匹配子 draw，覆盖3个 GE记录帧，仍不是36种独立姿态或36次射击。材质仍是实际观察的2张 CLUT4/ABGR8888 原图，未作高清重绘。type152窗口的末尾还保留projection恢复；type155窗口末尾保留depth-write/cull/UV-offset恢复。不能把单 draw 的状态永久泄漏给下一批对象。

`matrix_math_v1` 与 `strafe_matrix_math_v2` 继续独立回放原 mode0/1、VIEW 指令；已观察 stage的输出逐 bit相同。entry prefix controls仍未导出，结论不扩大到所有 VFPU/JIT/mode。

## 实际生产 C++ decoder

新增 `T3BGEEffectGeometry.h/.cpp` 的 `DecodeOriginalEffectStrip`，支持当前实际无权重/unlit PRIM4 VTYPE102（stride10）与11e（stride16）。它保留PSP局部坐标，读取u16 UV与s16 position；UV按原GE scale/offset分别F32舍入一次，颜色取原RGBA8888或无COLOR路径的原ambient RGB/alpha。原strip按奇偶展开，退化三角形也保留。该函数不推测变换、effect时钟或角色骨骼名。

`ge_effect_geometry_probe.cpp` 实际调用同一生产函数。`verify_effect_geometry_runtime.py` 从上述36个已对应GE的原始子 draw 构建输入，独立重读raw与registers，比较全部输出bytes：

- 36 draw，207个原始顶点，135个三角形/405个索引。
- position、应用一次的UV、RGBA和所有索引逐 byte一致。
- 截断、尾随bytes、非法lighting与错误PRIM四个输入均被实际 executable拒绝。

`runtime_effect_geometry_v1` 保存实际源码副本、输入、独立reference、exe、编译/运行命令、输出和逐draw绑定。它是生产独立 core的实际执行，尚不是正式UE module、最终GPU画面或M1可玩验收。调用者不能重复应用UV scale/offset，后续仍需使用每draw已核对的原变换与材质。

`negative_full_handler_v1` 另有三个合成反例：删掉companion snapshot、篡改原inner record、篡改producer count。均在预期独立检查处拒绝，原采集未改写。

## 仍需恢复

本轮证明的是首 emitter到callback-return的完整 inline PRIM窗口。首 emitter以前的材质准备、任意CALL/JUMP子list、多group实测、FEP节点时间推进、颜色/矩阵/f12随时间更新及新相机下billboard行为均未因此自动恢复。

下一步应沿原节点update/参数构造路径定位local matrix、颜色、UV与f12的实际时间来源，形成可驱动M1的FX生命周期；然后将已核对的marker、几何和材质放入正式运行时作移动射击视觉验收。原弹道/命中、碰撞、伤害、AI与高清美术仍属于未完成的完整目标。工具链取消终态保持，本轮未触发安装或桌面操作。
