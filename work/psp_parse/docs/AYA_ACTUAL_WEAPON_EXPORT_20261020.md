# 原版独立武器 mesh、材质与12帧 WORLD 导出

此次导出的是与 Aya 106-packet mesh **几何身份完全独立**的原版长枪。旧 weapon OBJ 实际对应 Aya packet86，不能作为武器身份依据。当前武器通过带 VTYPE 前缀的几何 SHA256 定位：

`168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a`

来源为 `out/AYA_BONE_GE_ACTIONS/manual_slot0_damage_probe/manifest.json` 的12帧。frame0 的 VERTICES record=1203；frame1..11 为1210。每帧唯一匹配，原始3888字节顶点数据完全一致。VTYPE=0x522，stride=16，243 vertices、81 triangles。全部原始顶点位模式保存在 `out/AYA_EXACT_WEAPON/weapon.vertices.bin` 和 `weapon.json.source_vertices`。

## 已验证的变换

每帧独立按 PRIM 时序重放 GE WORLD cursor/data（0x3a/0x3b）、VIEW（0x3c/0x3d）、BONE（0x2a/0x2b），均为12个float24、column-major 3×4。INIT矩阵不做猜测：目标 WORLD/VIEW/BONE 必须已被显式写全。

- 每帧以106个 Aya packet 的几何 SHA256 定位 body；106个 packet 的 WORLD 和 VIEW 在同帧全部相同。
- weapon 与 body 在12帧内均使用完全相同的 VIEW。
- weapon 的 bone0 在12帧均为 `59.2998046875 * I`，平移为0。
- 243个顶点的原始权重均为 u16=32767，即32767/32768；未擅自当成1。

原始 actor-space 运算：

```text
actor = inverse(body_WORLD) * weapon_WORLD * (weight * weapon_BONE * normalized_position)
normalized_position = s16_position / 32768
```

由于 weapon_BONE 平移经验证为0，T3BSKN2 将原权重先乘入 local position，并用1个 virtual bone、权重1：

```text
exported_position = normalized_position * original_weight
virtual_matrix(t) = inverse(body_WORLD(t)) * weapon_WORLD(t) * weapon_BONE(t)
```

这样 WORLD 平移只应用一次，且不会错误地被权重缩放。runtime 不依赖任何推测的右手/socket 名称。

12帧全部顶点对比原始运算顺序与导出 float32 数据，最大距离误差 **7.731397398637444e-6 原版坐标单位**，小于1e-4验证阈值；转换到当前 PC 场景单位后为8.555743715433884e-8。二进制重新读取验证 header、全部顶点位置/权重、12个时间值及144个矩阵分量通过。

## 时间、比例与资源接口

时间严格共用本次 body 的 `manual_slot0_damage_probe` 12帧，`(ticks-ticks0)/333000000`。样本范围0..2.7358837127685547秒；是稀疏 runtime 姿态，尚不是完整动作文件。与 body 的时间数组完全相同。

共用 `out/AYA_SOURCE_SKIN_EXPORT.json`：

- `pc_units_per_original_unit=0.01106623198148076`。
- `reference_floor=-0.15446150302886963`。

最终模型文件已经写入：

- `out/AYA_EXACT_WEAPON/aya_source_weapon.bin`。
- `work/t3b_hd/assets/models/aya_source_weapon.bin`。

T3BSKN2：1 virtual bone、1 packet、243 vertices、12 frames、1 material、flags=15（timed、RGB doubling、blend、alpha test）。文件25000 bytes，SHA256：

`beb0ebd6ee27cc3143eb11529898339fa4375ef7a2102a2c27bdd2f38850c34d`

runtime 材质位于 `work/t3b_hd/assets/materials/original_weapon/`，清单为 `aya_original_weapon_materials.txt`，material index=0。

## 原版武器材质

复用已校正时序的 `exact_aya_materials.py`，逐 PRIM 恢复 raw TEXTURE0、持久 CLUT RAM、LOADCLUT 和原始寄存器状态。12帧纹理、CLUT、RGBA及材质状态完全一致。

| 字段 | 观测 |
|---|---|
| 分辨率 | 64×64；buffer width=64 |
| 格式 | CLUT8、swizzled，ABGR8888 palette |
| UV | U16 /32768，scale=(1,1)，offset=(0,0)，REPEAT |
| Texture function | MODULATE，texture alpha，RGB doubling |
| Alpha test | GREATER，ref=0，mask=255，enabled |
| Blend | SRC_ALPHA/ONE_MINUS_SRC_ALPHA ADD，enabled |
| 非全不透明像素 | 40/4096；alpha范围0..255 |

纹理 SHA256：`ced18100c0368ca78a133a0540c92922774ebda9389d73e143ca7f014ec1db77`。

CLUT SHA256：`971195c1a564313ddf81b0222c51616b269d6959554efa39aa339484403fe9be`。

RGBA SHA256：`c280ce4c15928ffcad416a17a35e900766ec150d130e71e028fdfdbeb1f777ab`。

`aya_weapon_c280ce4c15928ffc.png/.bmp` 保存原版颜色与alpha。BMP为32bpp BGRA、BITMAPV4HEADER、显式RGBA masks，经读取后RGBA bytes完全一致。没有对贴图生成、重画或强制不透明化。

## 几何长轴与枪口候选

`weapon.json.geometry_measurements` 保存完整测量。59个唯一位置的 normalized raw bbox：

```text
min = (-0.99993896484375, -0.046600341796875, -0.1273193359375)
max = ( 0.411376953125,    0.046600341796875,  0.265289306640625)
extent = (1.41131591796875, 0.09320068359375, 0.392608642578125)
PCA principal axis = (-0.9959143368439849, 0, 0.09030301029647654)
```

`weapon_geometry_views.png` 的 XZ/XY 投影已视觉检查，枪管延伸至局部-X端。末端3个唯一原始顶点：

```text
(-32766, -669, 3599)
(-32766,    0, 4720)
(-32766,  669, 3599)
```

这3点形成 triangle38 的端盖；枪管另一截面在 x=-20095，具有完全相同的3个YZ坐标。因此几何端面中心的方向为严格(-1,0,0)。供 PC 特效使用的候选值：

```text
tip_normalized_raw = (-0.99993896484375, 0, 0.12123616536458333)
runtime_local_position = (-0.9999084491282701, 0, 0.12123246553043523)
runtime_local_direction = (-1, 0, 0)
```

runtime_local_position **已乘原权重**，用导出的当前帧 virtual_matrix 变换后再做与 body 相同的比例/floor转换，不要重复乘权重。该点是由枪管几何测得的特效起点候选，**不等于恢复了原版 muzzle socket 数据**。

## Source15 候选与未解决内容

在每帧实际 body GE draw 中提取 source15 的矩阵，并验证同帧所有引用都一致。以frame0建立固定 `C15=inverse(S15_0)*weapon_actor_matrix_0`，后续用 `S15_t*C15` 预测武器，最大顶点偏差 **0.08434938595133402 原版单位**。结果与独立探查一致，因此 source15 是本组姿态下较稳定的 attachment 候选；本导出使用逐帧真实 WORLD，不使用此近似，也不赋予 source15 右手/手指等解剖名称。

尚未恢复武器的原版资源名、attachment对象字段或原版muzzle socket/枪口发射数据；此处也未把12帧扩展为完整动作。工具未运行 PPSSPP、未修改即时存档、未修改 M1 源码或现有共享解析脚本。

复现：

```powershell
python -X utf8 work/psp_parse/tools/export_aya_actual_weapon.py --metadata work/psp_parse/out/AYA_SLOT0_SKELETON_METADATA.json --manifest work/psp_parse/out/AYA_BONE_GE_ACTIONS/manual_slot0_damage_probe/manifest.json --timing work/psp_parse/out/AYA_SLOT0_CORE_TIMING.json --body-report work/psp_parse/out/AYA_SOURCE_SKIN_EXPORT.json --runtime-root work/t3b_hd --out work/psp_parse/out/AYA_EXACT_WEAPON
```
