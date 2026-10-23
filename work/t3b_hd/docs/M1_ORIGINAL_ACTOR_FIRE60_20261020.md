# 原版异形、连续射击与武器源骨骼

本阶段把原版异形和新的 60 帧射击记录接入正式 M1。这里只恢复了记录中的几何、材质和姿态；原版 AI、伤害状态机、完整动画循环与高清贴图仍待恢复。

## 原版异形

`assets/models/original_actor_source.bin` 来自 28 packet、1800 顶点、600 三角形的原版对象。完整 11-bone hierarchy 为 `[-1,0,1,0,3,0,5,6,7,8,9]`，11 个 source bone 均参与蒙皮。60 个原始时间采样跨度 1.968607 秒，660 项 parent pointer 检查通过；异步 GE 请求 0/57 实际对应 source 样本 1/58，分别核对 636 个 palette component 和 12 个 WORLD component。对象身份用完整有序 geometry SHA 识别，不固定 RAM 地址。

保留原版 256² CLUT8 RGBA 材质、2524 个非零权重和全部 7920 个矩阵分量。独立 GE/binary 姿态差异最大 1.83e-5 原始单位。单位与 Aya 一致；floor 使用首帧最低点 -2.5759997368，这是明确的 PC 适配策略，不是恢复出的碰撞平面。

主程序实际加载该对象，按同帧姿态生成 600 个三角形用于枪口射线检测，绘制与命中表面的最大同步误差为 0。独立 Python 使用平面求交和 Gram 重心坐标复算，不复用 C 的 Möller–Trumbore 实现。

证据位于 `../../psp_parse/out/ORIGINAL_ACTOR_SOURCE_{METADATA,SKIN_EXPORT,VERIFICATION}.json`、`ORIGINAL_ACTOR_C_RUNTIME_VERIFICATION.json`，完整 C probe 与验证时的 exe 冻结于 `ORIGINAL_ACTOR_C_RUNTIME_PROBES/`。全部 60×1800 个 C 顶点与原版 source 比较，最大误差 6.12383e-5 原始单位。

## 距离拉开后的射击记录

`slot0_fire_reverse120_world60` 先按原版帧计数执行 120 帧后退输入，再采集 60 对 Aya/weapon source，约 33.3667ms 一次。GE 对照中 Aya 与异形 root 间距约 5.68/6.70 PC 单位，避免上一段近身接触中的放枪弯腰姿态。独立原生窗口复现显示远处异形和实际枪口火光；画面保存在 `slot0_fire_reverse120_visual/observed_distant_fire.jpg`。

正式 `assets/models/aya_source_clips.txt` 现在绑定 `aya_fire_reverse_capture.bin` 与 `weapon_fire_reverse_capture.bin`，fire 由 2 个稀疏样本换成 60 个连续样本。aim 仍为先前 3 个稳定样本。身体与枪械共用原始时间轴，末尾 clamp；尚未证明后坐循环边界，不能把约两秒记录称为完整动画状态机。

`AYA_REVERSE_CLIP_C_RUNTIME_VERIFICATION.json` 核对全部 60 帧 C 顶点：Aya 最大误差 3.03906e-5、weapon 1.57373e-5 原始单位。完整 probe/exe 冻结于 `AYA_REVERSE_C_RUNTIME_PROBES/`。逐帧对照图为 `../build/m1_reverse_capture_contact_sheet.png`。

## 武器三骨骼

武器实际有三个 source bone，parent 为 `[-1,0,0]`；draw 只使用 source0。新采集每帧保存完整 912 字节三骨骼记录，并核对选中 source0 的 304 字节记录及 C0 上传值，取代中间帧复用常量的假设。source0 的 GE 为 59.2998046875 I，在本段 60 帧中实际读取一致。

source1 的 +0x40 矩阵原点约 `(-59.30,0,7.50)`，+Z 朝向负 X，与枪管端点中心相距约 0.31058 原始单位、方向差约 0.00562。它是有空间证据的枪口候选，还没有找到使用它生成开火效果的原版 consumer，不能命名为已确认 muzzle socket。source2 同样保留、暂不猜测语义。叶子骨骼的 C0 含 bind compensation，不能用其近零平移替代 +0x40 marker 原点。

## 战斗验证范围

固定 2.55 单位 root 间距的 `--test-ranged` 中，5 发产生 4 次原版变形网格命中和 1 次射向旧场景墙体，完成击杀。独立射线结果差异最大 5.31e-8 PC 单位，报告 `AYA_M1_ORIGINAL_MESH_RANGED_RAY_VERIFICATION.json`。

旧默认近身 fixture 中仍只有 3 次命中，敌人剩 HP25。该 fixture 每 36 帧单次点击，每次 fire clip 都从时间 0 开始；它不是持续按键测试。后续射线穿过网格空处并击中远处旧碰撞墙，不能解释成“墙遮挡了敌人”。末尾姿态中，枪口在敌人 AABB 内，前方无交点、反向约 0.183 PC 单位才有表面交点。

新 `--test-held-close --legacy-scene` 保留相同 spawn、AI、碰撞和命中几何，144 帧后持续请求射击。6 发中 4 次真实 mesh hit、2 次射向墙体，敌人 HP0；fire clip 时间连续递增。独立射线误差 5.07e-8 PC 单位，报告 `AYA_M1_ORIGINAL_MESH_HELD_CLOSE_RAY_VERIFICATION.json`。这个对比说明不能将旧离散点射 fixture 的结果泛化为持续射击失败，也没有恢复出原版的瞄准点或近身碰撞。原版 AI、受击和死亡尚未恢复，异形记录末尾也 clamp；目前旧四柱碰撞仍为 PC 近似。

所有材质仍是原版分辨率。该阶段完成的是原版接入与可验证的数值路径，高清重制和完整游戏目标仍在进行。
