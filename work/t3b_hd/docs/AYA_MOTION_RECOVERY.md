# Aya 连续动作恢复

## 已恢复的证据

`ULJM05798_0001`–`0009.ppdmp` 共提供 9 个战斗帧转储。每帧的 weighted vertex blocks 已按真实 `vtype` 解码并保留 UV；不同帧的 draw 可见性不同，因此顶点数量不是固定拓扑：

这些转储来自同一段战斗状态的多次记录，不能直接当作连续时间轴；它们主要用于恢复 draw 覆盖范围、武器局部坐标和稳定的骨骼 pivot。

| 帧 | 顶点 | 三角形 | 说明 |
|---|---:|---:|---|
| 0001 | 2,645 | 833 | 完整姿态片段 |
| 0002 | 1,610 | 502 | 部分 draw 可见 |
| 0003 | 1,610 | 502 | 部分 draw 可见 |
| 0004 | 2,560 | 806 | 完整姿态片段 |
| 0005 | 2,560 | 806 | 完整姿态片段 |
| 0006 | 2,399 | 757 | 部分 draw 可见 |
| 0007 | 1,971 | 623 | 部分 draw 可见 |
| 0008 | 2,013 | 635 | 部分 draw 可见 |
| 0009 | 2,650 | 834 | 当前 M1 基准姿态 |

## 运行时方案

帧转储保存了已经 skin 后的顶点，但没有保存完整的骨骼矩阵。工程因此使用 `assets/models/aya_skeleton.rig` 中的 8 个重建骨骼 pivot 做连续 CPU skinning：头部、脊柱、左右手臂、左右腿和 pelvis 会随 idle、aim、recoil 时间连续变化；原始 UV 和 CLUT 解码贴图保持不变。

这种方案让 M1 具备连续动作和稳定拓扑，同时保留后续把真实骨骼矩阵替换进来的接口。

另外，PPSSPP GE debugger 捕获的 6 组 3×4 矩阵已保存为 `assets/models/aya_ge_matrices.json`，运行时以 0.35 权重叠加到重建 pivot 上；这组矩阵的原始记录保存在 `work/psp_parse/raw/ge_matrices.py`。随后通过 WebSocket `gpu.record.dump` 在同一战斗存档中保持 `square` 连续抓取 24 帧，解析每个 weighted draw 后的 `BONE` float24 commands。由于 GE slot 是 draw-local palette，`extract_aya_hierarchy_timeline.py` 将它们固定映射为 11 个层级通道：脊柱下段/上段、头部、左右上臂/前臂/手、左右腿，输出 `assets/models/aya_ge_hierarchy_timeline.json/.csv`。另外补采 `square`、`ltrigger+square`、`rtrigger+square`、`ltrigger+rtrigger+square` 四种输入姿态共 40 帧，输出 `work/psp_parse/out/AYA_POSE_VARIANT_ERROR.md`。运行时在 `shoot_t>0` 时按 30 Hz 插值；右手矩阵还会作用到武器挂点、枪口位置和枪口方向。

EBOOT/PRX 的静态路径也已从 PPSSPP 解密 RAM 镜像恢复：去掉 `ram.bin` 的 `0x48` 字节 loader/header 后，`matrix_context_wrapper (0x08bfff6c)` 在 `0x08bfff84` 调用 `dl_write_matrix (0x08c01088)`，通过 `0x3a/0x3c/0x3e/0x40` command family 写 packed float24 矩阵；相邻的 `z_un_08bfff98 (0x08bfff98)` 是通用 GE command emitter。80 次 live breakpoint sample 覆盖 26 个实际矩阵 caller，报告见 `work/psp_parse/out/AYA_MATRIX_PAUSED_CALL_MAP.md`。这些 caller 证明了原版矩阵/GE 上传机制，但匿名 `z_un_*` 调用点不能单独证明某个骨骼名称；语义仍由 weighted draw 与多姿态运行时数据交叉确定。详见 `work/psp_parse/out/AYA_EBOOT_MATRIX_ANALYSIS.md`。

对 44 个通用 command-emitter caller 又分别采集了 `square`、两种 trigger 瞄准和左右 strafe 射击 trace。`0x8b5e3a8` 的 0x10-byte 逐 draw 记录路径在 `rtrigger+square` 与 strafe 状态显著增加，但这只是动作相关的渲染状态证据，不能直接改名为某一根骨骼；见 `work/psp_parse/out/AYA_MATRIX_ACTION_TRACE.md`。

进一步在 `0x8b5e3a8` 的 `jal` 前暂停，读取 `s3` record 和全部相关寄存器。六组动作共 60 samples 均显示 `a1=0x102` selector、`s3+0=4`、`s3+8=7`，因此该路径是逐 draw GE command 状态，不是可直接读取的右手骨骼矩阵。右手、weapon mount 和 muzzle 仍以 `arm_right_hand` GE channel 驱动；新增 48 帧动作姿态的误差见 `work/psp_parse/out/AYA_ACTION_POSE_ERROR.md`，逐 draw 记录见 `work/psp_parse/out/AYA_DYNAMIC_DRAW_SUMMARY.md`。

同一运行时的 12 个 GE dump 已与 `0x8b5e3a8` 日志区间逐帧对齐：`arm_right_hand` 始终为 draw `1037`、palette slot `12`，矩阵随帧变化，而 record signature 不变。对齐报告为 `work/psp_parse/out/AYA_DRAW_RECORD_GE_ALIGNMENT.md`；M1 保持从该 GE channel 计算 weapon mount 和 muzzle。

## 真正的 GE BONE 写入路径

从修正后的解密 EBOOT/PRX（`ram.bin` 偏移 `0x804048`，去掉 `0x48` loader/header）继续向下追踪后，已把通用 command emitter 与真实 BONE writer 分开：

- `0x08b4f77c` 位于 `z_un_08b4f618` 的 per-bone record loop，构造 `0x2A` bone-slot command；
- `0x08b52330` 读取 `object+0x3c4` 的 `0x130`-stride record，矩阵输入为 `+0x40/+0x80`；`0x08b5251c` 将计算结果写入 `record+0xc0` 的 `0x2B` float24 payload，`0x08b52554` 是后续 flag/clear 分支；
- `0x08b46e1c` 是逐对象/逐 draw caller，将对象指针传入 `0x08b4f618`；`0x08b4f6e8` 是同一 BONE build 内调用 `0x08b5230c` 的矩阵 build caller，最终在 `0x08b5251c` 完成 record payload；
- 暂停式 runtime trace 在 `0x08b52554` 看到 `boneCount=44` 的 Aya 源对象和 `boneCount=3` 的武器/附属对象候选，见 `work/psp_parse/out/AYA_BONE_PAYLOAD_PAUSED.json`；汇总见 `work/psp_parse/out/AYA_TRUE_BONE_WRITER_ANALYSIS.md`。

同帧 GE 对齐继续确认 Aya 右手使用 draw `1037`、palette slot `12`，M1 已把 weapon mount、grip、muzzle 和 muzzle direction 接在该 GE channel 上。`0x8b5e3a8` 的 selector `0x102` 记录保持为 command state，不再作为右手矩阵源。

这一步已经完成了该索引的直接解析：在 `0x08b5251c` 读取每个 record 的最终 `0x2B` payload，并与同一帧 draw `1037` / palette `12` 的 65-vertex GE 矩阵逐帧比较，24/24 帧都命中 44-bone Aya source record index `36`。生成的 `assets/models/aya_true_right_hand_timeline.csv` 保存 hand rotation、weapon mount 和 muzzle socket 矩阵；M1 在 `shoot_t>0` 时优先使用这条 source-record timeline，旧的 11-channel timeline 仍只负责其他骨骼通道。

## 武器校准

命令 1095 在 0001–0006、0009 中都出现同一局部网格。运行时使用 `grip=(0.090, 1.790, 0.130)`，`muzzle=(0.300, 1.795, 0.106)`，施加 `155°` 的局部 yaw correction 和 `mount correction=(+0.742355,+0.029960,-0.252845)`，使恢复的武器轴与 Aya 的锁定 forward 对齐。射线起点、遮挡检测和枪口火线都从这个 socket 计算；误差表见 `work/psp_parse/out/AYA_SOCKET_ERROR.md`。

11 通道与 socket 的稳定 draw/palette 对照表见 `work/psp_parse/out/AYA_SOCKET_BONE_MAPPING.md`；其中 `arm_right_hand` 是 weapon mount、grip、muzzle 和 muzzle direction 的统一驱动通道。

## 贴图方向修正

原始 PSP UV 已由 `extract_runtime_character.py` 解码到 0–1；BMP loader 同时完成了图像行序转换，因此渲染阶段不能再次做 `1-v` 翻转。M1 已改为直接使用 `glTexCoord2f(u,v)`，修复了脸部纹理跑到腿部、脸部发灰的问题。场景建筑遮挡属于独立的 collision/scene layout 问题。
