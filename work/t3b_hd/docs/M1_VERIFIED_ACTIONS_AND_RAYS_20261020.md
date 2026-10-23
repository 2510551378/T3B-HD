# 原版动作、武器同步与实际枪口 ray

本轮完成原版短段 aim/fire 接入与 M1 真实枪口射线检测。完整高清重制仍在进行；现有敌人是 guard.pmf 代理，场景碰撞是 M1 简化竖直柱，材质仍是原版分辨率。

## 可复核的原版数据

- `../psp_parse/out/AYA_BONE_GE_ACTIONS/slot0_aim_verified/`：R 输入得到 12 个 source/GE 配对样本。
- `slot0_fire_verified/`：R+square 输入得到 12 个配对样本。两个采集各有 1272 个 Aya draw、3084 项有效 source 引用完全匹配。原生窗口图像分别保存在 `slot0_aim_visual_hold/observed_aim_window.jpg` 与 `slot0_fire_verified/observed_fire_window.jpg`：瞄准图弹药24，射击图弹药15且敌人掉血。
- 游戏操作依据：Square Enix 日文官方说明 R=lock-on、square=shot：<https://blog.jp.square-enix.com/3rd_birthday/2010/09/>。
- 近距离战斗采样中间存在明显方向变化，不能把整段标成稳定射击。保留原始文件，仅选择 aim 原始9..11、fire 原始10..11，`manifest_steady.json` 记录原始索引、ticks、SHA与选择原因。
- 运行时 `assets/models/aya_source_clips.txt` 绑定3采样aim、2采样fire。body与weapon来自同一原始capture，time/floor/units相同；44骨骼、106packet、3456顶点与真实243顶点枪械保持一致。
- 所有106packet共享已确认的原版256² CLUT8 Aya atlas；枪械使用独立64²纹理。新动作首尾共424draw材质再次一致，原版alpha保留。未声称已高清化。

## Runtime 与射线

`src/aya_source_skin.h` 逐clip严格验证几何、权重、父级、材料和时间轴；整份manifest通过后才启用。人物和枪械共用动作时间，缺少move则回到reference；采样末尾clamp，不伪造循环。按住SPACE可持续开火。

`src/combat_ray.h` 使用归一化方向做 ray–vertical capsule 解析相交。M1子弹只从实际枪管端几何候选起点、沿当前原版枪械矩阵方向发出；已移除 angle_target OR / player-origin LOS OR 命中回退。R选择锁定目标仍可用视锥和LOS，但不参与子弹命中。沿同一条ray比较目标与墙体的最早交点，tracer绘制到真实交点或射程终点。

当前 capsule 是测量 guard.pmf 的适配数据：半径.30、轴端Y=.30..1.45、localZ=.20随敌人yaw旋转。它不是原版Twisted hitbox。场景盒按无限竖直柱解释，不是已恢复的原版3D collision。

## 验证结果

- 构建 `mingw32-make -f Makefile.win` 无警告。
- `gcc -Wall -Wextra -Werror -std=c11 tools/test_combat_ray.c -o build/test_combat_ray.exe -lm`：41项几何检查通过。
- `t3b_hd.exe --test-combat-rays`：12项实际场景射线检查通过，包含侧向/高处/背向miss、墙体先命中、枪口在墙内、边界、目标转身及非法方向。
- 正常 `--test`：四次射线命中、敌人死亡、collision/LOS/Overdive进出通过。但此时枪口在近距离目标体积内，不能单凭该测试证明远距离方向正确。
- `t3b_hd.exe assets\scene\nyc_block_uv.obj --test-ranged`：敌人固定在2.55单位外，持续开火四次命中，枪口后命中距离1.13388、1.15470、1.15470、1.15470。前一枪使用fire首采样，后续使用.26722s末采样。独立Python复算端点到capsule表面误差4.85e-8；不扩大capsule、不修正枪械方向。
- 人物/枪械同clock同步361帧，0同步错误，0动作回退。`../psp_parse/out/AYA_ACTION_CLIP_RUNTIME_VERIFICATION.json` 验证实际C数值：Aya最大误差1.57e-5、weapon最大8.10e-6原始单位。
- `../psp_parse/out/AYA_M1_RANGED_RAY_VERIFICATION.json` 记录射线CSV身份与独立几何复算。

## 新增约30Hz source采集

`trace_aya_action_verified.js` / `capture_bone_pose_action.ps1 -DenseSource` 在bone43完成点一次 `memory.read` 读取44×0x130整块source记录，并以scalar read交叉检查边界数据。只在首尾导出GE，减少采样空洞；每帧原始binary保留，未改游戏RAM或保存文件。

`slot0_fire_dense` 与 `slot0_aim_dense` 各60样本，覆盖约2.136秒；中位间隔分别33.344、33.365ms。每段首个GE导出造成约200ms间隔，之后58个间隔约33ms，时间戳未压平。

- 两段共5280次parent pointer检查通过。
- 每段首尾106packet/514项Aya有效influence均完全匹配原始GE。通用audit还有其他角色/武器的108项未匹配，不能误算成Aya失败；dense integrity按原版106packet geometry SHA筛选。
- fire 31254/31680、aim 31402/31680个 matrix40*matrix80 分量在float24位级相同。近零抵消时单纯bit distance可达16640步，但最大值仅8.58e-6对6.17e-6；全部数值处于F32点积舍入加float24截断界内。原始误差和界比例完整写入 `AYA_SLOT0_{FIRE,AIM}_DENSE_INTEGRITY.json`。
- 这只是持键战斗source序列；可能混入受击/过渡，尚无每帧weapon WORLD配对，未接入当前runtime clips，不能声称完整后坐循环已恢复。

## 下一步

定位真实枪械的逐帧WORLD数据来源，与新dense source序列同一暂停点采集；对R-only与R+square序列识别抬枪、开火、回正、敌人接触段，再替换当前短片段。继续恢复移动/受击/倒地、原版Twisted与场景资源、原版命中数据，最后推进高清材质与完整游戏流程。

用户第一即时存档与备份SHA256仍均为 `32f7fe3d3d830079d7b4499066eb488562e33ce945765eea8461fc1fca18dc39`。
