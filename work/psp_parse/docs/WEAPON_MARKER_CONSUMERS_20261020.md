# 原版武器 source1/2 consumer 追踪

截至 2026-10-20，本轮确认了可读取 `source[index]+0x40` 的原版函数 ABI、静态调用链，并在真实运行时观察到对当前真枪 source1 的24次查询。该结果确认了原版 consumer，尚不能将 source1 命名为原版 muzzle socket。

## 输入与边界

- 模块：`raw/ULJM05798_module_08804000.bin`，base `0x08804000`，4,911,104 bytes，SHA256 `b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f`。
- 元数据：`out/AYA_BONE_GE_ACTIONS/slot0_fire_reverse120_world60/weapon_metadata_snapshot.json`，完整三条 `0x130` source records，parents `[-1,0,0]`。
- 真枪身份：单 draw、243 vertices、stride16、VTYPE `0x522`，SHA256(`little-u32(VTYPE) || raw_geometry`) 为 `168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a`。
- 静态可复查报告：`out/WEAPON_MARKER_CONSUMERS_20261020/static_analysis.json` 和 `disassembly.txt`。分析只扫描选定模块的 aligned direct-JAL，保留 PSP VFPU 未解码字。间接调用、未记录的对象状态不属于已覆盖范围。

## 精确 ABI 与解引用链

`0x08b44580` 的入口寄存器为：`a0=64-byte output matrix pointer`，`a1=drawable actor object`，`a2=source index`。a1 已是对象，不能再解引用一次。它先调用 `0x08b460a0` lazy update，随后读取 `[a1+0x3c4] + index*0x130 + 0x40` 与 `a1+0x220` WORLD，做矩阵组合并写入 output。入口处读取的是调用前 snapshot，不是 helper 尚未生成的 output。

| 地址 | 原版 u32 | 指令/含义 |
|---|---|---|
| `08b44580` | `27bdfeb0` | `addiu sp,sp,-0x150` |
| `08b44594` | `00c08025` | 保存 a2 到 s0 |
| `08b44598` | `00809025` | 保存 output a0 到 s2 |
| `08b4459c` | `00a08825` | 保存 actor a1 到 s1 |
| `08b445a0` | `0e2d1828` | `jal 0x08b460a0` |
| `08b445a4` | `02202025` | delay slot：a0=s1 |
| `08b445a8` | `8e2403c4` | 读取 actor source base |
| `08b445c4` | `24840040` | source record 的 +0x40 |
| `08b445c8` | `26250220` | actor WORLD +0x220 |

对象身份检查从 `a1+0x3e8` 取得 metadata，再由 metadata `+0x34` 取 draw table；没有借用历史固定地址或 actor 排序游标。

`0x08b3e610` 才是 `(output, handle, index)` wrapper：`08b3e61c:8ca50000` 执行 `lw a1,0(a1)`，`08b3e624:0e2d1160` 调用上述 helper，delay slot `08b3e628:27a40040` 将 output 改为 wrapper 的 stack+0x40。在 helper 入口，正常 wrapper return 为 `ra=0x08b3e62c`，wrapper 上层返回地址位于当前 `sp+0x84`。

另一个 `0x08b3e73c` 接受 handle/index 并直接返回 source+0x40 指针，有 8 个 direct-JAL callers。`0x08b442bc`/wrapper `0x08b3e5b8` 查询的是 source+0x30 translation，经 WORLD 变换，不能混作 +0x40 matrix API。

## 已定位的 state 路径

`0x08b44580` 有 2 个 direct-JAL callsites；其 wrapper 有 27 个。可追踪的 state 路径为：

`0x08b62e98` → `0x08bbc584 / 0x08bbc93c / 0x08bbcd78` → `0x08b3e610` → `0x08b44580`。

`0x08b62e98` 的 state+0x144 是 primary actor handle（`08b62ea0:8cb60144` 读入 s6）；+0x148 是可选 secondary actor handle，在非零分支才参与第二对象变换。state+0x14c/+0x14e 是两个 s16 selector。泛用 transform 将 selector 分成高 mode 与低12位；其中 `0x08bbc93c` mode0 路径直接以低12位作 bone index，其它部分路径经 metadata 数值 tag lookup `0x08b4492c`。该 lookup 读取 metadata+0x12 的 s16 count、metadata+0x28 的 entries，每条16 bytes，以 entry+0xe s8 tag 匹配，返回 entry+0xc s16 bone index 与三个 float offset。当前真枪 count=0，没有此种 aliases。

真实命中 `08b3e62c → 08bbccd0 → 08b630dc` 对应 primary handle + selector14c 路径：`08b630d0` 将 s6 传给 a0，`08b630d4` 调用泛用 transform，随后经 `08bbccc8` 查询 marker matrix。本次 +148=0，正是单对象分支；旧 capture 字段 `actorHandle148` 仅记了该可选字段，并不能代表实际使用的 primary handle。新脚本明确分为 `primaryActorHandle144 / secondaryActorHandle148`，原始证据文件不回写。

再向上，`0x08b62e98` 的两个 direct-JAL sites `08b63548 / 08b63794` 均属于 `0x08b634ec`。该函数依据 state+1、state+0x198 等字段分支，更新 state+0x60 transform。其三处 direct callers 为 `08b639c0 / 08b69ae4 / 08b69ef8`，后两者遍历以 state+0x124 为 next pointer 的状态链，读取 resource+0x198 与类别/状态 flags。这与通用 drawable/effect 状态更新机制相容；仅凭此代码形态不能确定具体 effect，更不能证明该 marker 是枪口。当前 capture 没有更上层有效 unwind，不能声称运行时经过三者中的哪一条。

既有 RAM 中可通过同一 metadata 与三条 parent/source0 C0 bytes 找到历史对象 `0x09b89480`，sourceBase `0x09b89070`，两个含 actor pointer 的 handle 候选 `0x09b8a590 / 0x09b919a0`。当前 capture 对象 `0x09b94fc0` 在旧 RAM 不是同一个有效分配。被动 pointer 引用不是 CPU consumer 证据。

## source1 空间证据及语义界限

source1+0x40 origin 为 `(-59.299999,0,7.499594)`，其局部 +Z 沿枪管前向。与独立几何 barrel cap centroid 距离为 0.310584 original units，与端面轴向距离 0.005624 units。source2+0x40 origin 为 `(-14.599234,1.798889,7.698667)`，局部 +Z 为 +Y。60 帧中这两个 local records 均稳定。

这是 source1 为枪口附近 marker 的空间候选证据。source1/2 的 skinning C0 是经 bind compensation 的矩阵，不能用其 translation 替代 +0x40 marker。模块中找到的 `close muzzle` 等字符串未形成与所选枪或 source1 的连接，不能据此命名。

## JIT code identity 与恢复契约

真实诊断 `slot0_weapon_marker_code_diagnostic/marker_consumers.json` 返回 PPSSPP `v1.20.4`，原始 memory.read 中有3条差异：

| 地址 | module expected | runtime raw |
|---|---|---|
| `08b44580` | `27bdfeb0` | `68064f5e` |
| `08b445a8` | `8e2403c4` | `68069cce` |
| `08b3e610` | `27bdff70` | `68064ee6` |

其它 words 一致。该次 probe 在装 BP 前 fail closed，0 stops，finally 已明确释放输入。上述 bit pattern 与官方 JIT RUNBLOCK 编码一致，**仅前缀不能证明还原后的 original opcode**。

官方 [MIPS.h](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/MIPS/MIPS.h#L27-L41) 定义 RUNBLOCK 前缀；[JitBlockCache.cpp](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/MIPS/JitCommon/JitBlockCache.cpp#L157-L164) 将 originalFirstOpcode 存入 cache 再写入 EMUHACK。[MemorySubscriber.cpp](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/Debugger/WebSocket/MemorySubscriber.cpp#L55-L99) 的 `memory.read(replacements:false)` 在 CPU/memory lock 内临时恢复原指令，读取后还原 JIT replacement。[DisasmSubscriber.cpp](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/Debugger/WebSocket/DisasmSubscriber.cpp#L68-L90) 的 encoding/macroEncoding 调用 [Memory::Read_Instruction](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/MemMap.cpp#L409-L460)，由 JIT 的原始 opcode 恢复路径提供内容。

新采样器同时保留 raw/expected，并要求两条官方恢复路径的全部 words 均与模块全等。macroEncoding 必须完整覆盖，任何真正差异、空洞、重叠、数据行或恢复 API 失败均在装 BP 前停止；没有 0x68 白名单，也不修改模拟器 CPU core 设置。后续 fire 与 idle 实际 capture 均已通过两条恢复路径，独立离线审计重新构建 disasm words 并核对模块与 sidecars。

## 实际 runtime 证据与阴性控制

`out/WEAPON_MARKER_CONSUMERS_20261020/runtime_audit.json` 由 `tools/analyze_weapon_marker_runtime.py` 独立检查保存的 module、original/disasm binary、disasm JSON、source/stack sidecars SHA 与返回链：

| 捕获 | 按键 | 全部 helper stops | 真枪 source1 rows | source2 rows | 已保存时间跨度 |
|---|---|---:|---:|---:|---|
| `slot0_weapon_marker_fire_verified` | R + square | 642 | 24 | 0 | 24条保留行跨度 255,589,417 ticks = 0.767536秒 |
| `slot0_weapon_marker_idle_verified` | 无 | 1108 | 0 | 0 | 旧格式未存全部 helper ticks，未知 |
| `slot0_weapon_marker_aim_control` | 仅 R | 1104 | 0 | 0 | 全部 helper 71424201529..72035347495 ticks，1.835273秒 |
| `slot0_weapon_marker_square_control` | 仅 square | 682 | 24 | 0 | 全部 helper 71368611459..71724619462 ticks，1.069093秒 |

时钟按原记录 CPU 333,000,000 Hz。四次均 code identity verified、failure=null、buttonsReleased=true、breakpointRemoved=true、cleanup errors空。fire保留行 source record SHA 均为 `18d791d6a96fa624fce1da9bcd6e2f3c6bb30fe8fe37a80d234d9b85bd6a4d88`。R+square 与 square-only 的48条保留行具有相同返回链、同一 state 159196480，primary handle 163390400，与经过解引用验证的 wrapper handle 一致；secondary handle=0，selector14c=1、14e=0。square-only 的24条保留行自身跨度0.767601秒；表中1.069093秒覆盖全部 helper，二者不可混用。

控制实验将按键因素分开：source1 查询在 square-only 也出现，R-only 的1.835273秒/1104次 helper 范围内没有出现。这支持“该原版 source1 transform consumer 与开火按键 square 路径关联，R alone 不足以触发”，不支持把它直接命名为 muzzle flash、弹道生成点或 recoil socket。idle的1108次命中只构成有限观察范围内无该武器查询的证据，不能以未知 tick 跨度声称四次观测等时。新脚本保存 `firstStopTicks / lastStopTicks`，覆盖包括被过滤掉的全部 helper 命中；不追填旧捕获缺失的数据。所有报告保留 `semanticName:null`。

此次缺少 helper return/output capture、state 的具体资源标识及后续渲染/FX 消费结果，因此还不能区分开火时更新的常驻 attachment 与短时 effect。下一阶段若继续追踪，应扩大已确认调用栈范围以读取 `0x08b62e98` 的上层 saved RA，并对 helper output 的去向或 state+0x198 资源作有边界验证，不再仅凭 marker 位置重复推断。

## 最小运行时 probe 与离线验证

`tools/trace_weapon_marker_consumers.js` 仅连接 parent 已运行的 debugger，单 BP `0x08b44580`，统计该入口全部调用，只对 index1/2 且完整 geometry SHA 匹配真枪的行保留 source、WORLD、stack 与返回链。不会启动模拟器、加载或保存即时存档。

```powershell
$env:MARKER_OUT_DIR = '<独立 capture 目录>'
$env:MARKER_BUTTONS_JSON = '{"rtrigger":true,"square":true}'
$env:MARKER_MAX_STOPS = '2400'
$env:MARKER_MAX_ROWS = '24'
$env:MARKER_DURATION_MS = '15000'
node work/psp_parse/tools/trace_weapon_marker_consumers.js
```

finally 明确 release 所有配置按键/analog，仅移除自己添加的 BP，仅 resume 自己持有的暂停点。无已验证的返回链不猜 unwind；无 source1/2 命中不能扩大成“该 marker 没有消费者”。下一步以命中返回地址与 state selector 将调用落到具体原版 effect 状态，再决定是否需要单独的 helper-return/output 采样。

离线 `trace_weapon_marker_selftest.js` 使用 MockWebSocket，无模拟器或网络连接。6 个案例通过：正常字节、JIT 恢复、无保留行仍保存全 helper ticks、恢复原字不符、disasm 原字不符、disasm 缺少覆盖。后三个均确认 0 BP、0 held input、诊断保存及 finally release。此测试只证明采样器契约，不替代运行时语义证据。
