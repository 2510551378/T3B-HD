# 武器 marker helper 的实际返回值采集契约

本 agent 仅做选定模块的静态核对、独立采样器实现和离线 VM 测试，未启动或连接 PPSSPP，未操作桌面、窗口、即时存档或 UE 文件。parent 后续使用既有安全 runner 完成了 square-only 的6对实际返回采样，结果见末节。

## 已确认 ABI 与唯一 exit

模块 `raw/ULJM05798_module_08804000.bin`，base `0x08804000`，SHA256 `b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f`。

`0x08b44580` 长0x210 bytes，入口 `a0=64-byte output pointer`、`a1=drawable object`、`a2=source index`。它把三个参数保存到s2/s1/s0，调用 `0x08b460a0(actor)` lazy update，然后读取 actor+0x3c4 指向的 source[index]+0x40 与 actor+0x220 WORLD。输出最终逐 word 写满原 a0 的0..0x3c，不能在返回后重新用当时的a0寻找 output。

| 地址 | 原版机器字 | 含义 |
|---|---|---|
| `08b44580` | `27bdfeb0` | sp -= 0x150 |
| `08b44594` | `00c08025` | s0 = entry a2 |
| `08b44598` | `00809025` | s2 = entry a0 |
| `08b4459c` | `00a08825` | s1 = entry a1 |
| `08b445a0` | `0e2d1828` | 调用 lazy update |
| `08b445a8` | `8e2403c4` | 读取更新后的 source base |
| `08b445c4` | `24840040` | source[index] + 0x40 |
| `08b445c8` | `26250220` | actor + 0x220 WORLD |
| `08b445ec` | `f02488a0` | VFPU 矩阵组合，square-only实际 output 支持 WORLD × source40 次序 |
| `08b44704..08b44774` | `ae44/45/46....` | 原 a0/s2 指向的64bytes写入完成 |
| `08b44778` | `8fb00140` | 恢复 s0 |
| `08b4477c` | `8fb10144` | 恢复 s1 |
| `08b44780` | `8fb20148` | 恢复 s2 |
| `08b44784` | `8fbf014c` | 恢复 entry ra |
| `08b44788` | `03e00008` | 唯一 jr ra exit |
| `08b4478c` | `27bd0150` | delay slot 恢复 sp |

`0x08b3e610` wrapper 长0x12c bytes。其 `08b3e61c:8ca50000` 将 handle 解引用成 actor；`08b3e624:0e2d1160` 调用 helper；delay slot `08b3e628:27a40040` 将 helper output 设置成 wrapper sp+0x40。

因此在 helper entry 观察到 `ra=0x08b3e62c` 时，必须同时有 `entry_output = entry_sp+0x40`。在 return BP `0x08b3e62c` 停止时，该处 `lw a0,0x40(sp)` 尚未执行：

- 当前 sp 应等于 helper entry sp，当前 ra 应仍等于 entry ra。
- helper 已恢复 s0/s1/s2，应分别等于入口时对应寄存器。
- **保存的 entry output pointer** 指向实际 helper 结果。当前 a0/a1/a2 是 caller-saved 临时值，不能用来重识别参数。
- wrapper 还没有把 stack+0x40 的矩阵复制到外部 output。本文采集的是 helper 的真实返回矩阵，不声称已观察更外层 consumer 的最终输出。

该64bytes保存完整16个F32与对应16个u32。依据原 WORLD/source+0x40 布局，以 column-major 4×4 解读、translation slots12/13/14；不转换成12个GE payload，不丢 homogeneous 分量。保存原始bytes是证据，布局/乘积解释可独立复核。

## 采样器状态机及约束

文件：`tools/trace_weapon_marker_output.js`。

启动时列出 CPU BP：如已有 enabled BP，或 entry/return 地址已有任何 BP，则停止且不替换。读取 full helper0x210 与 full wrapper0x12c 的 raw bytes，并通过 `memory.read(replacements:false)` 和 `memory.disasm.encoding/macroEncoding` 两条官方原码恢复路径逐 word 对照选定模块。保留所有 sidecars，任何真实差异/缺失都 fail closed；绝不按0x68前缀放行。官方恢复契约见 [MemorySubscriber](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/Debugger/WebSocket/MemorySubscriber.cpp#L55-L99)、[DisasmSubscriber](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/Debugger/WebSocket/DisasmSubscriber.cpp#L68-L90)、[Read_Instruction](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/MemMap.cpp#L409-L460)。[Breakpoint API](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/Debugger/WebSocket/BreakpointSubscriber.cpp#L114-L219) 明确 add 会替换同地址断点，因此必须先检查冲突。

1. 仅装 entry BP。统计实际观察到的入口；index必须为1、return必须为已确认wrapper地址、output/SP必须满足上述关系。
2. 用 metadata+0x34 draw table重识别真枪：3 source bones、单draw、243vertices、stride16、VTYPE0x522，完整 prefix+geometry SHA `168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a`。本轮额外保存原 geometry bytes，以便独立重算。
3. 保存 entry GPR、output/actor/index/ra/sp、pre source record、source+0x40、WORLD、0x240 stack。
4. **等待 entry BP remove ACK 后**，再核对 return 地址16bytes的两条原码恢复路径，然后添加唯一 return BP，再 resume。不会同时有两个自有BP。
5. 若共享 return PC 被别的SP命中，计作 foreign return，继续有界等候，不配错输出。匹配SP后还必须匹配原ra与callee-saved s0/s1/s2，否则失败。
6. 重新检查同actor的真枪metadata/draw/geometry身份，读取保存output地址的实际64bytes与post source+0x40/WORLD。source base若在lazy update中变化，会明确记录新旧地址；不会沿用旧base读post矩阵。
7. 保存实际F32输出、两种次序的独立 f64 预测 `WORLD × source40` 与 `source40 × WORLD` 及max_abs/RMS误差。这里只记录数据，不预称乘积已匹配或marker已命名。全部 `semanticName=null`。
8. 等待 return BP remove ACK 后再切回entry。达到行数上限则直接清理，无需重新添加entry。

step事件先入队，RPC ticket在send前登记；没有 armed BP 期间的盲目resume或队列清空。遇外部未知PC停止会保留外部暂停。finally明确 release 所有配置按钮及配置analog、仅移除自有BP、仅resume自有暂停。BP add请求在ACK前便登记清理候选，避免ACK失败后遗留自有断点。

## 环境变量与 parent runner 调用

从 workspace 根目录运行。parent 应选择**新的独立输出目录**；若已有 `marker_output.json` 脚本会拒绝覆盖。脚本只连接既有 debugger，不负责打开游戏或加载状态。

```powershell
$env:PPSSPP_DEBUGGER_PORT = '9900'
$env:MARKER_OUTPUT_OUT_DIR = 'C:\Users\25105\Documents\寄生前夜第四日\work\psp_parse\out\AYA_BONE_GE_ACTIONS\slot0_weapon_marker_output_square'
$env:MARKER_BUTTONS_JSON = '{"square":true}'
$env:MARKER_MAX_STOPS = '1200'
$env:MARKER_MAX_ROWS = '12'
$env:MARKER_DURATION_MS = '15000'
$env:MARKER_RETURN_TIMEOUT_MS = '3000'
node work/psp_parse/tools/trace_weapon_marker_output.js
```

输出路径优先取 `MARKER_OUTPUT_OUT_DIR`，兼容旧 runner 的 `MARKER_OUT_DIR`。两者都不应指向既有 capture。analog默认不操作；仅当parent需要时配置 `MARKER_ANALOG_JSON='{"stick":"left","x":0,"y":0}'`，finally会显式归零。

| 变量 | 默认/边界 |
|---|---|
| PPSSPP_DEBUGGER_PORT | 9900，整数1..65535 |
| MARKER_MAX_STOPS | 1200，entry观测次数1..20000 |
| MARKER_MAX_ROWS | 12，完整entry/return pair数1..240 |
| MARKER_DURATION_MS | 15000，100..120000ms |
| MARKER_RETURN_TIMEOUT_MS | 3000，50..10000ms |
| MARKER_BUTTONS_JSON | {}，boolean对象；可用square-only或R+square |

如果选中的entry恰好到达观测时限，允许最多一个额外return timeout完成这对数据；若不能返回，会保留inFlight与诊断并报失败，不伪造完整row。RPC自身也有10秒超时，不把wall-clock时限当作精确guest时长。

## 输出与覆盖边界

`marker_output.json` 包含 codeIdentity/transition history、helper/return stop counts、first/last stop ticks、first/last helper ticks、输入/清理、inFlight与完整rows；实际matrix、source、WORLD、geometry、stack均有bin sidecar与SHA256。即使有限性数值检查失败，已经读到的原始output仍保存于inFlight.returnAttempt。没有自动修改 M1/UE timeline 或正式资产。

后续增补 `preSourcesAll / postSourcesAll`：每份从对应entry/post sourceBase读完整三条0x130 records，共0x390/912bytes，保存file/bytes/sha256。原有preSource/postSource依旧是source1，但现在严格从同一份all-record snapshot的[0x130:0x260]切片，不增加独立读取造成的时序歧义。每条runtime source+0x124是parent pointer，不能按metadata parent index解释。该数据可用于同暂停点比较source0 C0蒙皮后的M1几何tip估计与source1实际helper WORLD transform；比较本身仍不赋予muzzle语义。此增补的实际capture/校准由parent负责，旧6对capture不追填all-record数据。

CPU register category可包含32个GPR之后的PC/HI/LO等额外条目。脚本要求至少32项，仅严格验证前32为u32整数并截取；`gprCategoryDiagnostics`保留类别名称/id/原长度/keys/读取次数。初版错误地要求length===32，parent首次真实运行在寄存器解析阶段停止、0rows且清理成功；修复后不追改这份失败capture，改用新的独立输出目录。

entry BP在等待选中helper返回时没有安装，因此 `helperStopCount` 只覆盖entry armed的时间，不能当作所有helper调用总数。foreign return和一般CPU线程身份没有进一步命名。post source/WORLD是helper返回后的同暂停点快照；若实际乘积不符，应先检查矩阵次序、VFPU布局/rounding与lazy update，不使用拟合source15或人工挂点补差。

## 已完成离线测试

`node work/psp_parse/tools/trace_weapon_marker_output_selftest.js` 使用 VM/MockWebSocket，无真实网络和进程。17个用例通过：

- 正常pair且entry step在add ACK前抵达，单BP切换、保存output指针、post-update矩阵与预先已知非交换乘积均正确。
- 同pair保留完整三records；Mock同时改变未被选中的source0 C0、source2+0x40，验证postSourcesAll确实重新读取，且单source1字段精确来自各自all snapshot切片。
- 35/36项CPU category只使用前32 GPR，保留原长度/名称；31项以及前32中有负数、小数、u32溢出均失败并完整清理。
- 共享return PC的foreign SP被跳过，随后正确pair。
- 非目标index、geometry不符均不误配。
- 已有BP冲突、初始原码不符、return原码不符，均fail closed且不替换外部BP。
- return RA不符、return超时、output读取失败，均清自有BP并release。
- 外部未知PC暂停保留，不被finally resume。

`node --check` 两个新JS均通过。这些测试验证采样器协议与ABI防护，不替代下面的原游戏实际output证据。

## parent 真实运行与独立审计结果

成功capture：`out/AYA_BONE_GE_ACTIONS/slot0_weapon_marker_output_square6_v2/marker_output.json`，SHA256 `a351fa4e78ce9c14faa7336fb95785f238638c23b514a276637956678ef050e0`。独立auditor由parent负责，报告 `out/WEAPON_MARKER_OUTPUT_20261020/square6_audit.json`，passed=true。本agent只读该报告，未修改capture或auditor。

- square-only共284个entry观测、6个return命中、6对完整rows；failure=null，所有自有BP移除，finally输入释放成功。
- 真实register category长度为35，前32 GPR切片修复已实际运行通过。
- 8个代码块（完整helper、完整wrapper、6次return块）通过两条原码恢复路径与选定模块的逐word核对。
- 六对均通过entry/return SP、RA、保存寄存器、raw geometry、source/stack sidecar核对；返回链为 `08b3e62c → 08bbccd0 → 08b630dc`。
- 每次helper历时667 guest ticks。六次均未观察到该调用期间source record或WORLD变化：这组不证明lazy update一定会改值，但return采样已经规避仅看entry的时序歧义。
- 实际64bytes output与 `WORLD × source40` 的最大绝对差为 **0.00015637223987141624**（original numeric units），第一行RMS `3.910346564473839e-05`。反序 `source40 × WORLD` 第一行最大绝对差 **5894.045393933542**，明确不支持该反序解释。

残差尺度与约5684的平移值所处的F32舍入尺度相容；没有因此宣称每一步VFPU舍入与JS f64完全一致，也没有将误差数字改写为“<1e-4”。当前可确认：原版开火相关consumer查询了真枪source1的完整WORLD组合矩阵。仍无helper之后的具体FX资源、发射或渲染消费证明，所有 `semanticName` 保持null，不能命名为已恢复的原版muzzle socket。
