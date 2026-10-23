# 原版武器关联 render → CPU GE 命令观测 ABI

本轮独立新增 `tools/trace_weapon_marker_ge_emit.js` 与 `_selftest.js`。旧 producer、冻结 capture、auditor、UE 与 checkpoint 均不修改。本代理只读取原模块和 retained captures，运行 VM/Mock；没有连接 PPSSPP、运行游戏或使用 UI。以下 runtime 字段契约仍待 root 独立启动和审核。

## 证据与成功条件

固定原 module SHA256：`b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f`，base `08804000`。固定 FEP section SHA256：`97443c71b1c1d644f323c6ff611afb740329cfe11a47a711f39dc59de06ec802`。

输入 retained alt6：`out/AYA_BONE_GE_ACTIONS/slot0_weapon_render_alt_fire6/marker_render_dispatch.json`，SHA256 `682fc0876b6739cb1c3e23f244ac98a602ff9205f154457800ece728c1621606`。逐 row 参数、原函数边界与 SHA 在 `out/WEAPON_GE_EMIT_STATIC_20261020/actual_alt6_branch_analysis.json`（SHA256 `ba3ced5eb6c3b0a5b2c7649951850c8fa3f09c2c2477d2968358ba82b6d1dba3`），旁有完整原函数 raw 与反汇编。

已观测：alt6 完成 6 次原 handler invocation/return；四个 D 为 FEP-relative `10ba0/10be8/10c30/10c78`。四行 type152 的 data+4 u16=0、data+6=0、parameter+1d=1、+1f=1；两行 type155 的 parameter+48=0、+4b=1。六行 N+1c=0、N+50 有效，N+54=0。

静态推断：这些字段选择下面两条路径；尚不是本轮实际 helper/CPU 命令观测。

| type | matrix helper / return | VIEW wrapper | geometry helper / entry RA | PRIM chain / emitter return |
| --- | --- | --- | --- | --- |
| 152 | `66bb4 / 982b4` | `bbb8d4 → fff6c → c01088(kind1)` | `6270c / 98410` | `5ddb0 → 5d258 → bba1fc → fff98 / bba214` |
| 155 | `66bb4 / 9a76c` | 同上 | `6050c / 9acc0` | `5ecac → 5e368 → fff98 / 5e3b0` |

表内使用 PC 的末尾 5 或 6 位简写；完整地址见下面 schedule 与原函数 raw sidecar。例如 `bbb8d4` 为 `08bbb8d4`、`c01088` 为 `08c01088`。这些 PRIM 是关联资源的 emitted geometry，不是用来筛选 state 的原枪 243-vertex mesh。source1、state、resource 仍无最终 muzzle/FX 语义名。

成功必须同一选中 invocation 走完九阶段：原枪 identity、原 FEP192、当前 D/render list/registry、matrix caller/return、VIEW 实际 CPU packet、geometry caller、PRIM writer caller/return、最终 callback return 全部通过。仅保存第一份符合限定 caller 的 PRIM。`geDrawObserved=false`、`semanticName=null` 始终保留；CPU 写入 display list 不代表 GE 执行或最终画面。

## 单 BP schedule 与代码身份

```text
ENTRY 08b69b58
→ DISPATCH 08b69d64
→ MATRIX_ENTRY 08b66bb4
→ MATRIX_RETURN 08b982b4 (152) / 08b9a76c (155)
→ VIEW_ENTRY 08c01088
→ GEOMETRY_ENTRY 08b6270c (152) / 08b6050c (155)
→ EMIT_ENTRY 08bfff98
→ EMIT_RETURN 08bba214 (152) / 08b5e3b0 (155)
→ CALLBACK_RETURN 08b69d6c
```

每次删除自有旧 BP 后才装新 BP；所有已知阶段地址上的既有 disabled BP 也拒绝；任何 enabled 用户 BP 均拒绝且不修改。代码必须同时经 `memory.read(replacements=false)` 和 `memory.disasm` opcode/macro 完整恢复与原 module 一致，不能仅接受 68xxxxxx EMUHACK。raw/expected/original/decoded/disasm 都保留。

启动完整检查：`69b58/258`、`bbd828/3c`、`66bb4/3b4`、`c01088/268`、`fff98/d0`、`bbb8d4/5c`、`fff6c/2c`、`c01e9c/58`。DISPATCH 再核实际 registry target：`9809c/3f0` 或 `9a514/808`。对应 geometry 全函数另核：152 为 `6270c/4c`、`5ddb0/30`、`5d258/350`、`bba1fc/24`；155 为 `6050c/68`、`5ecac/1d4`、`5e368/74`。每次阶段转换再检查目的 PC 的 8 bytes。

## 固定身份与 dynamic resource ID

ENTRY/dispatch/callback-return 继承 alt producer 完整身份：真枪 single draw、243 vertices、VTYPE522、three source bones、完整 geometry SHA256 `168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a`；P+198 prefix64 SHA256 `04afeecb38df20d41a7c24da1686e31cf70a8e631aa51e48321c776ab21d89b6`，完整 FEP record192 与原 section+48f0 相等。实际 D/list/definitions 必须是绝对 base+offset；header 原有 offset-or-relocated 兼容契约保持。

原 geometry resource ID 不等于 parameter+0c index。新 `geometrySource` 保存：header50，sourceTableField=38(152)/34(155)，index=parameter+0c，table=base+原 table offset，slot4→source record18（地址必须 base+原 slot offset），record+10 的有符号 runtimeId。只允许 index0..31、runtimeId0..4095，−1 明确失败。再存 C/a8 → C+a0/a4 container/24 → container[0] table+4*runtimeId slot4 → geometry object/20。原 FEP 的 record+10 为 FFFFFFFF，不据原 image 猜 runtimeID。

## 逐阶段 ABI 与 raw windows

令 Q=ENTRY.sp，S=Q−30；H=S−d0(type152) 或 S−110(type155)。所有数字无 `0x` 时也为十六进制，vertices/count/mode 值在 JSON 以整数保存。

ENTRY/DISPATCH/returned 字段完全保留 base schema。ENTRY a0=C/a1=P/a2=N/a3=1，RA=08bbd858。DISPATCH SP=S，s0=C/s1=N/s2=1/s3=D/s4=0，C94=B。JALR delay slot把 t0 复制到 a2，不能把 pre-delay a2(method descriptor) 当 parameter。

| 新字段 | GPR/返回要求 | 原始窗口 |
| --- | --- | --- |
| `matrix.entry` | PC66bb4, SP=H, RA982b4/9a76c, a0=C,a1=N,a2=N50,a3=mode,t0=H+10 | C/a8,N/64,P/1ac,H/d0或110；input64、P+6064、outputBefore64；modeSource indices4→N48 selected slot4→component4 |
| `matrix.returned` | SP=H, RA同；s0..s7/fp 与 entry 相同 | `(H+10)/64` actual output |
| `view.entry` | PCc01088, SP=H−60, RAfff8c, a0=dlContext,a1=1,a2=H−50 | stack60，input64，handlerMatrix=(H+10)/64，globalSlot08c3b588/4→globalMatrix64，cursor处before packet34 |
| `geometryHelper.entry` | SP=H, RA98410/9acc0；152(a0=C,a1=runtimeId,a2=0,a3=H)，155(a0=container,a1=runtimeId,a2=H) | C/a8，H/10 auxiliaryVector；DL context；已写 VIEW34，完整 VIEW→geometry 命令段(34..1000) |
| `emit.entry` | PCfff98, SP=H−70(152)/H−80(155)，RAbba214/5e3b0 | stack1a0，实际 vertices(count*stride)、155 s3 drawRecord10，DL context/before packet |
| `emit.returned` | 同 emit.entry SP/RA；s0..s7/fp 相同 | DL context、从原 emit cursor 开始的 actual packet |

matrix.entry 复核当前 C8c=P/C90=N/C94=B、N1c=0、a2=N50、mode=实际 B8 list[1]→N48 slot→component byte1。只将未初始化 `outputBefore` 当 raw；不要求其 floats finite。输入/实际 output/P60 等有效矩阵必须 finite。

matrix handler stack核 dispatcher saved registers：152 H+b4/b8/bc/c0/c4/c8 保存 s0..s5、H+cc=69d6c；155 H+e0/e4/e8/ec/f0/f4/f8/fc/100 保存 s0..s7/fp、H+104=69d6c。view stack[0]=bbb924，[50]=982bc(152)/9a840(155)。type155 可能在 matrix return 后对 H+10 做 pivot 调整；因此另读 view.entry.handlerMatrix，不要求它等于先前 helper output。

emit stack 链：152 offset0 为5d53c或5d558、44=5ddd4、50=6274c、60=98410；155 offset10=5ee08、50=60558、70=9acc0。再核 emitStack[emitDelta+callbackRAOffset]=69d6c。155 s3 指向 raw16 的 primitive/count/vertices，与 a0/a2/t0 一致；s1=VTYPE。

## CPU packet 的精确布局

每次 DL snapshot 为 `{address,cursor,global,context}`：global 在 `08ca31d8` 的4 bytes，address=该指针，context=该指针的20 bytes，cursor=原字 context+8。所有读必须 guest RAM `[08000000,0c000000)`、4-byte aligned；单次最多20000 bytes。

VIEW kind1 的 52 bytes：首 word `3c000000`；随后12个 word 为 `3d000000 | (u32(inputFloat) >>> 8)`，input offsets 按 float index `0,1,2,4,5,6,8,9,10,12,13,14`。新采样器在 geometry entry 读取原 cursor 开始实际 packet 逐 word 比较，且 current cursor−view cursor ∈[34,1000]、4-aligned、同 DL context。`3c/3d` 是 GE VIEW，不是 WORLD。

PRIM writer ENTRY：a0∈[0,7] primitive，a1≤ffffff VTYPE，a2∈[1,4096] count，a3=0 indexed pointer（本轮只支持 non-indexed），t0 有效 vertices。严格计算 PSP vertex stride；拒绝 indexed/morphed/no-position/非法 field type，vertices总长≤20000。保留实际原字，不把该资源 vertices 当 weapon original mesh。

expected packet 按原 fff98 逐 branch：

```text
若 a1 != 0: 12000000 | (a1 & 00ffffff)
若 a3 != 0: 10000000 | (((a3>>>24)&15)<<16), 02000000 | (a3&00ffffff)
若 t0 != 0: 10000000 | (((t0>>>24)&15)<<16), 01000000 | (t0&00ffffff)
04000000 | ((a0&7)<<16) | a2
```

a3!=0 的公式只记录原码，本轮 gate 拒绝该分支。return cursor 必须精确增加 expected packet bytes，并逐 word 相等。c01e9c stall-update 函数原码同时核验；不将 stall update 或 packet bytes 解释成 GE execution。

P60 的数学传递仍需独立审核原 VFPU/mode 方程。66bb4 在 N1c=0 时静态取 C8c+60 作为上级矩阵，实际 mode 和所有关键矩阵 raw 已保存；本 producer 不用无来源的乘法顺序预测强迫实际矩阵相等。

## JSON、运行接口与失败边界

输出 `marker_ge_emit.json`；schema 保留 `weapon-marker-render-dispatch-capture/v1`，新增 `probe=cpu-ge-emit-v1`。row 保留 `classification=observed_handler_invocation_return`，增加 `cpuEmissionClassification=observed_geometry_cpu_commands`、`cpuCommandWriteObserved=true`、`emitCoverage=first_matching_cpu_prim_per_handler`。顶层增加 `stageStopCounts`；stage keys 为 entry/dispatch/matrix_entry/matrix_return/view_entry/geometry_entry/emit_entry/emit_return/callback_return。原 `entryStopCount/dispatchStopCount/returnStopCount` 仍只计原三个阶段；first/lastStopTicks 计所有实际 owned stops。

统一 window `{address,size,raw:{file,bytes,sha256}}`；CPU GPR 保存前32个有效无符号值，另存 category名称/实际长度（允许35/36的 PC/HI/LO附项）。`inFlight` 中立即落盘已完成阶段与 partial raw；任何未知caller、代码差、指针/矩阵/packet差、超时均失败且不产生完成 row。0 eligible 只算 bounded negative。

root 可通过既有安全 runner 启动新路径，不需要本代理连接：

```powershell
$env:MARKER_GE_EMIT_OUT_DIR = '<new independent capture directory>'
$env:MARKER_MAX_ROWS = '6'
$env:MARKER_MAX_STOPS = '1200'
$env:MARKER_DURATION_MS = '30000'
$env:MARKER_STAGE_TIMEOUT_MS = '3000'
$env:MARKER_BUTTONS_JSON = '{"square":true}'
node work/psp_parse/tools/trace_weapon_marker_ge_emit.js
```

`PPSSPP_DEBUGGER_PORT` 默认9900；无 input env 时只发送显式 release。可用 MARKER_ANALOG_JSON，但不更改存档/源码/寄存器。输出已存在时拒绝覆写。producer self SHA 在模块加载时冻结。

finally 始终 release input/analog，移除自有 BP。未 ACK 的 add 也按已尝试 owned BP 清理；队列事件保留。queued/external pause 不 resume，只恢复自己确定拥有的暂停；timeout/inFlight 保持 outcome unknown，不能伪造完成。

## v1 离线冻结结果（历史 producer）

150 个 VM/Mock 场景全部通过；`node --check` producer/selftest 均通过。原 alt suite 的81项边界保留，新增69项 matrix/VIEW/geometry/CPU-PRIM、typed155及中间阶段 ACK/timeout 反例。日志 `out/WEAPON_GE_EMIT_STATIC_20261020/selftest.log`，独立标识 `offline_verification.json`。

Producer SHA256：`ce1e08cf4e34a08906384518519835ff0d3a6ad3ba3358a9ee0d56106f75d2cb`（45705 bytes）。只读冻结副本为 `out/WEAPON_GE_EMIT_STATIC_20261020/trace_weapon_marker_ge_emit_offline_validated.js`，与 source 逐字相同，副本仅作证据、不从该目录启动。九阶段真实 PPSSPP 采集与 root 独立 audit 仍为待办。

## v2 窄修：实际 byte component 对齐与 mode1 原输入

root 的首次真实九阶段尝试 `slot0_weapon_ge_emit_fire6_20261020` 已实际到达 MATRIX_ENTRY，未完成九阶段。rows=0，mode=1，失败原因为 word-only read 拒绝 `08d5e27a/4`；finally 清理成功。capture producer 是上述历史 ce1e08cf 版本，本轮不覆盖其 capture 或冻结文件。

原 retained raw `matrix_component_indices_0000.bin` 为 `03000600`（component index6），`matrix_component_slot_0000.bin` 为 `7ae2d508`，实际 componentPointer=08d5e27a。原 handler 指令 `lbu a3,1(a2)` 读取 byte 08d5e27b；它不要求组件基址4-aligned。旧工具错误地对组件基址调用 read4。

修复保持所有 read 的4-byte对齐/RAM/长度 gate 不变，仅此字段做地址分离。先保存 modeSource.indices/index/slot/componentPointer/fieldAddress=componentPointer+1；要求 componentPointer>=08000000 且 fieldAddress<0c000000。再保存 `component`=window(fieldAddress&~3,4) 与 `byteOffset=fieldAddress-component.address`；实际 mode 必须等于 component raw[byteOffset]。允许组件 +1 字段跨 word（例如 pointer%4=3），也允许最后合法 byte；原 pointer/RAM外或 +1 越界仍拒绝。若读失败，指针及 raw slot 在 inFlight 中先落盘。

schema/probe 名称兼容不变；新增 componentPointer/fieldAddress/byteOffset。旧 aligned-case 的 component window 地址与历史一样；auditor 应按 byteOffset 解取 mode，不能固定 raw[1]，也不能将 component.address 误当原 byte-struct pointer。

matrix.entry 另增加：

- `allRegisters.raw`：当次 `cpu.getAllRegs` 完整 JSON 响应，不删 categories、uintValues、额外 FPR/VFPU/control 项；GPR 字段仍只接受前32个有效 u32。
- `allRegisters.f12Decoded=false,f12Value=null`：producer不解码/虚构 f12。仅 GPR 的 Mock/旧 API 响应明确 `f12Availability=unavailable_gpr_only`；有其他 category 时为 `raw_categories_uninterpreted`，由独立 auditor 按真实 API 审核。
- `globalSlot`：08c3b58c/4；`globalMatrix`：其实际指针/64，严格 aligned/RAM/finite gate。不同于 view.entry 的 08c3b588 slot。
- 启动完整代码双恢复新增 `08b6589c/104`（原 mode1 helper），只添加该已确认函数；不扩大 mode2..6。P+30 已在 matrix.entry.state 的完整1ac窗口内，无需额外读。

这组新增只保留现有 API 响应和原输入窗口，不写寄存器、不额外调用 VFPU API，不把未知 prefix 初态当已知。修复后真实完整九阶段仍须重采，旧失败数据不能补成成功 row。

### v2 冻结交接

162 个 VM/Mock 与 producer/selftest syntax 检查通过。Producer 46880 bytes，SHA256 `a12b06d0db3c61baccb7e147ca91c83b682f4761bbf7b7537f8706202ebb04e5`。新冻结名 `out/WEAPON_GE_EMIT_STATIC_20261020/trace_weapon_marker_ge_emit_component_v2_offline_validated.js`；验证清单 `offline_verification_component_v2.json`、日志 `selftest_component_v2_final.log`。旧 ce1e08cf frozen/capture/verification 均保留；v2 未真实运行。运行环境变量与9阶段 schema 不变。

## v3 窄修：仅 display-list cursor/command 的 uncached RAM alias

root 的 v2 真实尝试 `slot0_weapon_ge_emit_fire6_component_v2` 已取得实际 mode1 helper output64，之后在 VIEW_ENTRY 因 DL cursor=48c5a9d0 触发有效 gate，rows=0/finally成功。原 DL context 在08ca31dc，其+8原字保留 uncached alias；不能把旧 capture cursor 改填08c5a9d0。

v3 仅新增 DL 专属 `commandReadAddress/commandWindow`，普通 pointer/read/window 及对象/矩阵/vertices gate 不变。允许4-aligned CPU地址的完整 window 位于 `[08000000,0c000000)` 或 `[48000000,4c000000)`，再取 canonical=CPU &~40000000。拒绝其它 alias、段外和跨段 window；最终 memory.read 仍只使用普通 PSP RAM 地址，最大长度20000。CPU cursor 运算/delta继续使用原始 CPU值，未将 alias 隐藏。

schema/probe仍兼容：

- 每个 DL snapshot 新增 `readCursor`，`cursor`始终为原 context+8的CPU原字；address仍为DL context pointer。
- 仅 `view.entry.packetBefore`、`view.packetAtGeometry`、`view.commandsThroughGeometry`、`emit.entry.packetBefore`、`emit.returned.packet` 的 command window 新增 `readAddress`；其 `address`仍为原CPU地址，size/raw不变。normal情况下address==readAddress，uncached情况下address=readAddress+40000000。
- 各命令 raw 使用 canonical memory.read保存；并没有从raw bytes反推/篡改CPU cursor。原始 DL context sidecar支持独立重算上述关系。

174 个 VM/Mock 与双syntax检查通过，包括正常/两类handler uncached、RAM下界alias、错误alias/range/unaligned/cross-window，以及普通matrix/vertices不得借用alias的反例。新版本尚未实际运行，完整九阶段仍待root新目录重采与独立audit。

### v3 冻结交接

Producer 47621 bytes，SHA256 `464337805b2210071ae069fccb7b6423b84ae3b61226b4cd77d8327807a3bf74`。新冻结 `out/WEAPON_GE_EMIT_STATIC_20261020/trace_weapon_marker_ge_emit_command_alias_v3_offline_validated.js`，验证 `offline_verification_command_alias_v3.json`，日志 `selftest_command_alias_v3.log`。所有旧 frozen/capture/verification 保留。
