# 原版 source1 → 最终 state 与 FEP 来源记录

新增实时来源核验见 [WEAPON_MARKER_LIVE_FEP_20261020.md](WEAPON_MARKER_LIVE_FEP_20261020.md)：state190基址与所选指针链已在5个窗口实测，record完整192bytes同ISO。下文候选基址描述保留为此前阶段；完整runtime section与consumer语义仍未确认。

## 实际三阶段观测

新采样器 `tools/trace_weapon_marker_state_output.js` 交替使用一个自有CPU breakpoint，取得 helper返回、generic返回、state函数返回三个暂停点。原型、完整函数机器码、原枪几何、SP/RA/callee-saved registers和原始binary snapshots均保留。未使用桌面输入，没有写即时存档。

| Capture（`out/AYA_BONE_GE_ACTIONS/`） | 输入 | Entry stops | 完整三返回配对 |
|---|---|---:|---:|
| `slot0_weapon_marker_state_square6` | square | 284 | 6 |
| `slot0_weapon_marker_state_aimfire24` | R+square | 662 | 24 |
| `slot0_weapon_marker_state_strafefire24` | R+square、left-stick x=0.7 | 682 | 24 |

54组均为真实函数调用配对，不是54个完整GE帧。全部 `stateRA=08b63550`、`outerRA=08b69f00`、完整flags=0。链为 `08b44580 → 08b3e62c → 08b630dc → 08b63550`；更上层saved RA确认经过 `08b69dbc` 的调用路径，而非只从静态三个候选猜测。

在全部54组中，helper原output64bytes、generic C64bytes和最终 `P+0x60` 64bytes逐字节相同。`tools/analyze_weapon_marker_state_output.py` 独立核对完整模块固定SHA、六个完整函数范围、每个返回点的原码双恢复、stack中的H/P/两层saved RA、原始geometry、四阶段state与data snapshots、单活动BP历史。报告：`out/WEAPON_MARKER_STATE_20261020/{square6,aimfire24,strafefire24}_audit.json`。

实际采样producer为SHA `f93d4d0929cc33ad949a1d781923febfa71b80ca49cf53e659b6dd3b1e956a17`，已冻结为该目录 `trace_weapon_marker_state_output_sampled.js`。后续脚本增加了queued-stop清理和producer字段，不能用后续源码hash冒充旧capture的实际producer。

## state组合公式的边界

`08b632cc..08b63494` 的VFPU指令结合官方PPSSPP v1.20.4 [Int_Vmmul / Int_Vtfm](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/MIPS/MIPSIntVFPU.cpp) 与 [ReadMatrix / ReadVector布局](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/MIPS/MIPSVFPUUtils.cpp) 进行独立解码。所用官方源文件及SHA保存在 `raw/ppsspp_v1.20.4_vfpu_reference/sources.json`，未将其代码并入游戏runtime。

对没有high-basis分支与外部Y调整的低位路径，令 M=marker、A=C+0x40 actor basis、L=组合前state+0x60，R与t分别表示basis和translation：

- 输出basis为 `(flags&0x20 ? A.R : M.R) × L.R`。
- 输出translation采用 `(flags&0x40 ? A.R : M.R)` 变换局部位置，再加 `M.t + state[0x50].xyz`。
- 两个低位都clear时，局部位置直接读 **state+0x10**；其它组合读L.translation。不能把两者相等当作任意state都满足的假设。
- 指令明确把homogeneous w设成1。`flags&0x200000` 或 `flags&0x10` 的额外路径未在此公式中代替实现。

本轮实际只覆盖flags=0、局部位置/offset为零、L为identity的路径，因此最终state恰好等于marker。F64公式与54个实际输出也完全相同，但不能据此声称其它flags或VFPU一般舍入已逐bit复现。针对非交换basis/非零translation的手工fixture只验证公式实现，不替代原游戏分支实测。

另由独立 `tools/verify_weapon_state_vfpu.py` 从原始opcode逐条回放实际分支，处理branch delay、F32逐乘逐加、VFPU寄存器/transpose及w分量；它不调用上述F64公式或synthetic fixture。54/54组的生成结果与实际stateFinal **0 component bit difference / max_abs=0**。报告 `out/WEAPON_MARKER_STATE_20261020/vfpu_replay_verification.json` 保存每条指令trace、模块/官方参考文件SHA和复现argv。此处逐bit结论仅针对已观察的flags=0路径。

## 从运行时data到原ISO的唯一匹配

54组四阶段的 `state+0x198` 都为 `08d51b70`，64bytes不变，SHA `04afeecb38df20d41a7c24da1686e31cf70a8e631aa51e48321c776ab21d89b6`。它在所选module image范围之外，不能叫EBOOT静态数据。

`tools/match_weapon_state_data_iso.py` 完整扫描原ISO，并用ISO实际pack目录逐项核对CSV索引的绝对偏移，发现此64byte序列只有一处匹配：

| 字段 | 已确认的离线值 |
|---|---|
| ISO位置 | `0x56bfc4b0` |
| type12 pack | `0x56bf7000` |
| section slot / ISO起点 | 1 / `0x56bf7bc0` |
| section magic / 长度 | `FEP\x07` / 778816 bytes |
| 记录在section内的偏移 | `0x48f0` |
| 完整section SHA | `97443c71b1c1d644f323c6ff611afb740329cfe11a47a711f39dc59de06ec802` |

原区段已只读提取为 `out/WEAPON_MARKER_STATE_20261020/original_source_match_section.bin`，报告 `original_source_match.json`。由偏移推算的runtime FEP base为 **08d4d280候选**，尚未live读取完整header/区段指纹，不能仅凭唯一64bytes就将其标为已确认基址或资产身份。

后续需要验证live FEP header与更多原始结构bytes，沿其pointer tables和state初始化路径建立对象关系，再定位实际渲染/FX消费。该记录也可能是transform descriptor而非资产根；`semanticName`继续为null。生产M1枪口、武器timeline未因这次观测自动替换。

补充结构交叉核对：现有entryState还实际保存 `+0x190=08d4d280`、`+0x194=08d4e234`、`+0x198=08d51b70`。离线FEP的table0[4]指向descriptor+0xab8，其+8指向list+0x48e0，list首项为record+0x48f0；descriptor的low16 index为4，table1[4]恰为+0xfb4。这与三项runtime指针对齐。静态初始化 `08b63f34/38/3c` 分别写入这三字段；但loaded header和实际relocation仍需直接读取，不能用相同的候选base反复相减代替新证据。

## 保护与下一步

三个capture均failure=null，按钮释放、自有BP移除及暂停恢复成功；移动capture额外归零analog，runner恢复原INI bytes。完整原ISO、slot0与INI的采集前后SHA核对另存保护报告。

同时完成的Aya native骨骼可行性分析见 `out/AYA_LOCAL_SRT_FEASIBILITY_20261020.md`。实际local SRT、global affine与GE float24 skin矩阵必须区分；不能把GE矩阵的量化shear误当原local骨骼无法迁移。UE实际编译、骨骼导入、画面和战斗验收仍未完成。
