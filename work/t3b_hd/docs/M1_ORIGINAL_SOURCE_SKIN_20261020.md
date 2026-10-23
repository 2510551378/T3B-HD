# M1 原版 Aya、真实枪械与材质接入

后续动作/射线/dense采集更新见 [M1_VERIFIED_ACTIONS_AND_RAYS_20261020.md](M1_VERIFIED_ACTIONS_AND_RAYS_20261020.md)。本页保留首次接入时的验证记录；其中 angle/LOS fallback 限制已由后续实现移除。

## 当前完成

2026-10-20 的运行时已实际加载 `aya_source_skin.bin` 和 `aya_source_weapon.bin`。Aya 为 44 source bones、106 packets、3,456 顶点、1,152 三角形；枪械为独立 243 顶点、81 三角形。每条原始 influence 均保留 source index 和量化权重，未按位置区域猜测、未清零矩阵平移、未重复对已变形 OBJ 蒙皮。

新数据布局和 CPU 实现在 `src/aya_source_skin.h`；`Makefile.win` 已加入 header 依赖。旧的“武器”是 Aya 身体 packet86，已经从加载/绘制路径停用。旧 source36 和手工握把校准不参与新资源绘制。

Aya 和枪械分别加载原版 256×256 / 64×64 atlas，保留 alpha。材质解码核对原版 CLUT、swizzle、UV、alpha test、SRC_ALPHA 混合和 RGB doubling；运行时支持带显式 RGBA masks 的 BITMAPV4，并校验文件范围。场景光照仍是 PC 简化实现，不能称逐像素复现原版。

## 矩阵与动作时间

完成 bone43 写入后再次采集整份 records，确认 GE 的 column-major 3×4 等价于 `record40 * record80` 的前三行。528 个 float24 分量中 525 个逐 bit 一致，其余 3 个相差 1 个量化步；最大 float32 与 float24 差约 0.0038 原版单位。该结果支持矩阵排列与乘法次序，不能替代完整 bind-pose / local animation 格式恢复。

存档 CoreTiming section v3 给出 CPU_HZ=333000000。旧工具把帧编号当30FPS会改变采样速度；新 binary 保留 12 个相对采样时间，跨度约2.736秒。来源是 `manual_slot0_damage_probe`，输入 buttons 为空，不能把这些姿态命名为完整射击动画。样本间 affine 插值是 PC 表现选择，最后一帧保持。

枪械位置使用同帧 `inverse(AyaWORLD) * weaponWORLD * weaponBone` 重放，已核对 12 帧中 body/weapon VIEW 一致和 Aya 106 draws 的 WORLD 一致。保持原版权重先于 WORLD 平移的计算次序。没有把 VIEW 写入角色局部空间，也没有把独立武器误归为身体 packet。

source15 是目前最稳定的武器 attachment 候选，但仍未当成已确认的解剖名称或原始游戏挂点。枪口位置采用真实枪械前端封口三角形中心及局部 -X 方向；该几何点与武器共用 affine 变换，尚不是从原版逻辑恢复的 muzzle socket。

## 已跑验证

- MinGW `-Wall -Wextra` 构建通过，无编译警告。
- GE 时序回归2项、材质语义回归7项通过。
- 1920×1080 的 `--preview` 与 `--inspect-aya` 实际运行并输出截图；查看截图确认完整身体、靴子和真实枪械已经绘制。
- C runtime 对原始首尾样本的全部3,456顶点最大差 `1.5632e-5` 原版单位；枪械 C / exported reference 最大差 `8.064e-6` 原版单位。武器另有独立原始 GE operation-order 比较，最大差 `7.7314e-6`。
- 正常场景 `--test` 退出码0；敌人生命归零、4次命中、边界碰撞、LOS遮挡、Overdive进入/返回通过。
- 新资源统计实测 Aya 44/106/3456/12，weapon243/12，legacy weapon disabled。不是只读到一个“44骨骼”常量。

验证产物：`../psp_parse/out/AYA_SOURCE_SKIN_RUNTIME_VERIFICATION.json`。可重跑：

```powershell
python -X utf8 ..\psp_parse\tools\verify_source_skin_runtime.py --runtime-root . --body-report ..\psp_parse\out\AYA_SOURCE_SKIN_EXPORT.json --out ..\psp_parse\out\AYA_SOURCE_SKIN_RUNTIME_VERIFICATION.json
```

截图 `build/m1_source_skin_fire_a.png` 为战斗预览，`build/m1_source_aya_front_a.png` 为无敌人角色检查。另修正了旧 look_at 的 yaw 符号问题，改用相机正交基，避免目标落在镜头后方。

## 后续必须完成

1. 采集有明确输入和姿态证据的瞄准、射击、移动、受击与倒地片段，恢复事件和真实动作时间，而不是给 idle 样本换名字。
2. 定位并确认原版 muzzle socket 与开火事件，移除旧射击代码的 angle/LOS 宽松回退；当前战斗 smoke pass 不证明原版弹道或射击姿势正确。
3. 在已校正 atlas/UV 基础上制作高清细节并对照身体部位，当前仍是原版贴图分辨率。
4. 恢复原版 Twisted、场景物件摆放、完整碰撞和关卡状态机。现有敌人为 PMF 占位，不能称完整原版战斗场景已接入。
5. 继续定位资源在 pack/FEP 中的静态来源，减少对运行时 capture 的依赖；扩展装备、章节、过场和存档系统。

这些项目未完成前，工程是可运行的重制切片，不是完整高清重制版。
