# Queue route 有界运行观察器

新增 `tools/trace_weapon_queue_routes.js`，只连接已经运行的 debugger。当前仅完成
离线 Mock，没有由本代理连接 PPSSPP、操作 UI、读写即时存档或确认实际 route。
实际执行由 root 的统一 runner 负责。

## Phase 和界限

固定顺序如下。每阶段默认最多 1500 ms 或 6 个 own stops；达到任一界限即收尾。
进行中的 own-stop 数据读取、resume ACK、最终 status 收尾可能超过名义时长，所有
实际 wall 时间均保留，不能把设定时长当作真实运行时间。

| Phase | Entry PC | 完整函数 bytes |
| --- | --- | --- |
| enqueue | `0x08bbdce8` | `0x19c` |
| range_draw | `0x08bbda68` | `0xb8` |
| range_alt | `0x08bbdb20` | `0xb8` |
| entry_callback | `0x08bbd7f0` | `0x38` |
| entry_callback_alt | `0x08bbd828` | `0x3c` |
| controller_dispatch | `0x08b5ac60` | `0x258` |
| enqueue_control | `0x08bbdce8` | 复用首函数 identity |

所有边界须精确匹配本地 `map.ppmap.txt`。原 module base `0x08804000`，固定 SHA256：
`b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f`。
六个 unique 函数分别保存 expected/raw/replacements=false original/disasm/decoded。
两个独立原码恢复结果必须逐 byte 等于固定 module，才会安装任何观察断点。

## 状态、resume 和暂停处理

每阶段初末分别请求 `cpu.status`，保留完整响应、请求与 ACK wall 时间（Unix ms）。
初始或阶段开始处若显示 stepping/UI paused，就退出并保留暂停，不自动恢复它。
已经 running 时不发多余 `cpu.resume`。

官方 v1.20.4 [CPUCoreSubscriber.cpp](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/Debugger/WebSocket/CPUCoreSubscriber.cpp)
显示：`cpu.status` 返回 stepping/paused/pc/ticks，running 时 PC 并非准确定位；
`cpu.resume` 不提供即时成功响应，而通过 resume 事件通知，非 stepping 状态会返回错误。
因此 observer 仅在自有停止后 resume，并等待 ticketed/unticketed `cpu.resume` 通知；
所有 debugger error 原文保留并使观察失败，不能把错误当作运行证明。

任意非自有 PC 的 stepping 通知会中止观察，cleanup 不 resume 外部暂停。
安装断点前先登记 ownership，即使 add ACK 超时也尝试删除自己的断点。
同一时刻最多一个 owned BP。resume 失败或 ACK 超时后不盲目重试，保留诊断和当前状态。
所有退出路径都尝试释放本工具的按钮/摇杆和删除自己的断点；cleanup 错误同样记录。

仅凭 PC 无法区分恰好发生在 owned BP 相同 PC 的外部暂停，报告明确保留此限制。

## Raw 停止记录

每个 own stop 记录完整 `cpu.getAllRegs` 响应、前 32 个 u32 GPR、停止 PC/ticks、
收到停止的 wall 时间和 SP 指向的原始 0x100 bytes。GPR 类允许包含附加 PC/HI/LO；
若提供这些字段，PC 必须与停止通知一致。所有范围/字节数必须合法。

所有入口均保留 a0/a1/a2 原值，不要求 exact weapon。每个 own stop 还保存：

- `global[0x08c3a680]` 的 4 bytes。
- 若其值是合法有界指针，保存 controller 前 0x30 bytes，保留 `+0x2e/+0x2f` 原值。
  null/sentinel/其他未知值原样记录且不跟随，不强制推断路径。
- 两个 callback phase 中，合法 a0 指针保存 E24；E 的 `+0xc/+0x10/+0x14` 若为合法指针，
  分别保存 C0x40、P0x1a4、N0x40 的小窗口。C/P/N 只是原字段标签，未知对象含义不作断言。

controller 只在 own stop 下读取。阶段初末 running status 不附带 manager/controller
读取，不能被误用为与停止原子一致的分支证据。各阶段也不是同一 guest 时间窗。
零命中不证明函数从未执行；需结合 armed interval 和完整 status/ticks 判断观察覆盖。

## 输出契约和复现

必须使用新的输出目录；`queue_routes.json` 用独占创建保留旧证据，所有新 sidecar 也拒绝覆盖。
producer 在连接前对已加载脚本自 hash。

```powershell
$env:QUEUE_ROUTES_OUT_DIR = '<new absolute output directory>'
$env:QUEUE_PHASE_MS = '1500'
$env:QUEUE_PHASE_STOPS = '6'
# 可选：QUEUE_BUTTONS_JSON / QUEUE_ANALOG_JSON（默认不持键）
node tools/trace_weapon_queue_routes.js
```

其余显式边界：`PPSSPP_DEBUGGER_PORT` 默认 9900；`QUEUE_PHASE_MS` 100..10000；
`QUEUE_PHASE_STOPS` 1..24；`QUEUE_RPC_TIMEOUT_MS` 和 `QUEUE_RESUME_TIMEOUT_MS`
默认 1500、范围 50..10000。不提供远端主机连接入口。

报告 schema：`weapon-queue-route-capture/v1`。顶层包含 producer/module/map、
`phaseOrder/phases`、完整 `rpcLog/events/errors`、`transitions/resumes/inputs`、
`codeIdentity/ownedBP/externalPause/cleanup/failure`。每个 phase 的 `statusSamples`
分别标为 before/after，并保留原 ACK 与 wall 时间。`rows` 中每个 raw sidecar 用
`{file,bytes,sha256}` 引用。`resumes` 保存实际 ACK 类型、原 ACK、错误或超时。
这些记录用于独立 auditor，不能只看 console 摘要。

`exactWeaponSelection=false`、`muzzleProven=false`、`GEConsumerProven=false`、
`semanticName=null` 始终明确保留。该工具不改旧 sampler/auditor/UE/checkpoint。

## 离线验证

```powershell
node tools/trace_weapon_queue_routes_selftest.js
```

42 项 VM/Mock 场景通过。覆盖七阶段完整状态 ACK/原码/raw windows、零 stops 但 running、
range 零命中而前后 enqueue controls 命中、连续三次 own stops、GPR32/35/36、
未知 controller 字节/null/sentinel、callback 非法指针、external pause、
ticketed/unticketed resume 成功与错误、无 ACK、status 非法/错误/超时/ticks 回退、
短读、错误 SP、原码/反汇编不符、已有断点、add timeout、remove 失败及拒绝覆盖。
Mock 不建立真实网络连接；原始文件不被修改，临时输出在验证路径后删除。
