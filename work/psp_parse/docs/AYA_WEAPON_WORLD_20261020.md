# 真枪 WORLD 来源与约30Hz配对采集

原模块 `raw/ULJM05798_module_08804000.bin` SHA256：`b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f`。

## 直接证据

`out/AYA_BONE_GE_ACTIONS/slot0_weapon_world_probe3/world_sources.json` 在bone43完成点读取一次44-bone Aya，然后单断点切换到通用WORLD writer，保留226次实际上传的GPR、stack、F32矩阵及完整GE dump。

`attribute_aya_weapon_world.py` 用106个Aya packet原始geometry SHA、真枪243顶点geometry SHA和逐PRIM WORLD核对：

- Aya WORLD匹配trace indices10/85/160，matrix pointer `0x09bb6a20`，object `0x09bb6800`。
- 真枪WORLD只匹配index161，matrix pointer `0x09b951e0`，object `0x09b94fc0`。
- 两者caller均 `0x08b526b4`，输入均为 `object+0x220` 的完整F32矩阵。
- 旧采样的候选地址曾为`0x09b951b0`，说明跨run不能固定矩阵地址。
- `s0=0x08c987cc/0x08c987d8` 是renderer排序列表游标，不是resource ID；绝不能按该值持久绑定武器。

结果：`out/AYA_WEAPON_WORLD_SOURCE_BINDING.json`。仅确认WORLD数据来源；未确认骨骼的解剖命名或原版muzzle/socket结构。

## 原版调用契约

```text
0x08b526b4 JAL 0x08bfff6c
0x08b526b8 delay slot: a1 = s7
s7 = s1 + 0x220 ; a0 = 2 ; s1 = drawable object

0x08bfff6c wrapper(selector=a0, matrix=a1)
 -> dl_write_matrix(context=a0, selector=a1, matrix=a2)
0x08c01088 dl_write_matrix
 -> WORLD type2: 0x3A000000 + 12×0x3Bxxxxxx
```

WORLD从column-major4×4 F32读取indices `[0,1,2,4,5,6,8,9,10,12,13,14]`，写入每个float的高24bits。callsite暂停时delay slot尚未执行，必须读s7，不能提前读a1。

模块另有`0x08b51c80`缓存WORLD路径，独立探针149次写入37个场景instance，没有匹配真枪，不能据此把场景实例当武器。

## 采集器修正

- 使用一个断点分阶段采集，避免多地址JIT失效的时序缺口。官方v1.20.4的 `BreakpointManager::Update(addr)` 只保留一个地址，稍后的Frame()才invalidate；连续添加多个BP可能仅最后地址进入新JIT block。它解释了早期BONE/WORLD零命中的现象，不能把零命中当游戏未执行的证明。未核对本地PPSSPP PE实现，源码解释仍标为解释。
- 连接时原CPU可能已暂停；WORLD采集显式resume。官方parser支持`&&`，不能将无命中归咎于复合表达式不支持。
- 正式用 `0x08b526b4` 单断点、`a0==2`，每次读取drawable metadata的drawtable，确认1packet、243vertices、VTYPE0x522，重算完整geometry SHA后才保留。固定排序游标/固定guest pointer不参与身份判断。
- 同一CPU暂停点读取44×0x130 source、Aya object+0x220和真枪object+0x220，全部保留原始F32/GE payload和真实ticks。
- 在武器WORLD上传时，Aya的draw已开始/完成，随后请求的GE dump会落在下一帧。同步removeBP→resume→dump的pilot造成全部不匹配，已作为失败证据保留，未用于runtime。
- 正式保留断点并异步请求GE、继续服务下一帧stop；`align_aya_world_capture.py` 按106packet、257项有效source、body WORLD与weapon WORLD全等唯一对齐。禁止按“请求帧号”猜测匹配。

## 新增数据

`slot0_fire_world_dense_verified` 与 `slot0_aim_world_dense_verified` 各60个配对样本，约1.969秒。中位间隔33.3667ms，最大<33.416ms，无旧采集的首帧200ms间隔。

两段GE请求样本0/57，实际精确匹配样本1/58。每段514项有效Aya引用、24个body WORLD分量、24个weapon WORLD分量完全一致；中间每帧武器geometry重新hash。

身体独立导出 `../t3b_hd/assets/models/clips/aya_{fire,aim}_dense_capture.bin`。持键采样仍可能包含近身受击和动作过渡；先做独立逐帧预览与核对，不直接覆盖现有短段aim/fire正式绑定。

来源：

- [PPSSPP delayed JIT invalidation](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/Debugger/Breakpoints.cpp#L611-L631)
- [single-address update state](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/Debugger/Breakpoints.h#L195-L198)
- [WebSocket breakpoint registration](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/Debugger/WebSocket/BreakpointSubscriber.cpp#L136-L143)
- [CPU resume](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/Debugger/WebSocket/CPUCoreSubscriber.cpp#L84-L96)
