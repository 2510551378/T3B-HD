# 实际 selector1 caller 的参数来源

新增实测覆盖原字段待采状态：见 [WEAPON_MARKER_BINDING_RUNTIME_20261020.md](WEAPON_MARKER_BINDING_RUNTIME_20261020.md)。新capture已保存config90、upper locals和完整handle/actor raw链；本篇保留静态来源与此前证据边界。

本报告只读 `slot0_weapon_selector_fire_probe/marker_selector_writer.json`、原模块和 map，不连接 PPSSPP/UI，不修改现有 sampler 或 auditor。它分析实际 caller 的参数来源；root 的独立 writer raw audit 另行负责证明四次实际写入。

复现：`python -X utf8 work/psp_parse/tools/analyze_weapon_marker_selector_source.py`。输出 `out/WEAPON_MARKER_SELECTOR_SOURCE_20261020/selector_source.json`，含4行现有 stack 解算、8个完整有界函数的原码/disassembly、固定 opcode anchors、下一次所需的地址计算。所有 code 均来自 SHA256 `b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f`。

## 实际观察与结论范围

四行实际 game callsite 都是 **`08971fe0`**，gameFunction=`08971edc`，size0x154，saved return=`08971fe8`。已有 capture 的更上 saved RA 均为 **`08977cc8`**，对应 `08976f1c`（size0xe90）中的调用点 `08977cc0`。这把15个动态候选收敛到实际命中的这一条链。

实际值在四行中一致：selector=1，primaryHandle=`09bd23c0`，game context=`09cae160`，slot container=`09b8b6d0`，上层 actor=`09bb7d60`，config record=`09c9a368`。leaf state/group地址会变化；不以固定state地址作为身份条件。

selector 的来源链是：

```text
config+0x90
  --0897704c load--> upper frame U+0x378
  --08977cbc load--> 08971edc 入口 t0
  --08971f14--> s2
  --08971fdc--> a3 at 08971fe0
  --> 08b26c6c / SetBindObjectPlus wrappers
  --> selector writer的a2=1
```

这建立了明确的原参数字段来源，不建立 muzzle/FX 语义。**旧capture直接保存的是下传后的 game s2=1；config+0x90原字段尚无raw snapshot。** 该字段的实际地址由保存的config指针计算为 `09c9a3f8`，后续必须从栈解算，不应在采样器硬编码此地址。

## 现有 raw stack 的精确 frame 解算

S=leaf selector entry SP，R=callerChain.rootSelectorEntrySP。实测递归depth1，所以R=S+0x20。以下是上层函数 prologue/epilogue明确保存的位置：

| frame | 由R计算 | 本次地址 |
|---|---:|---:|
| game wrapper `08b26c6c` local SP，G | R+0x30 | `09ffe240` |
| game function `08971edc` local SP，Q | R+0x50 | `09ffe260` |
| upper `08976f1c` local SP，U | R+0x70 | `09ffe280` |

| 原始 stack位置 | 保存值/含义 | 四次实测 |
|---|---|---:|
| G+0 | game s0，engine context | `09cae160` |
| G+4 | game s1，primaryHandle | `09bd23c0` |
| G+8 | game s2，selector | 1 |
| G+0x10 | game s4，failure sentinel | `ffffffff` |
| G+0x14 | game s5，slot container | `09b8b6d0` |
| G+0x18 | game return PC | `08971fe8` |
| Q+0xc | upper s3，config record | `09c9a368` |
| Q+0x10 | upper s4，actor | `09bb7d60` |
| Q+0x1c | upper return PC | `08977cc8` |

game s6保存slot byteOffset（`08971f48:0260b025`），下层已核对的函数不修改它，因此 leaf entryGPR[22]=0 支持 slotIndex=0。slot count 的格式为 **u32(container+4)**，slotsBase=u32(container+0)；`08971f1c:00a6302b` 使用 unsigned index<count，`08971f24:00059880` 做index×4。不能将count按u16读取。

上层三项 locals：U+0x374=requested resource ID，U+0x378=selector，U+0x37c=primaryHandle。旧 stack为S[0:0x400]，而U=S+0x90，因此 **U+0x370刚好等于S+0x400**；这组locals全部缺失，不能从旧sidecar补填。建议下一次另读 U+0x370,0x10，而非无限增大整个stack。

## 各参数的原版来源

`08971edc` 入口 ABI：

| 参数 | 原意义（只按数据流） | 本次上层赋值 |
|---|---|---|
| a0 | slot container | `[actor+0x148c]` |
| a1 | slot index | 0 |
| a2 | 请求resource ID，传给虚调用 | `[U+0x374]`，先前来自config+0x94 |
| a3 | primaryHandle | `[U+0x37c]` |
| t0 | selector | `[U+0x378]`，先前来自config+0x90 |

该函数只在container存在、index<count、slot当前为−1时继续。它从 `[08c3bb68]` 取context，调用context vtable descriptor+0x48（signed16 this adjustment、+4 function pointer），将返回值写入slot，然后用这个返回值作为 `08b26c6c` 的 stateKey。**config+0x94的请求ID与虚调用返回/slot缓存的stateKey是两层不同值**，旧capture尚未直接保存二者；不能把FEP record ID或某个指针当作已恢复stateKey。

`08b26c6c` 随后用stateKey查询到已配置的group/state，再传给global wrapper。game context来源于 `[08c3bb68]`；binding object context另来自 `[08c3a680]`，不是同一对象。对本次递归，R−0x14保存binding object context=`09c87e30`，其+0x18指向leaf入口的inner context=`09c87bd0`；这条内存链接尚需raw read确认，两个值不能混称一个context。

## primaryHandle getter 的准确 ABI

`08977038` 读byte(actor+0x161e)，`08977040` 将其正规化为0或1；调用 **`08b38dd0(actor,index)`**。getter完整size为 **0x58**，末尾 `08b38e20:03e00008` / `08b38e24:00000000`。

- `08b38dd0:8c860084`：u32 count=[actor+0x84]。
- `08b38de0:8c840080`：table=[actor+0x80]。
- `08b38dfc:000528c0`、`08b38e00:00a63021`、`08b38e04:00a62821`：合成stride **24×index**。
- `08b38e0c:8ca50000`：取所选24-byte条目首word为handle；无效index/table返回0。

getter返回值在 `08977050:afa2037c` 保存到U+0x37c；到调用前重载为s0，经delay slot `08977cc4:02003825` 作为a3传入。已有capture证明最终handle为真枪handle，尚未直接读取actor数组、bool源byte和所选条目。

## config record 的资源表路径（仍需实际表指针）

upper s4=入口actor。config s3在 `08976fe4/6ff4/7030` 从getter返回值获得，之后到实际调用点前没有覆盖s3的指令；`08977d20`的后续加0x7c发生在调用之后。

资源manager=`u32(08c3bc0c)+0x340`（`0896c5fc`）。一般getter `08ac288c` 从 manager+0x8be0 取连续record base，count在+0x8be8，stride经原码计算为 **0xe4**；越界index回退0。mode=3时有另一条 `08ac28cc` 路径，从manager+0x8be4的pointer table取record。upper读取actor+0x1538选择相关分支，也可能因前面的时间/索引计算再取新record；本次没有manager三字段/实际index的raw evidence，不指定哪条资源表分支已执行。

这里不能凭config地址位于RAM就把它叫原EBOOT静态data，更不能命名某个FX。后续如需给record定位原资源，应先补manager指针/表关系，然后单独做有界原资源关联。

## 下一次只读 provenance 的最小 windows

全部地址从当前R、G、Q及raw指针恢复，先验证guest范围/对齐，再读取；以下不要求新断点或新输入：

1. 保存已捕获stack中的G[0:0x20]、Q[0:0x20]原字，确认两层RA。
2. 另读U+0x370,0x10；应含+374 ID、+378 selector、+37c handle。
3. 读config+0x8c,0x10，保留+90 selector/+94 ID及相邻原字；核对field90=上层local selector=game s2=writer a2。
4. actor+0x80,8；actor+0x148c,4；actor+0x1538,4；actor+0x161c,4。
5. slotContainer[0:8]；检查byteOffset%4=0、index<u32 count，再读slotsBase+byteOffset,4。
6. 正规化actor+0x161e为index，检查index<u32(actor+0x84)，再读u32(actor+0x80)+24×index,24；首word应等于primaryHandle。
7. 保留primaryHandle[0:4]、解引用drawable+0x3c4[0:40]、metadata64和draw16原字；它们是原geometry身份的raw依据，不能仅报告解析后的JSON值。

资源manager/global context/vtable descriptor属于可选后续链；本次最小provenance不需要整段RAM、整份资源表或ISO重扫。零命中或缺失window只报告该观察范围，不回填值。最终 `semanticName=null`。
