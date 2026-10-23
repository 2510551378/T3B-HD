# source1 selector 的静态 writer 与最小 probe ABI

新增实测覆盖原字段待采状态：见 [WEAPON_MARKER_BINDING_RUNTIME_20261020.md](WEAPON_MARKER_BINDING_RUNTIME_20261020.md)。新capture已保存config90、upper locals和完整handle/actor raw链；本篇保留静态来源与此前证据边界。

范围为固定原模块中的 selector/primary setter、direct caller 链和已有 FEP/state 身份。未连接 PPSSPP 或 UI，未修改已通过的 state sampler、auditor、UE。此报告不把5条 SH inventory 当作全部写入证明；实际 writer 尚未动态观测，`semanticName=null`。

可复现产物：`tools/analyze_weapon_marker_selector.py` → `out/WEAPON_MARKER_SELECTOR_20261020/selector_analysis.json`。原模块 SHA256 为 `b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f`。脚本核对12个有界函数、保存完整原始 code、逐 word disassembly、direct caller 上下文与 shipped literal；map 的 `z_un_*` 仅作为边界标签。

## 1. 哪个函数写 selector

`08b6513c`，size0x118，ABI：a0=context，a1=state或group，a2=newSelector。frame0x20，入口 SP 记 S，执行 prologue 后 local SP=L=S-0x20。

| 入口数据 | 保存位置/寄存器 |
|---|---|
| a0=context | s1 |
| a1=state/group | s2；group递归时可换成child |
| a2=newSelector | s0 |
| caller ra | L+0x18 |
| 原 s0/s1/s2/s3/s4/s5 | L+0/4/8/0xc/0x10/0x14 |

若 byte(state+0)=0x6c，函数取 u16(+4) children count 和 u32(+0x30) child pointer table，递归调用自身；调用 `08b651a4` 的返回点为 `08b651ac`。group 路径不检查每个 child 的 v0，最后固定返回1，不能以 group 的成功值证明所有 child 均写入。

leaf 路径：

1. `08b651e8:8644014c` 读 signed16(state+0x14c)，若等于完整 s0，直接返回1，不执行任何 selector store。
2. `08b651f4:8e440144` 读取 primary handle。
3. primary=0：`08b651f8:50800006` 是 **BEQL**，taken delay slot `08b651fc:a650014c` 执行 SH s0→state+0x14c，跳到 `08b65214`。
4. primary!=0：annul 该 delay-slot store，`08b65200:0e2eefeb` 调 validator `08bbbfac(a0=primary,a1=newSelector)`。失败返回0；成功时 `08b65210:a650014c` 执行同一个 SH，然后到 `08b65214`。
5. `08b6521c` 调 `08b65338(context,state,2)`；该函数只有 `03e00008;00000000`（jr ra/nop），在选定模块中不执行 flags 修改或矩阵重算。随后返回1。

所以两个 SH 互斥，不能把 `08b651fc` 的地址存在当作已经执行。此函数不写 primary+0x144 或 flags+0x154，也不直接写最终矩阵。

## 2. primary setter 与同次配置顺序

`08b646b4`（size0x11c）ABI 与上者相似：a0=context、a1=state/group、a2=newPrimaryHandle，同样递归 group。leaf 先比较现有 primary；不同且旧 selector!=−1 时，用 `08bbbfac(newHandle,oldSelector)` 验证。成功后在 **`08b6478c:ae500144`** 写 primary。旧 selector=−1 的分支直接返回1，跳过 primary 写入。

唯一外部 direct caller `08b5b990`（size0xac）按顺序执行：

```text
08b5b990(objectContext, stateOrGroup, primaryHandle, selector)
  08b5a50c(stateOrGroup, "SetBindObjectPlus")   // 校验byte0为65或6c
  08b646b4([objectContext+18], stateOrGroup, primaryHandle)
  08b6513c([objectContext+18], stateOrGroup, selector)
```

原字符串位于 `08c2d5c0`，ASCII 为 **SetBindObjectPlus**。字符串传给 validator 的 a2，但该 validator 实际只检查 state pointer、byte0；因此把这个标签作为 shipped literal 关联，不凭它推断最终 FX 类型。

这两个写入不是事务：primary setter 可能已成功写入，而随后新 selector 的验证失败；没有 rollback。不能从最终失败码推断两个字段均保持旧值。两个 setter 都不写 flags+0x154。

## 3. selector1 与原矩阵节点的直接关系

`08bbbfac`（size0x108）在 selector=1 时进入普通 mode0 路径：

`handle → 08bbbf9c（直接返回handle） → 08b3f140（解引用handle[0]） → 08b447cc(drawable,1)`。

`08b447cc` 读 drawable+0x3e8 metadata，检查 index>=0 且 index<signed16(metadata+6)；合法返回0，metadata缺失返回−2，非法索引返回−1。`08bbbfac` 将−1/−2转换为验证失败，其余返回1。真枪的独立 geometry 身份已证明 metadata boneCount=3，因此1是合法 source index。

之后已经实测的 state 更新链读取 signed16(state+0x14c)=1，经 generic/wrapper/helper 取 **同 drawable 的 source[1]+0x40**，再与 WORLD 组合。此处的“节点1”是原 source 索引关系，不等于已命名的 muzzle/socket。record byte+8=0/+0xc=0，constructor先清selector；该 setter链提供了运行后显式配置 selector 的可达路径，尚待实测确认本次游戏调用者。

## 4. 更上层 caller 链和能传入1的来源

在固定模块的 direct J/JAL 扫描中：

```text
22个game callsites
  → 08b26c6c(context, stateKey, primaryHandle, selector, optionalFrame)
    → 08b59a98(_, state, primaryHandle, selector)
      → 08b5b990(globalObjectContext, state, primaryHandle, selector)
        → primary setter 08b646b4
        → selector setter 08b6513c
```

`08b59a98` 的 objectContext 来自 global `[08c3a680]`；它的入口 a0 在该 wrapper 中被覆盖，不能把前一函数 v0 当实际 binding context。`08b26c6c` 先用 `08b274dc(context,stateKey)` 的树查询取得 state，−1则失败；primaryHandle为0则直接返回0。a3=selector 原样传递，t0=optionalFrame；t0!=−1 时另调用 `08b59af4`/`08b65254` 设置 state+0x150 frame 字段，不能把这个参数叫 flags+0x154。

22处中，5处固定 a3=0，2处固定 a3=0x13，其余15处为动态来源；没有静态立即数 a3=1 的调用点。所有上下文原码在 JSON，当前优先候选为：

| game callsite | selector 的静态来源 | 对值1的证据边界 |
|---|---|---|
| `08a9a8c0` / `08a9a904` | `08a97c10` 返回对象+0x90，经 s5/stack+0x1ac保存恢复 | 该字段若为1即可传入；本报告未动态读取字段 |
| `08a9ee0c` / `08a9ee50` | 同类返回对象+0x90，经s3 | 特殊分支将s3改成7/8/9/10，该分支不能产生1；其它分支仍动态 |
| `0896693c` | object+0x1344 | 未读取实际字段 |
| `089805b8` / `08982504` | object+0x14d4 | 未读取实际字段 |
| `08980624` | object+0x14d8 | 未读取实际字段 |
| `089a2558` | object+0x1348 | 未读取实际字段 |

其余动态 caller 是 `0883c1a4`、`088e5608`、`088eafdc`、`0896f8a0`、`08971fe0`、`089a2430`。这15处只能称为“可传入1的动态路径”，不能声称哪一处已配置本次真枪 state。

## 5. 最小单 BP writer probe 合约（已实现，本代理未进行实际采样）

实现于独立 `tools/trace_weapon_marker_selector_writer.js`：ENTRY=`08b6513c` → POST_WRITE=`08b65214`，不修改原 state/output sampler。没有在 `08b651fc` 的 branch-likely delay slot 设普通线性断点。启动先验证完整 setter、primary setter、validator和 wrappers 的原始 code 双恢复身份，并核对实际 game caller 的完整有界函数。

入口先保存 a0/a1/a2/ra/SP、原 state[0:0x1a4]、有界 stack，过滤：newSelector==1、leaf byte0=0x65、旧 signed16 selector!=1。old==1是 no-op，单独记录后继续入口观察，不等待 postwrite。primary非零时必须从 handle[0] drawable 重新核对真枪单243/VTYPE0x522的完整 geometry SHA，而不是只看一个旧 actor 地址；state190/194/198及FEP record可与已证实的源链关联。

| POST_WRITE `08b65214` 检查 | 精确值 |
|---|---|
| SP | leaf入口S−0x20 |
| s0 / s1 / s2 | newSelector / context / 同一个P |
| s3/s4/s5 | leaf入口对应GPR值（leaf路径不改） |
| [SP+0x18] | 原 leaf entry RA |
| live RA（primary非零） | `08b65208`，来自validator调用 |
| live RA（primary为零） | 原 leaf entry RA |
| state+0x14c | 实际 u16=1；保存包含+0x14e的原始word |

POST_WRITE 位于所有 selector stores 之后、callback之前；可以精确读取实际已写状态，不要求整个 state 或矩阵改变。若 validator失败，postwrite不会命中，应 timeout fail closed 并保留入口证据，不能报告成功写入。primary零分支不证明绑定到真枪，只能作为独立非actor候选记录。

direct leaf 的原 entry RA=`08b5b9f4`，其入口 SP=S 时上链 saved RA 为：

| 位置 | 应为 |
|---|---|
| S+0x10 | `08b59ad8`（SetBindObjectPlus wrapper 的 caller） |
| S+0x20 | `08b26d04`（global wrapper 的 caller） |
| S+0x48 | 上述22个game callsite+8之一 |

若 entry RA=`08b651ac`，说明 group递归：每层当前 entry S 是 parent 的 local SP，在 **S+0x18** 读取 parent保存RA，再 S+=0x20，可有界回溯至root setter RA=`08b5b9f4`，然后用root入口S套上述三个offset。必须设置明确最大层数并保存每层raw stack；不猜未知RA。postwrite的SP核对始终用最内层leaf入口S，而非root S。

应先从54组已确认 state身份的同一即时状态观察，但如果绑定早于采样启动，零命中只能说明观察区间未触发；不能说明该 writer 不存在。实际捕获前后均不需要写内存或修改存档。

## 6. 独立采样器实现、输出与离线验证

producer SHA256：`295300d081d950c6dca5342e871a35b2623ce08cf0ae7cf91fe1b8dc85b8ed86`。`node --check` 与 **40 个离线 VM/MockWebSocket 情景** 全通过，未使用网络或模拟器。测试包括 direct/一层与两层递归、35/36项GPR、signed no-op、非目标资源/geometry/group/null primary、每层未知caller、depth超限、错误SP/validator RA/saved RA/GPR、已有BP、原码或disasm不等、postwrite timeout/read error、实际selector不等、额外state改动、external pause及ACK timeout队列清理。

采样器先固定检查模块SHA，完整检查9个函数（selector、primary、bind/global/game wrapper、validator、handle_index、bone_bounds、callback_stub），每个目标game caller函数在该capture首次出现时做同样的完整检查；每次POST_WRITE还核对其16-byte窗口。`memory.read(replacements:false)` 和 `memory.disasm` 恢复值必须逐word等于原模块，保留raw/emuhack与两套恢复sidecar。每个 eligible target保存入口 SP 开始的 **0x400 bytes** stack；递归上限默认8、可设0..16，每层0x20，超过上限或未知 RA 直接fail closed。

仅保留：byte(P+0)=0x65的leaf、P+0x198所指前64bytes具有指定SHA、primary+0x144可解引用至 exact243-vertex/three-bone原枪geometry的目标。primary=null不属于这个probe的目标，不会按零primary分支伪造一条真枪写入。保留所有该目标的新selector请求值；不先把值限制成1，便于观察实际配置序列。入口旧signed16值经u32符号扩展与完整a2比较，符合MIPS equality；实际store验证的是u16(a2)。

输出 `marker_selector_writer.json`，schema=`weapon-marker-selector-writer-capture/v1`。sidecar均为绝对file/bytes/SHA256：

- `rows`：仅完整POST_WRITE实测。`classification=observed_selector_write`，`actualWriteObserved=true`。
- `noOpEntries`：旧selector与a2相同的入口，`classification=no_op_entry`，`actualWriteObserved=false`；继续观察ENTRY，不等待POST_WRITE。
- 每条目标：`entryArgs={a0,a1,a2}`、`context`、`state`、`primary`、`entrySP/RA/GPR/Ticks`、`newSelector`、`oldSelectorSigned/U16`、`expectedStoredU16`、`beforeFields`（含FEP190/194/198、primary、selector word与flags）、`stateBefore`、`resourcePrefix`、`weapon`（含geometry sidecar/SHA及原metadata/draw words）、`entryStack`。
- `callerChain`：`recursionDepth`、每层`recursion`的childEntrySP/RA、parentLocalSP、savedRAAddress/value；`rootSelectorEntrySP/RA`；`savedRA.{bind,global,game}`；`gameCallsite`、`gameReturnPC`、`gameFunction`原map边界。
- 实际写入：`postWrite={pc,ticks,gpr,stateAfter,postStack,fields}`；`changedByteOffsets`只能包含0x14c/0x14d。POST_WRITE处必须SP=leafS−0x20、RA=`08b65208`，因为本probe目标的primary一定非零；不能误要求caller原RA。postStack[+0x18]则必须保留caller原RA。
- 全局：`firstStopTicks/lastStopTicks`涵盖观测到的ENTRY/POST_WRITE；`firstEntryTicks/lastEntryTicks`只涵盖ENTRY。另有entry/postWrite/target计数、rejections、`negativeScope`、`guestTickScope`。没有任何guest stop时ticks=null，只能报告wall-time/stop bounds，不虚构原版运行跨度。
- 失败：保留`inFlight`及已取得的`postAttempt`，timeout明确标为验证/执行结果未知。queued stop保留收取时的BP ownership，ACK超时后恢复已确认自身暂停、保留外部暂停；finally清自有BP并显式release所有指定input。

根代理的既有安全runner参数：`MARKER_SELECTOR_OUT_DIR` 指向全新目录；`MARKER_MAX_STOPS`默认1200、`MARKER_MAX_ROWS`默认12、`MARKER_DURATION_MS`默认15000、`MARKER_STAGE_TIMEOUT_MS`默认3000、`MARKER_MAX_GROUP_DEPTH`默认8。继承 `PPSSPP_DEBUGGER_PORT`、`MARKER_BUTTONS_JSON`、`MARKER_ANALOG_JSON`；默认held={}，不持有按键，仍在启动/cleanup显式release。需要开火时由root设置 `MARKER_BUTTONS_JSON={"square":true}`。不接受覆写已有report。

离线验证命令：

```powershell
node --check work/psp_parse/tools/trace_weapon_marker_selector_writer.js
node work/psp_parse/tools/trace_weapon_marker_selector_writer_selftest.js
```

只有root可决定运行既有隐藏/API runner，本代理没有执行实际脚本、修改存档或启动PPSSPP/UI。

## 7. 别名写入覆盖限制

离线 raw immediate-store scan得到5个 non-SP SH+0x14c，与root inventory一致；另外有19个 SW 和17个 SWC1 的相同直接位移候选，基址是否为目标state尚未建立，不能直接称作41个实际selector写点。未见同一简单形式的 SB，但这不是无 byte writer 的证明。

仍未覆盖基址先加偏移后 store、indexed/copy writes、SWL/SWR、VFPU store、JALR调用链、其它模块或动态代码。当前结论严格限于两条已明确 setter SH及其静态可达调用者，不是“全部 selector 写入已恢复”。
