# 精确武器关联资源的实际渲染 handler 调用与返回

`slot0_weapon_render_alt_fire6/marker_render_dispatch.json` 已取得六组真实 `08b69b58 ENTRY → 08b69d64 before-JALR → 08b69d6c RETURN`。113 次入口中107次不匹配精确 FEP prefix而排除，剩余6次全部完成调用与返回，没有 inFlight/failure 或清理错误。它使用 slot0 的显式备份、隐藏 PPSSPP debugger/API 和 R+square，没有桌面操作或存档写入。

producer 在连接前冻结为 `out/WEAPON_QUEUE_ROUTES_RUNTIME_20261020/trace_weapon_marker_render_alt_sampled.js`，SHA256 `99506c736f6821451dcc533b41ef0ce0966e5b99d795e61de2289ae2fefc98a0`；此前独立81项 Mock通过。选择本路径的依据来自实际 queue routes 的 controller `+2e=0/+2f=1` 与 guest progress，详见 `WEAPON_QUEUE_ROUTES_RUNTIME_20261020.md`。

| 原 FEP D offset | 配对数 | 实际 type / target | 观测 callback ticks |
| --- | ---: | --- | --- |
| `10ba0` | 2 | 152 / `08b9809c` | 2013、2013 |
| `10be8` | 2 | 152 / `08b9809c` | 1777、1777 |
| `10c30` | 1 | 155 / `08b9a514` | 1946 |
| `10c78` | 1 | 155 / `08b9a514` | 3230 |

六组均为同一 state `097d2540`，节点分别为 `097d2340/21b0/1f60/1d10`。每组留存并独立核对：

- 原枪 handle→drawable→metadata/draw→完整243顶点/VTYPE522的实际 raw identity，ENTRY和RETURN均核验。
- 原 FEP header/table1[4]、完整192-byte record、严格 relocated D/list/definition指针；不能用原文件offset代替 live pointers。
- 完整 dispatcher/wrapper/实际 handler 原码的 memory.read 与 disasm 双恢复，共20个实际 code-check blocks。
- ENTRY caller RA=`08bbd858`，DISPATCH/RETURN SP=ENTRY_SP−30，原始saved frame和callee-saved GPR。
- 实际 registry slot/object/vtable/method20、signed this-adjust、filter byte和JALR t2。before-JALR的a2仍是method descriptor；实际parameter来自t0，delay slot才move至a2。
- `[N+48]+4*definitionIndex` 的原始parameter指针、`[N+44]+u16(B+2)` 的mutable-data来源；type152读取32/7bytes，type155读取76/32bytes，不盲读64byte矩阵。

六组parameter/mutable snapshots前后均未变。这既不否定handler执行，也不证明它没有向其它GE命令缓冲写入。FPR/VFPU与f12没有采集，尤其alternate的N+4c条件时间调整不能从本报告推回精确动画时间。

root `analyze_weapon_render_dispatch.py --route alternate` 从独立raw数据核对6组成功，报告为 `out/WEAPON_QUEUE_ROUTES_RUNTIME_20261020/render_alt_fire6_independent_audit.json`。阳性严格要求三阶段断点生命周期、target/entry/dispatch/return计数和无external pause。`verify_weapon_render_alt_audit.py` 拒绝13个反例，含valid-hash错误registry method和saved RA、混淆delay前a2、错误caller、缺BP生命周期、伪造target计数与GE/语义overclaim；旧empty分支9个反例继续通过。

证据范围到 **actual_callback_invocation_return_verified=true**。`geDrawObserved=false`、`semanticName=null`；未确认具体视觉是枪口火焰、粒子或弹道，未替换正式M1枪口/timeline。后续应在已确认handler内追实际helper/命令写入，如type152的`08b62674/08b6270c`、type155的`08b60374/08b6050c`条件路径，再关联VIEW/GE提交。静态可达helper不能直接计为本次已执行。
