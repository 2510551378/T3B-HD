# 武器 source1 的多阶段 output 采样 ABI

范围为新的 `trace_weapon_marker_state_output.js` 和离线 Mock；本代理未连接 PPSSPP、未操作桌面、未改存档或旧采样器。`semanticName=null`。这里说明可观测的数据流与严格检查，尚未把任何 state/resource 命名为枪口、FX 或发射器。

选定模块：`raw/ULJM05798_module_08804000.bin`，guest base `08804000`，SHA256 `b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f`。

## 返回点和完整代码身份

令 H 为 `08b44580` helper 入口 SP，P 为调用 state 的地址，C=H+0x210。

| 阶段 | 唯一活动 BP | 预期 SP | 读取结果 |
|---|---:|---:|---|
| entry | `08b44580` | H | 入口 GPR、stack[0:0x3ac]、三条 source、WORLD、state |
| helper return | `08b3e62c` | H | 原始输出 H+0x40 的64 bytes；更新后的三条 source 与 WORLD |
| generic return | `08b630dc` | C | C 的64-byte副本及 **C[0:0x160]** 同暂停点 context |
| state return | `08b63550` 或 `08b6379c` | H+0x370 | 最终 P+0x60 的64 bytes、完整 P[0:0x1a4] |

每次先 remove 当前断点并收到 ACK，再检查下一个目标的16-byte原码身份，再 add 下一个断点并收到 ACK，最后 resume。不会同时安装两个断点。启动时拒绝任何 enabled CPU BP，以及上述五个地址任一已有 BP（包括 disabled）；不移除或修改别人的 BP。

启动检查以下完整有界函数。每一块同时保存 default/raw read、`memory.read(replacements:false)`、`memory.disasm` 原始 JSON 和重建 opcode；后两条恢复路径都必须逐 word 等于选定模块。仅有 `0x68xxxxxx` emuhack 前缀不构成通过条件。

| 函数入口 | byte 长度 | 已核对的返回/调用锚点 |
|---|---:|---|
| helper `08b44580` | `0x210` | `08b44788:03e00008` jr ra；delay `27bd0150` |
| wrapper `08b3e610` | `0x12c` | `08b3e624:0e2d1160` jal helper；`08b3e734` jr ra；delay `27bd0090` |
| generic `08bbc93c` | `0x43c` | `08bbcd5c..6c` restore s0..s3/ra；`08bbcd70` jr ra；delay `27bd0180` |
| state `08b62e98` | `0x654` | `08b630d4:0e2ef24f` jal generic；`08b634bc..e0` restore；`08b634e4` jr ra；delay `27bd0160` |
| parent `08b634ec` | `0x438` | `08b63548/08b63794:0e2d8ba6` jal state；`08b6391c` jr ra；delay `27bd0040` |
| copy64 `08bfd23c` | `0x44` | 4×4-word复制；`08bfd278` jr ra，delay v0=初始dest |

## entry 身份与 stack 合约

入口 ABI 为 a0=H+0x40 的64-byte输出，a1=drawable，a2=source index。只选择 index=1；drawable 必须通过 metadata boneCount=3、单 packet、243 vertices、stride16、VTYPE=0x522，以及 `SHA256(u32le(VTYPE)||geometry)`：

`168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a`。

handle→drawable 的一层解引用必须实际读取并等于 a1；不依据指针外形命名资源。source record+0x124 是 runtime parent **pointer**，此次按原始 bytes 保存，不当作 metadata parent index。

| 入口位置 | 必须满足 |
|---|---|
| ra | `08b3e62c` |
| H+0x80 / H+0x84 | C / `08bbccd0` |
| H+0x1fc / H+0x200 / H+0x204 | P+0x60 / P / C+0x40 |
| H+0x20c | `08b630dc` |
| H+0x338 | 完整 flags；必须等于 live P+0x154 |
| H+0x33c | P（state 保存的 parent s0） |
| H+0x360 | `08b63550` 或 `08b6379c` |
| H+0x3a8 | `08b639c8`、`08b69aec` 或 `08b69f00` |
| s0/s1/s2 | H+0x1b0 / 1 / primary handle |
| s4/s5 | P+0x10 / P+0x90，交叉核对 stack 的 P |
| s6 | primary handle；handle[0] 必须等于 drawable |
| fp / s7 | `u32(s32(flags)>>16)` / fp&0x40；当前已确认单 helper 分支要求 s7=0 |
| P+0x144 / P+0x148 / signed16(P+0x14c) | primary handle / 0 / 1 |

`08b62ee0:000bf403` 是 **SRA fp,t3,16**，不是 SRL；高位符号扩展保留为 unsigned GPR bit pattern。未把 fp=0 推断为完整 flags=0。

helper return 检查 SP、RA 和 s0..s7/fp 全部保持入口值，并再次核对真枪 geometry/metadata/table。允许 lazy update 更换 sourceBase，但记录 `sourceBaseChangedDuringCall`，并从更新后的真实 base 重新读所有 source。

generic return 检查 SP=C、RA=`08b630dc`，s0..s3 必须等于入口 stack H+0x1fc/200/204/208 保存的四值；s0=P+0x60、s1=P、s2=C+0x40、s4=P+0x10、s5=P+0x90，s6/s7/fp 保持已确认值。C[0:64] 必须逐 byte 等于 helper actualOutput；C+0x128 flags 必须等于入口 flags。C+0x40 basis 与 C+0x128 flags 来自这次 return 的 **genericContext**，不会用 entryStack 代替。

state return 检查动态 PC、SP=H+0x370、RA=stateRA，以及 s0..s7/fp 分别等于 entryStack H+0x33c..0x35c 保存的 parent 值；s0 必须为 P。此时状态函数的所有 VFPU/translation 分支已经执行完成，但 parent 返回点之后的工作尚未执行。

## 原始字段与 sidecar

输出 `marker_state_output.json`，schema=`weapon-marker-state-output-capture/v1`。每个 sidecar 都有绝对 `file`、`bytes`、`sha256`；矩阵附带 `words`、`f32`、column-major layout。只有完整走完三个返回阶段才加入 `rows`；失败中的部分证据保留为 `inFlight`。

- 入口：`H`、`P`/`statePointer`、`sp`、`ra`、`entryGPR`、`entryStack`、`frames`、`savedRA`、`flags`、`stateRA`、`outerRA`、`entryState`、`stateBefore`。
- 原版身份：`actor`、`index`、`metadata`、`drawTable`、`sourceBase`、`geometry`、`geometrySHA256`、`metadataHeader`、`drawHeader`。
- helper 前后：`preSourcesAll`/`postSourcesAll`（各0x390）、`preSource`/`postSource`（index1，各0x130）、`preSource40`/`postSource40`、`preWorld`/`postWorld`、`actualOutput`、`returnTicks`/`returnGPR`、`stateAfterHelper`。旧 output 采样器的这些字段名保留。
- generic：`genericContext`（C,0x160）、`genericOutput`（前64bytes）、`genericReturn={pc,ticks,sp,ra,gpr,helperOutputByteEqual}`、`stateAfterGeneric`。
- 最终状态：`stateAfterReturn`（0x1a4）、`stateFinal`（P+0x60,64）、`stateReturn={pc,ticks,sp,ra,gpr}`。
- `resourceIdentity.{entry,helperReturn,genericReturn,stateReturn}`：`fieldAddress=P+0x198`、`address`、`requestedBytes=64`、`semanticName=null`、`status`；有效时 `bytes` 是64-byte sidecar。null、越界/未对齐、read error 分开标记，不把它们当资源格式已解析。
- `helperOutputBefore`、`wrapperExternalBefore`、`genericOutputBefore` 保留入口原始内容。

`comparison` 仅比较 JS f64 的 WORLD×source40 及反序与 helper 的原始 F32 结果；不在 sampler 预测最终 state，也不要求 `stateFinal==actualOutput`。全部 helper stop 的 ticks（含各返回）与仅 entry 的 ticks 分别计数。入口 BP 未安装期间的其它 helper 调用不会被枚举。

## 离线验证与运行交接

离线命令：

```powershell
node --check work/psp_parse/tools/trace_weapon_marker_state_output.js
node work/psp_parse/tools/trace_weapon_marker_state_output_selftest.js
```

Mock 覆盖两种 state 返回点、32/35/36项 GPR、SRA高位符号扩展、三阶段独立 timeout/SP/RA/saved-register错误、未知链/P/flags、generic copy/flags不等、每阶段 read error/外部暂停、断点冲突、两条原码恢复路径错误、resource三种阴性状态、add ACK timeout清理。成功路径故意让 final state 与 helper 不同，并在 generic pause 更新 C+0x40，防止错误使用 entry snapshot。

实际运行只能由 parent 的既有安全 runner 发起；本代理未运行下列采样命令。对新目录设置 `MARKER_STATE_OUT_DIR`，例如 `.../out/AYA_BONE_GE_ACTIONS/slot0_weapon_marker_state_square6`；建议 `MARKER_MAX_ROWS=6`、`MARKER_MAX_STOPS=1200`、`MARKER_DURATION_MS=15000`、`MARKER_STAGE_TIMEOUT_MS=3000`、`MARKER_BUTTONS_JSON={"square":true}`。其余 `PPSSPP_DEBUGGER_PORT`/`MARKER_ANALOG_JSON` 继承旧采样器接口。禁止复用已有 marker_state_output.json。

```powershell
node work/psp_parse/tools/trace_weapon_marker_state_output.js
```

RPC pending 与 stepping waiter 都在发送前注册，未 ACK 的 BP add 也记录为 owned，以便失败清理。queue 记录 `ownedBreakpointAtReceipt`；即使初始 add ACK 超时，已排队的自身 stop 仍会在 finally 恢复，已排队的 external stop 保持暂停。finally 显式 release 全部指定按键及 analog，移除自有 BP，只 resume 已确认属于自身的暂停。失败不会改写任何已有捕获、存档、旧采样器或正式 runtime manifest。

清理补丁后的脚本在连接前保存 `producer={file,sha256}`，对自身文件只读一次，写入整个 capture report。该补丁阶段脚本 SHA256 为 `2992259d135c3abfcf0af98296a3156623647b00dee62e04a2c3b5a73157e5cd`，50 个离线 Mock 全通过；后续 FEP opt-in 版本见下节。

## Parent 实际采样后的证据边界

Parent 用补丁前 producer `f93d4d0929cc33ad949a1d781923febfa71b80ca49cf53e659b6dd3b1e956a17` 完成 square6、aimfire24、strafefire24，共54组完整返回；代码冻结为 `out/WEAPON_MARKER_STATE_20261020/trace_weapon_marker_state_output_sampled.js`，身份记录在同目录 `producer_identity.json`。这些 capture 不能归因于后来加入 producer 字段和排队超时清理补丁的新版脚本。

三组 report 的 failure 均为 null、cleanup.errors 均为空；parent 的独立 `square6_audit.json`、`aimfire24_audit.json`、`strafefire24_audit.json` 均 passed。54组均 flags=0、stateRA=`08b63550`、outerRA=`08b69f00`，helper→generic→final 在该分支逐 byte 相同。此结果不覆盖 flags 非零或另一个 stateRA 分支。

四阶段 resource pointer 均为 `08d51b70`，64-byte SHA256 `04afeecb38df20d41a7c24da1686e31cf70a8e631aa51e48321c776ab21d89b6`。选定模块 image 结束于 `08cb3000`，该运行时地址位于其后，不能称为该 EBOOT image 内的静态 data。ISO 唯一字节匹配及其加载关系由独立资源调查记录；这里仍只记录 runtime identity，`semanticName=null`。

## 固定来源 FEP opt-in probe

新增 `MARKER_FEP_PROBE=1`，默认关闭，关闭时不增加 FEP guest read。只有首条真枪 source1 已通过完整 entry caller/stack/state ABI 后才执行；同一 capture 的后续 row 不重复读取。修正 +8 relocation 后的当前 producer SHA256：`f9a7326312d4b96fd24a4238b66dfa77cbe5f66464fce885b35aaf48a61d94d4`；`node --check` 和 **58 个离线 Mock** 全通过，包括 relative/relocated 表指针、错误 +8 pointer、两条 row 只读一次、坏 base/header、read error、state 三字段不符。

此功能只针对 parent 已发现的 ISO section `0x56bf7bc0`、size `0xbe240`、record relative `0x48f0`，不能视为通用 FEP parser。base 直接读取首条 row 的 entryState+0x190；不从 resource 地址减常量得到。还要求 state+0x194=base+0xfb4、state+0x198=base+0x48f0，base 和每个窗口均须通过 guest RAM 范围/对齐检查。

| window name | base-relative offset | bytes |
|---|---:|---:|
| `header_tables` | 0 | `0x400` |
| `type0_descriptor4` | `0xab8` | 12 |
| `pointer_list` | `0x48e0` | 16 |
| `table1_record4` | `0xfb4` | 64 |
| `record` | `0x48f0` | `0xc0` |

先读取真实 header 窗口并保留 raw sidecar，检查 FEP07、version `0x00090001`、section length `0xbe240`、前两表 count=93。**+8 是 offset/pointer，撤回此前“header length”命名**：`offset8Pointer` 允许 `0x48` 或 base+0x48。header+0x28/+0x2c 表指针允许原版 relative `0x50/0x1c4` 或实际 base+对应 offset，两者保留原始 word 交给独立 auditor 判断 relocation。任何 header 检查失败都不再读取后四窗。其它 read 失败也保存已取得的诊断并 fail closed，完整 capture 的 failure 不会伪装成功。

Parent 的首次 `slot0_weapon_marker_state_fep6` 使用 producer `67026c80e410853715316515389ce2bac7d96648ec92eaa494bee001fcab7292`，只保存 header 窗口后 fail closed、rows=0、cleanup 全通过。唯一 gate 失败为旧 `headerBytes` 检查：原文件 +8=0x48，live +8=`08d4d2c8`=base+0x48。其它 magic/version/size/counts 和 +28/+2c gates 均通过。实测 +0xc 从原0变为 `01ff0000`，作为未知 runtime 状态保留，未据此命名格式；+0x30..0x44/+0x4c 的 relocation 由 parent 独立审计。修正只改变 +8 的命名与两种精确合法值，未扩大读取范围或放松其它 gates。

top-level `fepProbe` 保存 `enabled`、`attempted`、`status`（disabled/not_attempted/reading/captured/failed）、`sample`、`sourceState190/194/198`、`headerChecks`、`windows`、`failure`、`scope`、`isoEvidence`、`semanticName=null`。每个 window 保存 `name/offset/address/size/status` 及 `raw={file,bytes,sha256}`；失败的 window 附带 error。`captured` 仅表示有界读取和结构 gate 完成，不能等同 loaded-resource 身份或 FX 语义已确认。

父代理的既有安全 runner 只需在新输出目录添加该 opt-in；本代理未执行 PPSSPP 或 UI。probe 不修改 source、state、原 ISO、存档或正式 runtime manifest。

这些检查证明的是 ABI 与保存机制；只有实际 capture 加独立 auditor 才能证明这条运行时数据流。即使最终 state 公式得到验证，也仍需要更下游 consumer 的证据才能给出具体 FX/socket 名称。
