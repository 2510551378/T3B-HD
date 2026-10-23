# 原版武器 source1：真实返回矩阵与连续输入复核

## 本轮实际确认的范围

PPSSPP v1.20.4 从 slot0 的只读备份启动。CPU helper `0x08b44580` 与 wrapper `0x08b3e610` 的完整机器码分别通过原码 memory.read 与 disassembly 双重核对。只有精确匹配原步枪 243 vertices / VTYPE 0x522 / 完整 geometry SHA 的 source1 调用被保留。

在入口保存原 a0 output 指针，然后切换单个自有 breakpoint 到 `0x08b3e62c`。返回暂停点检查 SP、RA、s0/s1/s2，读取真实64bytes output与更新后的 source+0x40、WORLD，而不是用预测矩阵代替原输出。

| Capture（`out/AYA_BONE_GE_ACTIONS/`） | 输入 | Entry stops / paired outputs | 保留查询跨度 | WORLD × source40 最大绝对差 |
|---|---|---:|---:|---:|
| `slot0_weapon_marker_output_square6_v2` | square | 284 / 6 | 0.167117039 s | 0.000156372240 |
| `slot0_weapon_marker_output_aimfire24` | R + square | 662 / 24 | 0.767590348 s | 0.000236245628 |
| `slot0_weapon_marker_output_strafefire24` | R + square + left-stick x=0.7 | 662 / 24 | 0.767511141 s | 0.000238019024 |

这里的54组是实际helper调用配对，不能当作54个完整GE帧。等待return期间没有entry BP，entry stops也不是整段游戏的所有helper调用数。时间按原ticks与333MHz计算，不用宿主耗时替代。

## 独立复核与数值解释

`tools/analyze_weapon_marker_output.py` 重新读取所有原始sidecars，核对固定ULJM05798模块SHA、两条恢复路径的完整机器码、disassembly word覆盖、几何bytes、source切片、F32 words与JSON值、单断点切换、入口/返回GPR与调用栈。它从原始F32输入独立做F64矩阵乘法，不采用采样器预先保存的predicted矩阵作为真值。

三份报告位于 `out/WEAPON_MARKER_OUTPUT_20261020/{square6,aimfire24,strafefire24}_audit.json`。54组全部通过上述证据一致性检查，返回链均为 `08b3e62c → 08bbccd0 → 08b630dc`，每次helper耗667 guest ticks。

数值支持 column-major `WORLD × source40`。反序 `source40 × WORLD` 的max-absolute error，在三次capture中最小仍分别为5894.04539、5851.34438、5817.84892。正确顺序的约2.4e-4差主要出现在数千原始单位的平移分量；这是原F32结果与F64参考的差，不等于零bit差异，也未宣称VFPU逐指令舍入已复现。

三组source1 local record在每次helper入口和返回间都未变化，WORLD也未变化；这批样本没有证明lazy update实际刷新了矩阵。保留post快照仍是正确的读取契约。移动输入下，实际output origin的各轴范围约为26.4233、6.7700、39.4081原始单位，+Z方向相对首条最多变化19.8113°，因此不是仅验证一张静态姿势。

审计器另用临时报告验证了4种坏证据被拒绝：错误return SP、错误原output指针、与raw bytes不符的JSON matrix words、擅自命名muzzle。原capture未被改写。

## 首次失败与修复

`slot0_weapon_marker_output_square6` 在0保留行时因严格要求32个category值而停止。真实PPSSPP GPR category有35项，新采样器改为验证并使用前32个GPR，保留category长度/名称诊断。额外项不会被当作GPR。35/36项格式及非法GPR反例已加到离线Mock；失败capture保留，不覆盖成成功。

三份成功capture的failure均null，按钮释放、自有BP移除、自有暂停恢复全部成功；移动capture还明确归零analog。runner只停止自己启动的模拟器并原字节恢复INI，没有写即时存档。slot0 SHA仍为 `32f7fe3d3d830079d7b4499066eb488562e33ce945765eea8461fc1fca18dc39`，INI SHA仍为 `d75494e1285bcd45d736260728870e5aa4902151c6c3300d9f0c3384c93bca34`。

## 对 M1 的意义及剩余工作

现在已经取得原版开火相关source1 transform的实际输出，组合顺序与连续输入下的变化也有实测支持。`semanticName` 继续为null：本轮没有追到具体FX资源或弹道生成consumer，不能直接称其为已确认枪口。

M1现有射线起点仍是原枪mesh的几何枪管端点估计。未确认用途之前不替换正式武器/枪口绑定。

## 补充：同暂停点全3 source与M1几何端点测量

第四次capture `slot0_weapon_marker_output_strafefire_dense24` 为 R+square、left-stick x=0.7，722次entry stops、24次return、24组有效配对，failure=null，按钮/analog/BP清理成功。连同上表共78组实际返回值，仍不是78个完整GE帧。新增 `preSourcesAll/postSourcesAll` 各912bytes，一次读取全3条records；source1字段由同一snapshot切片，避免跨读取时刻混用。

独立 `strafefire_dense24_audit.json` 通过，WORLD×source40最大绝对差0.000202978923。`tools/measure_weapon_marker_geometry.py` 则读取M1源代码中真实 `SOURCE_WEAPON_TIP` 常量与负X方向构造，以及当前weapon clip的units；从同暂停点source0与WORLD重算几何端点，和实际helper output比较。

关键格式：source+0x124是guest parent pointer，3骨为 `[null, sourceBase, sourceBase]`；source0+0xC0是12个 `0x2Bxxxxxx` GE BONE command words，payload为IEEE F32的高24位，按column-major3×4恢复。它不是16-F32矩阵。所有24行还确认root+0x40为identity，GE payload与source0+0x80矩阵选定12项的高24位逐字一致。source1+0x40/helper output仍是完整16-F32，两种格式不能混读。

测量结果 `strafefire_dense24_geometry.json`：24组中，M1几何端点估计与原版source1 output origin最大相距 **0.3437013 cm**，方向相对output +Z最大差 **0.000002259°**。这说明当前真实枪mesh的几何枪管方向与这个开火相关marker高度一致；0.344cm的位置差仍保留，没有拟合常量使其归零。

这里比较的是同一原始world空间的解析等价公式，没有实际执行M1的Aya-relative baked矩阵、时间插值、任意玩家yaw、渲染或交互。因此它不能替代M1实际跟手/画面验收，也不能单独命名marker。没有替换生产射线起点或timeline。

首次校准曾错误把+C0指令字当16-F32，产生无效几何结果；已改用上述GE解码并严格交叉核对，原错误报告单独保留为 `strafefire_dense24_geometry_invalid_f32_interpretation.json`，`passed=false`，不计入任何校准结论。

下一步是沿已知caller链观测最终state+0x60，而非再用空间接近推断语义。`WEAPON_MARKER_STATE_CONSUMER_ABI_20261020.md` 已静态确认wrapper/generic两层复制和最终state的组合分支：当前0x240 stack只够浅层，需扩到H+0x3ac取得完整flags及两个saved RA，再交替单BP验证 `08b630dc` 与动态state返回PC。具体FX资源/后续consumer仍未观察。

采样器ABI、边界和运行变量见 `WEAPON_MARKER_OUTPUT_ABI_20261020.md`。所有结论只覆盖当前slot0、当前原步枪及这些有限输入窗口，不代表其它武器、全部动作或完整游戏已恢复。
