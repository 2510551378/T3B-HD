# 武器关联状态实际进入原版渲染队列

后续通过实际controller/queue route选择alternate入口，已取得六组精确武器关联handler调用与返回，见 `WEAPON_QUEUE_ROUTES_RUNTIME_20261020.md`、`WEAPON_RENDER_ALT_RUNTIME_20261020.md`。本页保留原enqueue阶段证据，不将其单独升级为GE draw证明。

`slot0_weapon_enqueue_fire6` 通过隐藏 debugger/API 取得 6 次完整 `08bbdce8 → 08b935f0` 配对。91 个 enqueue entry 中 85 个因不匹配所选原 FEP record 被排除；6 个精确资源/原枪目标全部完成返回。没有桌面输入或存档写入。

独立 `tools/analyze_weapon_enqueue.py` 核对完整原始函数双恢复、entry/return SP/RA/callee-saved registers、原始栈中的四层 caller、真实枪械 handle→drawable→metadata/geometry 链，以及 FEP header、完整 192-byte record 和实际 node descriptor。实际参与消费的 D/list/definition pointers 必须是 base-relocated 的绝对地址，不能用原文件 offset 代替 live pointer。

四个此前仅静态可达的 D 都已得到实际 node+40 观测：

| FEP descriptor offset | 完整 enqueue 配对 | 原 render list 中的类型 |
| --- | ---: | --- |
| `10ba0` | 2 | 152 |
| `10be8` | 2 | 152 |
| `10c30` | 1 | 155 |
| `10c78` | 1 | 155 |

所有配对的当前 post definition 均实际为 type14。返回时逐字节核对 `E+8=1`、`E+c=C`、`E+10=P`、`E+14=N`，并依据 entry 前的 320 个 head/tail words 和返回后的实际 bucket 链验证新 tail、旧 tail.next 或空桶 head。bucket 与实际返回 v0 一致，观测为 200 或 203；没有声称重放 depth-helper 的 VFPU 数值计算。

6 次调用均保持完整 state 字节不变；其 selector=1、flags=0。节点没有 parent18/1c，transform50 的局部平移前三种为 `(0,0,5)`，最后一种为 `(0,0,7)`，transform54 为 null。这些是原始字节观测，未将其直接命名为最终枪口/弹道坐标。

报告为 `out/WEAPON_MARKER_STATE_CONSUMER_20261020/enqueue_fire6_independent_audit.json`；9 个损坏证据反例全部拒绝，包含 valid-hash 的错误 SP/stack/queue link 和未 relocation 的 live D pointer。实际 strict producer 冻结为 `trace_weapon_marker_enqueue_strict_sampled.js`，SHA256 `85d65e07a5e12d016db590c9457f86deda489603dd70771273187de845e39b0e`。86 项离线 Mock 通过，实际 finally 释放输入、移除自有断点且无错误。

结论到实际 enqueue 为止。原 render list 的 152/155 仍是后续 renderer 的候选；它们的 callback 执行、GE 命令和具体视觉语义须独立运行观测。`geDrawObserved=false`、`semanticName=null`。后续最小三阶段 probe 是 `08b692f4 entry → 08b694f4 before-JALR → 08b694fc callback return`，并必须保持同一 C/P/N/D 与真实 registry/target 身份。
