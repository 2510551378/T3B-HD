# Aya 原版骨骼与 draw 绑定恢复（2026-10-20）

## 已验证的结果

目标为当前工程内 ULJM05798 的 44-bone Aya capture。采用原版 module 的 MIPS 指令、旧 guest RAM、用户第一个即时存档的独立 PPSSPP 运行和 36 帧已有 GE capture 交叉核对。

- 44/44 parent indices 已恢复，runtime `record+0x124` 指针全部吻合；层级无环，根索引为 0、43。这里只确认索引关系，不推断解剖名称。
- 原版 draw table 包含 106 个 packet、64,560 bytes 和 3,456 条顶点记录。顶点不是去重后的数量。
- 恢复了每个 packet 的增量 palette 更新、完整 palette 状态及每条顶点的 source-index 权重；没有使用 bbox 猜绑定。
- 35 根骨骼有直接非零顶点权重。未直接带权重的索引为 `[0,8,10,18,20,24,35,42,43]`；其中 `[0,8,10,24]` 是带权重骨骼的祖先。其余 5 根的用途尚未确认。
- 旧 RAM 与新战斗运行的 descriptor bytes、整份 draw table bytes 和父子索引全部一致。地址可以变，内容哈希一致。
- 36 帧共有 3,816 次原版 packet 几何匹配（106×36），9,252 次有效 palette/source 引用与原版显式表完全一致；没有错误 source、未匹配矩阵或 primitive/count 冲突。

## 字段与静态依据

Guest module 基址为 `0x08804000`。以下地址只适用于当前提取的 ULJM05798 module；不能作为其他版本的通用偏移。

| 字段 | 已验证用途 | 静态位置 |
|---|---|---|
| `object+0x3e8` | metadata 指针 | `0x08b468e0` |
| `metadata+0x06` | s16 骨骼数量 | 与 44-record runtime 一致 |
| `metadata+0x18` | 每项 0x10 bytes 的骨骼描述表 | `0x08b468e4` |
| `descriptor+0x0e` | s16 parent index；-1 为根 | `0x08b46990`、`0x08b4699c` |
| `object+0x3c4` | 0x130-byte source records | `0x08b469a0` |
| `record+0x124` | parent record pointer | `0x08b469c4`、`0x08b469e0` |
| `parent_record+0x40` | 层级计算读取的父矩阵 | `0x08b46a34`、`0x08b46a3c` |
| `metadata+0x34` | draw table；前 4 bytes 是数量/保留字 | `0x08b4f74c`、`0x08b4f750` |
| `packet+0x05` | palette 更新数量，非每顶点权重数量 | `0x08b4f804` |
| `packet+0x08` | GE VTYPE | `0x08b4f8c4` |
| `update+0x00` | palette index，乘 12 后写 GE BONE cursor | `0x08b4f81c`–`0x08b4f850` |
| `update+0x02` | source index，乘 0x130 得到 record | `0x08b4f854`–`0x08b4f870` |
| `record+0xf0` | uploader 调用的 GE matrix-command payload | `0x08b4f874` |
| `packet+0x06` | 顶点 stride，以 halfwords 计 | `0x08b4f938`–`0x08b4f94c` |

Draw packet 格式：`<Hh4BI` 的 12-byte header，随后 `update_count` 个 `<hh>` palette 更新，再随后 `vertex_count*stride_halfwords*2` bytes 顶点；下一 packet 按 4 bytes 对齐。Palette 保留前面 packet 已设置的插槽。

描述表前 7 个 s16 已原样保留；rotation convention、translation scale 尚未完成验证。`+0x40/+0x80` 的原始矩阵 words 一并保留，不宣称已经确认 inverse bind。快照暂停于 bone-0 writer，不能把整个 source table 当成同一轮已完成的动作帧。

## 修正 GE 时序错误

本地 PPSSPP `raw/Record.cpp` 的 `Recorder::EmitPrim` 先调用 `FlushPrimState` 导出 VERTICES，再把 PRIM 追加到 `lastRegisters`。随后为下一 draw 设置的 BONE/VTYPE 可以与这个 PRIM 一起出现在同一个 REGISTERS block。

实际样本的 record 890 就以 `0403000c` 开头，后面再写 `2a000018` 和 `12008522`。旧工具读取整个 block，将后面的 palette 用到了前面的 draw。新工具逐命令维护状态，仅在 PRIM 时取当前矩阵，并跨 record 保留状态。初始 INIT 中未解读的矩阵不会被编造；只有显式观察到全部 12 个分量才视为可用。

已修正 `extract_ge_timeline.py`、`map_aya_source_bones.py` 和 `audit_source_draw_influences.py` 的相关路径。保留的 `register_state` 仅解析单个 block 的写命令，不代表 draw snapshot。其他旧调用方仍需按用途逐个迁移，历史材质与人体部位报告不能自动获得这项修正。

`test_replay_ge_draws.py` 的两个回归用例检查同块 PRIM 后状态更新、跨 draw palette 继承和不完整矩阵处理；均通过。

## 产物与复现

- `out/AYA_ORIGINAL_SKELETON_METADATA.json/.md`：旧 RAM 的层级、draw 和顶点权重。
- `out/AYA_SLOT0_SKELETON_METADATA.json/.md`：用户存档独立运行的相同解析与逐项比较。
- `out/AYA_BONE_GE_ACTIONS/manual_slot0_metadata/metadata_snapshot.json`：暂停运行时的原始 u32 words。
- `out/AYA_EXPLICIT_PALETTE_GE_VERIFICATION.json/.md`：36 帧的逐 packet/source 验证。
- `out/AYA_ACTIVE_SOURCE_AUDIT_SLOT0_PRIM.json/.md`：修正后的通用 active-influence 审计。它还保留其他几何的 672 次 unmatched，不能归入 Aya 的失败绑定；Aya 显式几何的 9,252 次全部通过。
- `out/AYA_SKELETON_CODE_EVIDENCE.txt`：原 module 的逐 word 指令与 SHA256。

在项目根目录 PowerShell 中运行：

```powershell
python -X utf8 work/psp_parse/tools/recover_aya_skeleton_metadata.py --ram work/psp_parse/raw/ram.bin --metadata 0x08fa3ac0 --source-base 0x09bb32c0 --out work/psp_parse/out/AYA_ORIGINAL_SKELETON_METADATA.json
python -X utf8 work/psp_parse/tools/recover_aya_skeleton_metadata.py --snapshot work/psp_parse/out/AYA_BONE_GE_ACTIONS/manual_slot0_metadata/metadata_snapshot.json --compare work/psp_parse/out/AYA_ORIGINAL_SKELETON_METADATA.json --out work/psp_parse/out/AYA_SLOT0_SKELETON_METADATA.json
python -X utf8 work/psp_parse/tools/verify_aya_explicit_palettes.py work/psp_parse/out/AYA_SLOT0_SKELETON_METADATA.json work/psp_parse/out/AYA_BONE_GE_ACTIONS/manual_slot0_damage_probe/manifest.json work/psp_parse/out/AYA_BONE_GE_PAIRS/manifest.json --out work/psp_parse/out/AYA_EXPLICIT_PALETTE_GE_VERIFICATION.json
python -X utf8 work/psp_parse/tools/test_replay_ge_draws.py
```

存档源文件及备份 SHA256 都保持为 `32f7fe3d3d830079d7b4499066eb488562e33ce945765eea8461fc1fca18dc39`。本轮只加载备份，未写即时存档；采集进程结束，PPSSPP debugger 配置已恢复。

## 仍待解析

先用正确 palette/geometry 身份重核 source index 的身体部位，再验证 bind-pose convention、连续局部动作、武器与枪口挂点。CLUT 和 FEP 的唯一资源绑定另行继续；本轮没有宣称这些已完成，也没有把尚未验证的新层级写入 M1。

本轮工具执行结果是 Python/Node/PPSSPP 的本地证据，不是 REA Evidence。REA MCP 当前未连接；只运行了现有 CLI 的只读 doctor，发现运行时版本和注册问题，未修改其配置或安装依赖。此问题不阻塞上述本地解析和交叉验证。
