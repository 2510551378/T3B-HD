# source1 helper 之后的 state+0x60 数据流

范围仅限选定模块的 `08b3e610 → 08bbc93c → 08b62e98 → 08b634ec`，及 parent 已保存的 square6_v2 GPR/stack。未连接 PPSSPP，未修改 trace、auditor、runner 或 UE。语义候选始终为 `null`。

模块 SHA256：`b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f`。下列地址均为原版 guest 地址。

## 记号与真实 stack 交叉核对

令 H 为 helper `08b44580` entry SP，它也是 wrapper `08b3e610` 的 local SP。当前确认链的各 frame：

| frame/数据 | 相对 H | square6_v2 sample0 |
|---|---:|---:|
| wrapper local SP / helper entry SP | +0 | `09ffe140` |
| helper实际output | +0x40 | `09ffe180` |
| generic `08bbc93c` local SP（记 B） | +0x90 | `09ffe1d0` |
| wrapper外部output B+0x120（记 D） | +0x1b0 | `09ffe2f0` |
| state函数 `08b62e98` local SP（记 C） | +0x210 | `09ffe350` |
| parent `08b634ec` local SP（记 U） | +0x370 | `09ffe4b0` |
| parent调用者 SP | +0x3b0 | `09ffe4f0` |

sample0真实保存值：entry s0=D、s1=1、s2=`09bd23c0` handle、s4=`097d2550`、s5=`097d25d0`、s6=`09bd23c0`、s7=0、fp=0。state P=`097d2540`，由 s4-0x10、s5-0x90、stack[H+0x200] 三者一致确认。

| 已保存的 stack offset | 实际值 | 静态含义 |
|---|---:|---|
| H+0x80 | `09ffe350` | wrapper保存的generic s0，即generic输出C |
| H+0x84 | `08bbccd0` | wrapper上层return PC |
| H+0x1fc | `097d25a0` | generic保存的state函数s0，即P+0x60 |
| H+0x200 | `097d2540` | generic保存的state函数s1，即P |
| H+0x20c | `08b630dc` | generic上层return PC |

这些offset由 prologue/epilogue 计算，并与已存raw stack一致，未根据指针外形猜测。

## wrapper 输出并未直接写 state

`08bbc93c(a0=actor handle, a1=selector, a2=output)`：

- `08bbc93c:27bdfe80` 分配0x180 frame；`08bbc948:00a08825` 将selector放s1，`08bbc94c:00c08025` 将output放s0。
- `08bbc95c:0e2eefe7` 调用 `08bbbf9c`。该函数恰是 `03e00008;00801025`，直接返回a0，不额外解引用/包装handle。返回值存s2。
- mode0路径 `08bbc970` 检查selector高位为0，`08bbc978` 取低12位；`08bbc97c` 跳 `08bbccc4`，delay slot `08bbc980:27a40120` 设置a0=B+0x120=D。
- `08bbccc4:02402825` 设置a1=handle s2；`08bbccc8:0e2cf984` 调wrapper，delay `08bbcccc:02203025` 设置a2=bone index s1。

因此在已确认index1路径中，wrapper外部output是generic stack的D，**不是state+0x60**。wrapper在 `08b3e6b8..08b3e728` 把 helper的H+0x40原样复制64bytes到D，`08b3e734/738` 返回并恢复SP；可在 **PC=08bbccd0、SP=B** 观察已经复制完的D。

随后 `08bbccd0..08bbcd4c` 把D的16个word原样复制到B+0xe0；`08bbcd50:27a500e0` 设置a1=B+0xe0，`08bbcd54:0e2ff48f` 调 `08bfd23c`，delay `08bbcd58:02002025` 设置a0=generic output C。

`08bfd23c` 长0x44，实质为64byte memcpy：每轮读写4words，source增加0x10，循环至source+0x40，v0返回初始dest。没有矩阵乘法、归一化或去除translation。故generic正常返回后，C保存了helper输出的完整复制；可在 **PC=08b630dc、SP=C** 观察它。

## 谁指定最终 state+0x60 输出

两处调用 `08b62e98` 均位于 parent `08b634ec`：

| 调用点 | delay slot | 返回PC |
|---|---|---|
| `08b63548:0e2d8ba6` | `08b6354c:02002825`，a1=P | `08b63550` |
| `08b63794:0e2d8ba6` | `08b63798:02002825`，a1=P | `08b6379c` |

两处调用前分别为 `08b63544:26080060` / `08b63790:26080060`，设置 **t0=P+0x60**。其它入参为a0=parent context、a1=P、a2=state+0x198指针指向的数据、a3=a2+0x10。注意 `08b6351c` 的branch delay会将a2从primary handle改成resource/data指针；不能把该处最终a2误当actor handle。

`08b62ed4:01008025` 立即把传入t0保存为s0，随后 `08b62f44:26150030` 设置s5=s0+0x30=P+0x90。因此该函数后续 `(s0)` 的4列写入落到 **state+0x60..0x9f**，`(s5)` 写入落到其translation column **state+0x90..0x9f**。

其 `08b62ea0:8cb60144` 从P+0x144取primary handle；`08b62eac` 保存P到s1。`08b630d4` 调generic时a0=primary handle、a1=P+0x14c的selector，delay `08b630d8:03a03025` 设置a2=C。故数据流为：

`真枪source1+0x40 / WORLD → helper H+0x40 → wrapper D → generic C → state函数按flags组合 → P+0x60`。

## 08b630dc 之后为什么不能直接把 state+60 等同 helper output

`08b630dc:1000003b` 跳 `08b631cc`，delay `08b630e0:33c40020` 计算 `(state[0x154] >> 16) & 0x20`。sample0及sample1的已存fp均为0，故这些样本排除该高位basis分支。

零分支 `08b631cc:5080003f` 的delay `08b631d0:8fa40128` 从C+0x128重新读取**完整state+0x154 flags**。这些lower flags不是fp本身，不能从fp=0推成flags全0。之后按flags的0x40/0x20选择以下分支：

| flags低位 | 起点 | state矩阵写入点 |
|---|---|---|
| bit0x40=1，bit0x20=1 | `08b632e0` | `08b6330c..08b63318` 写P+0x60四列，后续写P+0x90 |
| bit0x40=1，bit0x20=0 | `08b63324` | `08b63350..08b6335c` 写P+0x60四列，后续写P+0x90 |
| bit0x40=0，bit0x20=1 | `08b633c0` | `08b633ec..08b633f8` 写P+0x60四列，后续写P+0x90 |
| bit0x40=0，bit0x20=0 | `08b63424` | `08b63450..08b6345c` 写P+0x60四列，后续写P+0x90 |

这些路径使用C的marker矩阵、C+0x40的primary actor basis矩阵、先前local输出等做VFPU组合。当前通用Capstone未解这些VFPU word；本文保留地址，不把其确切乘法次序/特殊分量写成已验证的公式。已确认的是marker矩阵被读取并参与最终state transform，而非仅一个未使用的临时变量。

所有上述路径汇合 `08b63480`：读P+0x90与P+0x50，再经VFPU指令写回P+0x90（最终store `08b63494:faa00000`）。如完整flags的0x10置位，`08b634b0` 另调用 `08bbc0b4(a0=P+0x90,a1=0)`，`08b634b8:e6000034` 将f0写到P+0x94。故 **返回前的完整state+0x60** 才是最终变换；在中间store暂停可能尚缺translation处理。

## 更上层 saved RA：现有0x240 stack未覆盖的地址

| 位置/字段 | 相对 H | 用处 |
|---|---:|---|
| state函数保存完整flags（C+0x128） | +0x338 | 分辨上述低位分支 |
| state函数保存parent s0（C+0x12c） | +0x33c | parent local state指针P的另一个核对点 |
| state函数保存RA（C+0x150） | **+0x360** | 决定return为08b63550还是08b6379c |
| parent保存s0（U+0x34） | +0x3a4 | 更上层调用者的s0，不无条件叫state |
| parent保存RA（U+0x38） | **+0x3a8** | 决定下面三个调用点之一 |

parent `08b634ec` 的3处direct-JAL callers及相应return：

| 调用点/函数 | parent返回PC | 返回时可恢复的state/context寄存器 |
|---|---|---|
| `08b639c0`，函数08b63924 | `08b639c8` | s0=P，s1=context |
| `08b69ae4`，函数08b69a54 | `08b69aec` | s4=P，s0=context |
| `08b69ef8`，函数08b69dbc | `08b69f00` | s2=P，s5=context |

parent返回时SP应为H+0x3b0。到state函数返回PC（08b63550或08b6379c）时SP应为H+0x370，parent的s0=P应已恢复；此处可保存P+0x60的最终64bytes与state+0x198指针。更上层三个候选的实际选择必须读取saved RA，不能凭context外形或函数所在代码区命名FX。

## 后续最小观测计划（未实现/运行）

不需要增加同时活动BP。可在真枪source1 entry验证后保存H、P与上述saved RA，再逐级交替暂停：helper return `08b3e62c` → generic return `08b630dc` → 动态选定的state返回PC。每一步先remove当前BP ACK，再add下一BP，并核对预测SP/RA。

- `08bbccd0`：验证wrapper外部output D是否与已保存helper输出逐byte相同。
- `08b630dc`：验证generic output C是否相同，保存完整flags与P+0x60修改前状态。
- `08b63550/08b6379c`：读取最终P+0x60，确认组合后的原版state输出。
- 扩到H+0x3ac的stack范围才足以包含两层saved RA；现有0x240 sidecar只支持较浅链。当前报告不能追填这些未采数据。

读取到state+0x198资源指针也只是下一阶段入口；仍需记录资源身份和具体消费，不能直接认定muzzle flash、子弹生成器或常驻attachment。本文 `semanticName=null`。
