# 原版队列实际分发路径

隐藏 PPSSPP/API 采集 `slot0_weapon_queue_routes_fire6/queue_routes.json` 完成七个顺序观察阶段，全部正常结束。原 module 的六个完整函数均通过 memory.read 原码恢复和 disasm 独立恢复；每个阶段仅一个自有断点，实际 stop/resume 配对 30 组。producer 在连接前冻结，SHA256 为 `98f92c1c3f89aaa2e7d7d8a25f200ec82dd4020312d16921ca7dca3148243241`。

| 阶段入口 | 实际停止数 | 阶段前后 guest ticks 增量 |
| --- | ---: | ---: |
| enqueue `08bbdce8` | 6 | 43992814 |
| range_draw `08bbda68` | 0 | 677776978 |
| range_alt `08bbdb20` | 6 | 39069023 |
| callback `08bbd7f0` | 0 | 677776978 |
| callback_alt `08bbd828` | 6 | 22222196 |
| controller_dispatch `08b5ac60` | 6 | 33333294 |
| enqueue_control `08bbdce8` | 6 | 33333294 |

每阶段初末都有完整 `cpu.status` ACK，均显示 paused=false、stepping=false；ticks 不回退。该协议中的 ticks 是 CoreTiming CPU cycles，running 时的 PC 只是近似值，依据 [PPSSPP v1.20.4 官方 CPUCoreSubscriber.cpp](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/Debugger/WebSocket/CPUCoreSubscriber.cpp#L90)。这里的 tick 差覆盖每个顺序阶段及处理开销，不是相同 guest-time 的同时覆盖，也不把它换算为某个动作的精确时长。

30 个实际暂停点都通过原始 global4→controller30 字节记录确认：`[08c3a680]=09c87e30`，controller `+2e=0`、`+2f=1`。因此本次现场与静态 alternate 分支条件一致。range_alt 的六次观测交替为：

- `(a0=2,a1=9,a2=256)`，caller RA=`08b5ae8c`，三次，范围含此前精确武器 enqueue 所在 bucket200/203。
- `(a0=4,a1=266,a2=8)`，caller RA=`08b5a378`，三次，范围不含200/203。

controller_dispatch 的实际 a0 均等于同暂停点的 global controller，a1 有 `0/1/2/3/-2`，caller RA 均为 `08b593c8`。必须区分此处 callback mode 与下层 range 函数的 a0；callback mode3 对应下层 range mode2。

callback_alt 六次 E 原始记录的 kind byte8 都为1，bucket分别315、315、9、64、93、104。它们是本阶段最早的六个入口，**没有按原枪或原 FEP 选择**；不能把它们直接称为武器节点、handler return 或 GE draw。C/P/N 字段仅按 E+c/10/14 解引用留存，未升级为已验证对象语义。

root 的 `tools/analyze_weapon_queue_routes.py` 独立从 raw registers、原始 stack、controller global/bytes、code/disasm、phase status 和全部 RPC/resume ACK 复核；phase status 与 register sidecar 按 ticket 绑定完整 RPC ACK，resume 同时核对 ticket/通知和 wall ordering。报告 `out/WEAPON_QUEUE_ROUTES_RUNTIME_20261020/queue_routes_fire6_independent_audit.json` 通过。`verify_weapon_queue_route_audit.py` 的13个坏证据反例全部拒绝，含 valid-hash 错误 controller bytes、伪造 GPR/stack/status、缺或错 resume ACK、并发 BP 和 GE/weapon overclaim；另一个明确标为 synthetic 的 mode3 记录正确分类为特殊265路径，不把其被忽略的a1/a2当实际范围。producer 的42个 Mock 结果独立保留。

本次明确支持优先使用 `08b69b58 → 08b69d64 → 08b69d6c` 做后续精确资源/原枪的三阶段观测。旧 `slot0_weapon_render_fire6` 没有 controller/tick 样本，因此本次发现不能追填为旧 capture 的现场字节；旧零命中仍保持独立的 bounded negative。完整原表、构造器及265特殊路径见 `out/WEAPON_QUEUE_DISPATCH_STATIC_20261020/REPORT.md`。

本采集没有修改原状态字段、寄存器或存档，finally 释放输入、移除自有断点，清理 errors=[]、未消费 stops=[]。
