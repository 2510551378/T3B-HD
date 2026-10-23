# 原版 28-packet actor：完整 source skin 导入资产

这份资产来自 `original_actor_source_60` 的原版 guest-memory/source records 与两份独立 GE dump。原版形体为长臂钩爪异形；工具不赋予 species 或骨骼解剖名称。

## 已验证结果

- 原版 metadata 明确给出 **11 个 source bones**，11 个 descriptor parent 与 record `+0x124` 指针一致。
- 父索引为 `[-1,0,1,0,3,0,5,6,7,8,9]`，唯一 root 为 source 0。
- **28 个 packet、1,800 条顶点、600 个三角形**，完整 ordered geometry SHA256 为 `eed4c94e2a8885a866ebfb0ba29f47701d6795b00275cab52896ae4135a5205c`。
- 11 个 source indices 全部有实际非零权重。2,524 个非零 influence 分量保留原量化值，不重新归一化；原顶点权重和范围为 `0.99993896484375..0.999969482421875`。
- **60 个原版时间样本，1.968606975975976 秒**，由存档验证的 CPU clock `333000000 Hz` 计算；不假设固定 30 Hz、循环终点或动作类别。
- 每帧完整 `0x130` source block 共 **660 次父指针检查**通过。7,920 个矩阵分量保存在输出 binary 中，没有丢弃 translation。
- `record40 * record80` 与实际 GE float24 输出在既有 F32 dot-product/float24 truncation 误差界内。近零抵消使最大 raw bit distance 为 32；最大误差/界为 `0.9491569203`，不以 bit distance 单独判定错误。

## 独立 GE 对齐

异步 dump 的请求编号不是 source frame 编号：

| GE 请求样本 | 唯一匹配 source sample | 有效 palette 分量 | WORLD 分量 |
|---:|---:|---:|---:|
| 0 | 1 | 636 / 636 exact | 12 / 12 exact |
| 57 | 58 | 636 / 636 exact | 12 / 12 exact |

对齐使用所有 packet 的真实非零 palette influences、完整 ordered geometry、actor WORLD，不用固定对象地址或 renderer 排序游标。

独立 verifier 直接从 GE 原始顶点格式读取 weights/positions、按 GE slot matrices 运算，与 T3BSKN2 source-index skinning 比较。两个交叉样本的最大位置误差为 `1.32289897e-5`、`1.82740787e-5` 原版单位。该检查未执行编译后的 M1 C runtime；M1 CPU probe 是后续集成验证。

## 材质与场景尺度

材质为原版 `256x256 CLUT8` swizzled texture、ABGR8888 palette。PNG 与 BMP V4 的 RGBA/alpha 均与两份 GE dump 的实际 CLUT 解码逐 byte 一致。

- texture SHA256：`70ee2537a15f93923fa3e732db6ac5d5e0f5f91e6484d57779ba40bf15d406b7`
- CLUT SHA256：`9431f3ba5e5d3af635b653413287433d3a8cda148672e1d260070b43f0b52e57`
- RGBA SHA256：`f2bb1be7a73e3b51fdc9834127e71a84b5dbe01b1e4ad0aa9a5821632763d306`

PC scale 直接取 canonical `AYA_SOURCE_SKIN_EXPORT.json` 的 `pc_units_per_original_unit=0.01106623198148076`，没有按敌人身高单独缩放。floor 明确选择 `first-pose-min`，值为 `-2.5759997367858887`；这是固定导入地面选择，不是恢复到的原版碰撞面。初帧 PC bbox 约为 `[-0.6660,0,-0.2336]..[0.7295,1.8794,0.7664]`。

actor WORLD 用于严格对齐，未烘入 source-local skin matrices；M1 的 actor placement/yaw 负责场景位置。后续样本保留原姿态变化，末样本是否保持由通用 SourceSkin runtime 决定。

## 产物

- `tools/recover_original_actor_metadata.py`：可配置 bone/packet count、原 metadata hierarchy/palettes/weights 解析。
- `tools/export_original_actor_skin.py`：源完整性检查、异步 GE 唯一对齐、原材质和 T3BSKN2 导出。
- `tools/verify_original_actor_export.py`：独立 GE/raw-vertex 对 binary/RGBA 验证。
- `out/ORIGINAL_ACTOR_SOURCE_METADATA.json`：11-bone hierarchy 与完整原版 vertex/source-index 数据。
- `out/AYA_BONE_GE_ACTIONS/original_actor_source_60/manifest_aligned.json`：逐实际 GE pose 匹配后的 manifest。
- `out/ORIGINAL_ACTOR_SOURCE_SKIN_EXPORT.json`：完整导出身份、单位、floor、矩阵、材质与输入 SHA。
- `out/ORIGINAL_ACTOR_SOURCE_VERIFICATION.json`：独立验证结果。
- `../t3b_hd/assets/models/original_actor_source.bin`：通用 SourceSkin 资产。
- `../t3b_hd/assets/materials/original_actor/original_actor_materials.txt`：独立原版材质 manifest。

这些工具不修改 capture scripts、原 Aya/weapon exporters、M1 C/header 或存档。当前记录是一段完整原 actor pose timeline；原游戏全部敌人动作库、行为逻辑和原 pack/FEP 资源命名仍未恢复。
