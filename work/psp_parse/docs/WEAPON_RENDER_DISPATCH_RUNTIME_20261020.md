# 武器渲染入口的首次运行采集：零命中

后续已通过实际 queue/controller/tick 观测选择 alternate 路径，并取得六组精确武器关联 handler 调用与返回，见 `WEAPON_QUEUE_ROUTES_RUNTIME_20261020.md` 和 `WEAPON_RENDER_ALT_RUNTIME_20261020.md`。本页保留原入口的首次零命中边界，不追填旧现场数据。

`slot0_weapon_render_fire6/marker_render_dispatch.json` 是隐藏 PPSSPP debugger/API 的实际采集，producer 在连接前冻结，SHA256 为 `0f841ac9149a0456014f8336ed184915f56e037cd1ccff49caf87241340904a5`。从 slot0 的显式备份加载，输入为 R+square，配置观察上限 15000 ms、2400 个 entry stops、6 个完整配对；这些是上限，不是实际 guest 运行时长。

实际 `entryStopCount=dispatchStopCount=returnStopCount=targetEntryCount=0`，没有 rows，也没有 rejection、inFlight 或 failure。完整入口 `08b692f4/24c` 和 wrapper `08b69540/24` 的 memory.read 原码恢复、disasm 恢复均与固定原 module 一致；入口断点 add ACK、输入 ACK、最终输入释放及自有断点移除均保留。没有 guest tick 样本，因此不能证明这一观察窗口中的 guest execution progress，更不能证明不存在渲染消费者。

`tools/analyze_weapon_render_dispatch.py` 默认拒绝零行结果；仅显式 `--allow-empty` 才允许将本记录归为 `bounded_no_render_stops`。此时 `passed=true` 只表示记录身份和上述边界检查通过，同时强制 `actual_callback_invocation_return_verified=false`、`guest_execution_progress_verified=false`、`geDrawObserved=false`、`semanticName=null`。报告为 `out/WEAPON_MARKER_STATE_CONSUMER_20261020/render_fire6_bounded_negative_audit.json`。正常 callback 的独立 auditor 分支尚未被真实成功 capture 覆盖。

`tools/verify_weapon_render_empty_audit.py` 验证此实际空记录，并拒绝 9 个反例：默认空记录、伪造 entry count/guest ticks、GE overclaim、缺断点 ACK/输入 ACK、未释放按键、外部暂停、清理未完成。完整结果在同目录 `render_empty_audit_cases/verification.json`。producer 的 81 项 Mock 通过只代表受控仿真协议检查，不替代真实执行。

原 module 还明确存在另一条候选队列路径：`08bbdb20 → 08bbd828 → 08b69b58`，其 before-JALR 为 `08b69d64`，return 为 `08b69d6c`；已有 probe 选择的路径是 `08bbda68 → 08bbd7f0 → 08b69540 → 08b692f4`。两者均读取 D+2c render list，但入口、caller RA 与部分 setup 不同。下一次应先从实际队列分发确定路径和 guest progress，再建立对应 ABI 采集；不能直接把另一条静态路径标为已执行，也不能将现有零命中解释为已排除原路径。

此前 6 次实际 enqueue 的证据仍独立有效，详见 `WEAPON_ENQUEUE_RUNTIME_20261020.md`。它没有因本次零命中升级为 callback/GE/视觉证明。没有替换 M1 的正式枪口或 timeline。

采集后 `source_protection_after_config_enqueue_render.json` 确认 ISO、slot0 原即时存档、PPSSPP INI 的 SHA256 全部保持原值，且无 PPSSPPWindows64 进程残留。
