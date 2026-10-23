# 武器 state 的实时 FEP 来源核验

`slot0_weapon_marker_state_fep6_v2` 取得 6 组完整 helper/generic/state 返回。独立 `tools/analyze_weapon_state_fep.py` 从原始 sidecars 核对 state+190 的真实基址 `08d4d280`，并将 5 个有界窗口与 ISO 中的 FEP section 比较。报告为 `out/WEAPON_MARKER_STATE_20261020/fep6_v2_source_verification.json`。

- ISO section 起点 `0x56bf7bc0`，长度 778816 bytes，SHA256 `97443c71b1c1d644f323c6ff611afb740329cfe11a47a711f39dc59de06ec802`。
- 原版 table0[4] → descriptor `+0xab8` → pointer list `+0x48e0` → record `+0x48f0`。table1[4] 为 `+0xfb4`。
- state+194=`08d4e234`，state+198=`08d51b70`；实测 header、descriptor、list 与 table1 中的相关指针均发生 base relocation。
- 所选 record 的完整 192 bytes 与 ISO 逐字节一致，扩展了此前仅 64 bytes 的唯一匹配证据。
- header+8 从源值 `0x48` 变为 `base+0x48`；它是 relocated offset/pointer，不能继续解释成固定 header 长度。
- header+0xc 从 0 变为 `0x01ff0000`，语义尚未知。不能把这项不同归为 relocation 或猜测为已确认 flags。

实际读取 1308 bytes，覆盖 header/tables、descriptor、pointer list、table1 record 和 selected record。没有完整转储运行时 778816 bytes；核验结论只覆盖这些窗口。其余 record 的结构见 `SELECTED_FEP_GRAPH_20261020.md`，未采集的 record 不因共享结构而获得运行时语义确认。

首次 `slot0_weapon_marker_state_fep6` 因错误的 header+8 gate 停止，0 组成功；失败和清理记录保留。修正后重采通过，4 个错误基址/地址/hash/语义反例均被独立审计拒绝。采样 producer 冻结为 `out/WEAPON_MARKER_STATE_20261020/trace_weapon_marker_state_output_fep_sampled.js`。

来源身份和 relocation 已有实测证据，具体 FX、枪口或弹道 consumer 仍未确认；未据此替换 M1 正式枪口/timeline。
