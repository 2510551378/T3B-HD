# The 3rd Birthday 原版还原清单

这份清单把“已经观察到的事实”“可用于重制的推断”和“仍需 PPSSPP/静态证据补齐的缺口”分开。它是 PC 高清版的输入边界，不把未验证内容当成已还原。

## 已锁定

| 子系统 | 当前证据 | 状态 |
|---|---|---|
| UMD / pkg 容器 | ISO9660、`3rd.pkg`、436 个 `pack`、245 个 SEDB、42 个 PSMF、624 个 RIFF | 已锁定结构 |
| type-8 网格 | 91 个几何容器、4,120,816 顶点、1,324,784 三角形、20-byte vertex record | 已锁定导出器 |
| 4bpp CLUT 贴图 | 6,195 张、CLUT/像素偏移和 16 色表已验证 | 格式已锁定，语义绑定未全锁定 |
| Aya 运行时网格 | `aya_original_runtime.obj`，2,650 顶点、834 三角形、UV 已恢复 | 可用于重制 |
| Aya 44-bone source object | `0x08b52330` 读取、`object+0x3c4`、44×`0x130` record | 已锁定调用契约 |
| GE 矩阵上传 | `0x08b46e1c → 0x08b4f6e8 → 0x08b4f77c → 0x08b5251c` | 已锁定关键路径 |
| source→GE draw 映射 | 合并 idle/strafe/射击及 60 帧 idle-long 后覆盖 35/44 source indices、3,916 个稳定映射、RMSE=0；新增 60 帧 aim/fire dense manifest 的可用 GE 帧再次覆盖同一 35 个 index | dense manifest 的 60 帧中只有 2 帧有完整 GE dump；仍缺 9 个 index，受击/倒地语义未恢复 |
| Aya 右手 socket | source 36、GE slot 12、draw 1037、24 帧 | 已锁定 |
| 武器枪口方向 | hand rotation + local muzzle offset，运行时归一化 | 已接入 M1 |
| M1 碰撞 / LOS / Overdive | 自动测试 4 hits、collision、LOS、Overdive return | 已接入并通过 |

## 部分锁定

| 子系统 | 已知 | 缺口 |
|---|---|---|
| 44-bone 语义 | 当前射击样本覆盖 26 个 source index 的 GE draw | 其余 source index 需要 idle、strafe、受击、倒地等姿态重新配对 |
| 11 个动作通道 | spine、head、左右上臂/前臂/手、左右腿已有 hierarchy timeline | 尚未证明 11 通道覆盖全部原版 draw state |
| 材质绑定 | 全量已保存 Aya/动作 capture 的 CLUT/TEXTURE0 匹配新增报告统计 206 个 runtime payload signatures，其中 84 个有 exact/subsequence type-8 pack 命中；新增 3 个 1024-byte CLUT 子序列命中来自 `slot0_fire_world_paired3` | 仍有 122 个 payload 未命中，重复 pack 记录和 FEP 语义关联仍未锁定；该匹配不改变默认 M1 材质 |
| FEP | 154/154 块已生成 index/weight/name/offset inventory | 顶点流与完整 skinning 解码仍需 runtime draw 交叉验证 |
| SEDB | 新增 245 个 `SEDBSSCF` 文件的结构 inventory：53,002,424 bytes、统一 version=3/format=0x300400、7,221 个候选 offset regions | 仍只证明容器/区段结构；字段语义、房间/实体 ID、碰撞形状和脚本事件关联仍缺 |
| `3rd.fsd` | 新增结构报告确认 7,932 bytes、header count=761；`0x730` 起 761 个完整 8-byte 条目，全部 tag=1，末尾 `u32=1` 哨兵 | 第二字段高熵且非单调，记录编码、pkg/room/entity 语义尚未解出 |
| EBOOT/PRX | PPSSPP RAM 中的解密代码、矩阵函数、调用点已定位 | 原始 Kirk 加密文件仍不能直接静态反编译，完整函数语义未恢复 |

## 尚未锁定

- 原版对白、菜单文本、字体和汉化文本编码。
- 全部敌人类别的骨骼、攻击状态、伤害/受击状态机和生成规则。
- 当前 PPSSPP 状态文件已确认是可操作教程战斗区，但仍停在“锁定目标/导航”教学阶段；尚未得到可重复触发 Aya hurt/death 的独立 savestate。
- 武器类别、弹道散布、后坐力、弹匣/换弹和全部挂点。
- 关卡触发器、房间流、过场与 gameplay 状态的连接关系。
- 音频事件、混音参数和视频时间轴与场景事件的绑定。

## 下一批证据

1. 用同一套 `BONE_GE_PAIRS` 采集 idle、strafe-left/right、aim、hurt、death 帧，扩展 source→GE coverage。
2. 从每个 type-8 pack 的 draw/material 表建立可复核的 CLUT→draw→场景实体索引。
3. 对 154 个 FEP 块做索引、权重、骨骼流的字段级解码，并与运行时 vertex block 交叉验证。
4. 对 SEDB 和 `3rd.fsd` 做字段聚类，再用 PPSSPP 场景切换/实体生成事件验证语义。
5. 以 PPSSPP 输入/输出 trace 建立敌人、武器、相机和 Overdive 的状态机，而不是只记录画面。

## 证据边界

静态反汇编只能说明代码布局和调用关系；PPSSPP GE/内存 trace 才能证明某个矩阵、draw 或状态在运行时实际出现。任何没有对应 trace、包内字段验证或可重复测试的结论，都必须继续标成推断或未知。

## 2026-10-21 新增验证

- UE 5.8 Game target 已在 ASCII path 通过 35/35 actions；MSVC 14.44.35207 与 Windows SDK 10.0.22621.0 已安装并由 UBT 实际采用。证据：`../t3b_unreal/Validation/ue_game_build_t3bremake_v1.json`。Editor build/Editor render 仍未锁定，SwarmInterface 还需要 .NET Framework SDK。
- `verify_action_clip_probe.py` 已验证 approach_fire Aya/weapon pair：合法输入通过，截断 weapon 与 sample-time 不一致 body 均拒绝。证据：`../t3b_unreal/Validation/action_clip_probe_verification_v1.json`。

- UE SourceData visual replay 已可显式切换已验证的 `approach_fire` Aya/weapon pair；默认 reference，证据 `../t3b_unreal/Validation/ue_game_build_actionclip_v1.json`。
- 最新 C/SDL2 M1 source-spawn 回归保持 4 次命中、敌人死亡、Overdive 往返和单位枪口方向；没有改变原 ISO/存档。

- Aya 44-source hierarchy 新增结构 role audit：35 directly weighted、4 ancestor-only、5 other nonweighted；9 个未映射 index 的状态被独立 verifier 锁定，未推断解剖名称。

- CLUT/TEXTURE0 匹配已复核覆盖全部 17 个保存 capture root、264 个 frame 文件；206 signatures/84 matches/122 unmatched 与旧报告完全一致，未替换默认 M1 材质。

- 原版 rifle `T3BWMK1` source marker（index 1/2）已纳入 UE SourceData 并由 replay loader 校验；未把它命名为 gameplay muzzle/socket。
