# 高清重制路线

## 当前正式路线（2026-10-20）

用户要求选定正式引擎，现确定为 **Unreal Engine 5**，以 UE 5.8 稳定系列为迁移基线，采用 C++ 与 Blueprint。现有 C/SDL2/OpenGL 2.1 运行时保留为原版资源和数值对照原型，尚未完成 UE 迁移。详细选择与 U0–U3 验收见 `docs/ENGINE_DECISION.md`。

当前已确认并实际接入 C 原型：Aya 44-bone/106-packet、60 帧射击及真实枪械、11-bone 原版异形、140-draw 原街景及 73 张 RGBA 纹理。PC 场景碰撞适配使用 8551 个可确认无透明孔的原街景三角形；原版碰撞、AI、完整动作状态与高清资产仍未完成。最新证据见 `../psp_parse/docs/CONTINUATION_CHECKPOINT.md`。

以下 M0–M3 内容为早期原型路线记录；其中旧 weapon OBJ、source36、手工 pivot/socket 与 guard 占位路径已经被后续证据取代，不能当作当前原版还原结果。

## 成功条件

第一阶段完成后，程序应能在 Windows PC 上启动一段可重复游玩的场景：

- 1920×1080 渲染，稳定 60 FPS；
- 艾雅第三人称越肩镜头；
- 一个纽约战区环境块，包含碰撞和基础灯光；
- 锁定、移动、射击、翻滚、掩体；
- 一类 Twisted 敌人，包含受击、死亡和弱点反馈；
- Overdive 从艾雅切入目标并返回；
- 中文/英文 HUD 切换；
- 运行日志能记录帧率、资源缺失和战斗状态。

## M0：工程骨架与资产验证（已完成第一版）

1. 建立 SDL2 + OpenGL 3.3 PC 运行时。
2. 从 `work/psp_parse/out/meshes/` 读取一个环境 OBJ。
3. 读取对应 PNG 贴图，生成材质和基本法线。
4. 完成自由相机、窗口缩放、资源错误日志。
5. 输出第一张 1080p 截图和三角形/纹理统计。

当前结果：

- `t3b_hd.exe` 已在 Windows 本机编译通过；
- 默认加载 `pack_0x4c199000.obj`；
- 实测加载 102,153 个顶点、34,051 个三角形；
- 1920×1080 OpenGL 窗口可启动，运行标题栏统计约 76 FPS；
- WASD 旋转、Q/E 缩放、鼠标滚轮缩放可用；
- 场景使用深度测试、三角形法线近似着色和距离雾。

仍待补齐：窗口截图回归、真实贴图材质（碰撞盒和可行走区域已在 M1 接入）。

## M1：纽约战区垂直切片（核心循环已跑通）

1. 艾雅重建模型：近景 LOD、头发和衣摆二次运动、枪械挂点。
2. 第三人称镜头、锁定射击、软吸附和目标切换。
3. 基础 Twisted：巡逻、锁定、受击、弱点、死亡。
4. Overdive：时间缩放、跳入目标、短内部镜头、返回本体。
5. 场景雾、体积光、枪口火、命中火花和屏幕空间泛光。
6. HUD：血量、锁定框、武器、Overdive 状态和任务目标。

当前结果：

- `aya.pmf` 已接入，3,457 三角形，支持 idle / hurt 动画片段；
- 原版战斗帧已恢复艾雅静态几何与 UV：2,650 顶点、834 三角形，运行时优先加载 `aya_original_runtime.obj`；
- `aya_albedo.bmp` 已接入 Aya UV；场景包重新导出为 `nyc_block_uv.obj` 并接入重复采样的战区材质；
- 9 个战斗帧已保存到 `assets/models/poses/`；`aya_skeleton.rig` 提供连续 CPU skinning，weapon draw 与 muzzle socket 已接入 M1；
- PPSSPP GE debugger 捕获的 6 组 3×4 矩阵已导出为 `aya_ge_matrices.json` 并接入运行时；
- 武器命令 1095 的跨帧局部坐标已校准，`grip`、`muzzle` 和 `-90°` weapon yaw correction 已用于射线与枪口火线；
- `aya_draw_materials.json` 记录 358 个 draw 的 CLUT/TEXTURE0 哈希，Aya 主 draw 区间使用 `CLUT[834]` + `TEXTURE0[836]` 解码贴图；
- `guard.pmf` 已接入，1,666 三角形，支持 walk / hit / dead；
- 第三人称越肩镜头已接入，镜头会跟随艾雅并在锁定时转向敌人；
- `R` 锁定，`SPACE` 射击，射击会扣除 Twisted 生命并触发受击/死亡动画；
- HUD 已显示艾雅和敌人生命条、锁定准星；
- `--test` 自动回归已验证 `enemy_hp=0`、`enemy_dead=1`。

M1 补充结果：

- `assets/scene/nyc_block.col.txt` 已接入，玩家和敌人都不能穿过边界/障碍盒；
- 锁定只接受视野内、角度和距离符合条件的目标；
- 射击使用 xz 平面射线，障碍盒会阻挡命中和火线；
- `F` 触发 Overdive：0.32 秒切入、1 秒内部镜头、0.32 秒返回，期间时间缩放到 0.25；
- 自动回归已验证：`shots_hit=4`、`collision_boundary=1`、`los_blocked=1`、`overdive_seen=1`、`overdive_return=1`、`enemy_dead=1`。

仍待补齐：真实骨骼矩阵替换重建 pivot、更多动作帧的拓扑对齐、武器切换和 Overdive 内部可操作目标。

## M2：原版数据接入

- 将已解析的环境几何按关卡编号整理成可加载场景。
- 继续从 PPSSPP 实时战斗帧恢复角色顶点、骨骼和材质绑定。
- 识别 SEDB 中的物件摆放和触发点。
- PSMF 仅作为本地参考；重制版先使用可替换的占位过场接口。

## M3：章节化与表现升级

- 关卡流式加载、章节选择、存档。
- 武器/技能/装备和难度。
- 过场播放器、字幕和画面比例适配。
- 4K 超采样、HDR 可选、手柄震动和宽屏镜头校正。

## 当前阻塞

角色骨骼、连续动作帧和原版 CLUT/材质绑定仍未完全恢复；当前已用真实战斗帧完成静态网格、UV 和一套可运行材质接入。M1 的战斗场景、碰撞、锁定射击和 Overdive 已可回归。
