# Aya 与真实武器的逐帧 WORLD 配对

本轮将此前仅有身体的约30Hz采集推进为身体与真枪同暂停点配对，并通过C运行时全帧检查。新序列用于独立检查，尚未替换正式战斗中的短段aim/fire。

## 已确认

真枪原始geometry SHA `168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a` 对应243顶点/81三角形。原版WORLD实际输入是drawable `object+0x220` 的F32 4×4，caller `0x08b526b4`，最终通过 `0x08c01088` 逐列取高24bits写入GE。证据与静态调用契约见 `../../psp_parse/docs/AYA_WEAPON_WORLD_20261020.md`。

正式采集每帧重新解析drawable metadata并核对完整geometry SHA；不固定guest对象地址，不把renderer排序列表游标当资源ID。同暂停点读取44 source骨骼、Aya WORLD、枪械WORLD。

`slot0_fire_world_dense_verified` / `slot0_aim_world_dense_verified` 各60帧，约1.9686秒，中位间隔33.3667ms；无大于1.5×中位间隔的空洞。两段每帧2640项parent pointer检查通过。异步GE请求0/57实际对应采样1/58，按257有效source引用、完整106packet、body/weapon WORLD唯一全等对齐，不能按请求帧号配对。

## 导出与验证

- `assets/models/clips/aya_{aim,fire}_dense_capture.bin`：各44骨骼、106packet、3456顶点、60帧。
- `assets/models/clips/weapon_{aim,fire}_dense_capture.bin`：各1虚拟骨骼、1packet、243顶点、60帧。
- 武器变换由 `inv(bodyWORLD) * weaponWORLD * originalWeaponBone` 得到，保留原始权重折叠、geometry、UV、normal、材料bytes。没有source15拟合或手工握把偏移。
- `export_aya_dense_weapon.py` 独立验证capture、binding、raw source、F32→float24、原版geometry、两次GE重放与binary readback；9项真实数据/反例测试通过。
- `align_aya_world_capture.py` 4项检查通过：正确数据接受、错误枪械WORLD/错误有效骨骼/重复候选全部拒绝。
- 原版256² Aya/64²武器材质保持不变；没有声称已完成材质高清化。

## C 全帧预览

```powershell
.\t3b_hd.exe build\empty_scene.obj --inspect-capture build\aya_dense_capture_clips.txt
```

该模式只加载指定的独立manifest，按每个原始sample time逐帧绘制身体与武器；没有敌人或模拟射击。全60帧C顶点probe被独立核对并冻结在 `../../psp_parse/out/AYA_DENSE_C_RUNTIME_PROBES/`，报告 `AYA_DENSE_CLIPS_C_RUNTIME_VERIFICATION.json` 保留exe、manifest、CSV的SHA。

| 序列 | Aya最大误差（原始单位） | 武器最大误差（原始单位） |
|---|---:|---:|
| aim，全60帧 | 3.09395e-5 | 1.57051e-5 |
| fire，全60帧 | 3.08887e-5 | 1.56260e-5 |

图像：`build/m1_dense_capture_contact_sheet.png`，原始逐帧PPM分别保留。

预览明确显示：采样0..10举枪，20..50放低枪并弯腰，59恢复瞄准。这些是原版真实姿态，但仅凭持键与姿态不能区分具体受击/过渡状态。整段不能作为无接触连续射击循环。正式 `assets/models/aya_source_clips.txt` 继续绑定原先已验证的3采样aim/2采样fire。

默认资产检查、12项场景ray检查、四枪远距离战斗回归及原版source数值验证再次通过；新增检查模式不改变默认游戏路径。

## 未完成

- weapon bone=59.2998046875 I在canonical及两次GE cross-check中一致，中间帧目前复用该常量，尚未逐帧单独读取weapon source bone。
- 需要先拉开与近身敌人的距离，再采集干净的抬枪/开火/回正，识别状态边界并接入正式动作切换。
- 继续恢复原版Twisted、场景、碰撞与章节资源；当前guard代理和简化场景仍是待替换项。
- 原版解剖socket/muzzle数据、完整后坐循环及高清材质仍待确认。

已新增原版敌人候选资源：`../../psp_parse/out/ORIGINAL_ACTOR_CANDIDATES_20261020/` 有两帧精确蒙皮pose OBJ、原版256²RGBA atlas与inventory。28draw/600tris，投影为长臂钩爪异形；未接入M1，下一阶段恢复其source骨骼与连续动作后替换guard代理。

原ISO没有改写，用户第一即时存档SHA仍为 `32f7fe3d3d830079d7b4499066eb488562e33ce945765eea8461fc1fca18dc39`。
