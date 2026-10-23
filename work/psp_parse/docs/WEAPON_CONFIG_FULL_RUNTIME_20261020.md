# 完整武器配置的运行时来源核验

`slot0_weapon_config_full_fire6` 取得 4 次完整 selector 写入及同暂停点的完整 `0xe4` config、manager 来源和 108 个 pointer-table words。采样仅使用隐藏进程与 debugger/API，没有桌面输入或存档写入。此处不把请求资源 ID 命名为某个 FX。

独立 `tools/analyze_weapon_config_source.py` 从 raw 窗口重算所有地址和 membership，再逐一比较原 section 的 108 个完整记录。四次都唯一匹配 **index 18**，完整 228 bytes 逐字节相同，SHA256 `2e4bce0176650bf775e6cec3711b11da829bc5339e160b6a332ef9eeadc83e7b`。此前 16-byte 片段有 34 个候选；本次完整记录消除了该歧义。

运行时观测：

| 字段 | 原始字节解算 |
| --- | --- |
| `[08c3bc0c]` | `09ca11c0` |
| manager=root+340 | `09ca1500` |
| manager+8be0 连续表 | `09c99360` |
| manager+8be4 pointer table | `09c9f3b0` |
| manager+8be8 count | 108 |
| 实际 config | `09c9a368`=连续表+18×e4 |
| config+90 | 1，传入原 selector writer |
| config+94 | `00280216`，传入请求资源 ID |

108 个 pointer-table words 全部保存，但没有解引用其 payload；它们均不等于本次 config，报告保留 `contiguous_only` membership。不能仅从 membership 或 actor mode 宣称实际执行了哪条 getter 分支：上层 `08977028` 还可能改写 config 指针。没有读取 live section header，故不确认完整运行时 section 基址。

原 section 位于 ISO `0757111c`、24632 bytes，SHA256 `7411909bb4e848af75628d4c305bccc1d25361cdf91e79831984900f12e866f3`。原 header 的 count=108、stride=e4、records offset=8 与完整尺寸一致；从完整 section 提取的第 18 项与捕获记录相等。本结论不扩展为全部 config 字段语义已恢复。

证据：

- `out/WEAPON_CONFIG_SOURCE_MATCH_20261020/full_record_runtime_audit.json`：4 行完整记录与 manager/alias 的独立核验。
- `full_record_negative_cases.json`：7 个错误证据反例全部拒绝；另一个保留合法 raw、只改未知字段的反例正确得到“capture 可审计但原记录无 exact match”，没有用近似匹配冒充来源确认。
- `selector_config_probe_sampled.js`：实际 producer 冻结副本，SHA256 `ff8eaa7fbf3738266a83987986a49083df5c199ece9febb33f6d44709c7723bc`。
- 旧 40+45 Mock、新 42 Mock 通过。采集 finally 无错误、释放按键并移除自有断点。
