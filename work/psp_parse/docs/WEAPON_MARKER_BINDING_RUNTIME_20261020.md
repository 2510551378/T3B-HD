# 原版武器 selector 的实际来源与写入

本轮通过隐藏 PPSSPP debugger/API 采集，没有桌面输入或存档写入。旧 producer 已冻结，新 producer SHA256 为 `8383019e838baf4fa6eb1b31ff6bc4518382bf1257d1e4e1c045ed956a1f1bf8`，冻结副本为 `out/WEAPON_MARKER_SELECTOR_20261020/trace_weapon_marker_selector_writer_binding_sampled.js`。

## 实际调用链

`slot0_weapon_selector_fire_probe` 与新增的 `slot0_weapon_selector_binding_fire6` 各取得 4 次完整 selector 写入，均为 old=0 → new=1。每组有 8 个 entry stops，其中 4 个为 group entry，4 个为所选 leaf；没有将 group 当作一次 leaf 写入。

实际链为：

```text
08976f1c 的调用点 08977cc0
  → 08971edc 的调用点 08971fe0
    → 08b26c6c → 08b59a98 → 08b5b990
      → 08b6513c（group → leaf，一层递归）
        → 08b65210: SH s0,state+14c
        → 08b65214: POST_WRITE
```

独立审计从原始 stack 重新展开递归和 saved RA，核对每个 JAL 与完整原始函数。POST_WRITE 的 SP=leaf entry SP−0x20，live RA=`08b65208`（validator 返回点）；栈保存的原 caller RA=`08b651ac`。4 次配对间隔均为 70 guest ticks，完整 state 只改变 byte+0x14c，flags 不变。

## 新采集补齐的原始数据

所有地址均从本次 leaf GPR/stack 解算，未硬编码此前 RAM 对象地址。原代码来源与 frame ABI 见 `WEAPON_MARKER_SELECTOR_SOURCE_20261020.md`。

- `config+0x90=1` → 上层 stack+0x378=1 → game s2=1 → writer a2=1，4 次全部由 raw windows 交叉核对。
- `config+0x94` 与上层 stack+0x374 均为 `0x00280216`，这是请求资源 ID。
- actor+0x161e 实际为 0，故选 actor+0x80 指针数组的第 0 个 24-byte record。该 record 首 word、上层 stack+0x37c 与 state primary handle 均为 `09bd23c0`。
- raw primary handle → drawable → sourceBase/metadata → draw header 的指针链已保存；metadata 为 3 source bones，draw 为 243 vertices、VTYPE `0x522`，完整 geometry SHA256 与原枪一致。
- 所选 slot 的缓存 stateKey 依次为 `0x55`、`0x87`、`0xb9`、`0xee`。它们与请求 ID `0x00280216` 明确不同，不能混称一个资源标识。

每行保存 9 个 binding windows，以及 handle4、drawable字段40、metadata64、draw16和完整 geometry。旧 capture 缺少这些 raw 解引用窗口，其独立报告保持 `primary_to_actor_raw_dereference_retained=false`；新增 capture 为 true，不能将新证据追填到旧 capture。

## 独立验收与范围

`tools/analyze_weapon_selector_writer.py` 独立检查原 module/map/producer hashes、完整原码双恢复、单活动断点生命周期、raw stack、实际 SH 输出及每个窗口地址/字节。报告：

- `out/WEAPON_MARKER_SELECTOR_20261020/fire_probe_independent_audit.json`：旧 4 次写入、14 个 code blocks。
- `out/WEAPON_MARKER_SELECTOR_20261020/binding_fire_independent_audit.json`：新 4 次写入、完整 raw identity 与 selector/primary 来源。
- `binding_independent_negative_cases.json`：11 个错误证据反例全部拒绝，包括重新计算正确 hash 后篡改 config90、upper378、primary record 或 slot count。
- `tools/trace_weapon_marker_binding_selftest.js`：45 个离线 Mock 场景通过；原 selector selftest 的 40 个场景继续通过。

两次实际采集均无 failure、无未完成配对，finally 释放按键并移除自有断点。它们只覆盖当前调用路径，未覆盖全部别名 store、其它模块或所有战斗状态。

本轮确认的是原 source index 1 的配置来源和写入。它与先前 helper/state 矩阵、FEP record 身份证据相连，具体使用它的 FX/弹道 consumer 仍需追踪。`semanticName=null`，不因枪管附近的位置而将其直接命名为最终 muzzle，也未据此替换 M1 正式几何枪口。

## 原配置片段的来源搜索

四行 `config+0x8c` 的 16-byte 窗口在完整 ISO 中有 34 处 exact matches，均落在 pack type34、section0（ISO `0x0757111c`、24632 bytes）。因此没有唯一确认完整 config record 或 live section base。目录由 ISO9660 中 `3rd.pkg` 的真实 LBA 换算，并逐项核对实际 pack headers；没有将旧 CSV 的相对偏移当作 ISO 绝对偏移。全部候选、提取 section 和限制见 `WEAPON_CONFIG_SOURCE_MATCH_20261020.md` 与 `out/WEAPON_CONFIG_SOURCE_MATCH_20261020/source_match.json`。下一步须取得完整 config record/manager 表关系后消歧，不能从这 16 bytes 选一个候选补填。
