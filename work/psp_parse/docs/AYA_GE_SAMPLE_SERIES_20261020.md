# Aya：72 个原始 GE 样本的动态着色与实际 UE 回放

2026-10-20。目标是将已恢复的静态 GE 顶点光照扩展到实际采样序列，避免把某个姿态的灯光复制成整段原版动作。完整 M1／高清重制仍未完成。

## 原始数据与时间边界

现用 `slot0_fire_reverse120_world60/manifest_aligned.json` 的 60 个 CPU/source-bone 样本只有两份完整 GE dump；原校准明确对应 source samples 1、58。这不足以恢复其全部逐帧灯光。

本次改用已有、完整逐样本 GE 的两个独立采集：

| 原始采集 | GE 样本 | 原 manifest SHA-256 |
|---|---:|---|
| idle_long/manifest.json | 60 | a4774003b6a6a21c895f1b03029670af95f2b7dc30c029c97d60e2dd207a81f8 |
| slot0_fire_verified/manifest_runtime.json | 12 | 466c9c3a95b6d14cb7cbbee25936955b8459a0d325bc18e4dea0e04cb974875a |

每份 dump 均按完整 `VTYPE + vertex bytes` SHA 匹配原 106 个唯一 Aya packets，并检查 PRIM 的计数、顺序和三角形类型。没有按包大小、draw 区间或外形猜角色身份。

样本次序是已观察的 GE dump 顺序。原 CPU ticks 发生在后续异步 dump 之前，不能自动视为 GE 精确时间。预览均匀 30 fps 是展示选择；不称恢复了完整原动画片段，不将这两个组拼成同一连续动作，也不与旧 60 帧武器时间轴混绑。

## 逐 draw 恢复与材质

`tools/recover_aya_ge_sample_series.py` 重放 saved context、逐字 GE 命令及 WORLD/VIEW/PROJECTION/BONE 上传，保存 7,632 draws、248,832 顶点的完整计算输入。独立的已有材质迭代器和矩阵重放循环在每个目标 PRIM 的全部寄存器上相互核对。

全部原 VTYPE 都是非 through、无索引／morph／COLOR0，U16 weight/32768、S8 normal/128、S16 position/32768、U16 UV/32768。保留原权重和原顶点法线，不做归一化权重或替换为面法线。

每个 draw 重放原 CLUT 与纹理。完整原材质 identity 与已冻结 Aya material ID 一致：每组只有一个原材质；两组各有一个光照寄存器状态，总计两个状态。灯状态在组内相同并不意味着顶点颜色相同，原蒙皮位置和法线逐样本参与计算。

初版 `inputs_v1` 的材质 decode cache key 只含原纹理／CLUT RAM 和 render 参数，未覆盖所有 decoder 寄存器。修正为包含 TEXFORMAT、TEXSIZE、TEXBUFW、TEXMODE、CLUTFORMAT 及 known-CLUT mask 后，实际重新解析得到 `inputs_v2`。两版 binary、全部 draw/frame/lighting observations 逐字节／逐值相同。原 UE 运行继续保留其 v1 输入身份；独立审计显式核对 v2，并未重写旧证据。

正式解析输入为 `out/AYA_GE_SAMPLE_SERIES_20261020/inputs_v2/inputs.json`。`recovery_code_retention.json` 保留实际脚本及两个解析依赖的源码身份；这是解析完成后的留存，不冒称启动前冻结。

## Production reader 与独立软件参考

新增 UE 源目录中的 `Public/T3BGESeries.h` / `Private/T3BGESeries.cpp`：

- 读取 T3BLIT1 小端数据，检查边界、有限数、GE PRIM/VTYPE/weight contract 和样本间固定 packet geometry。
- `EvaluateSample` 调用 production `T3BGELighting`，返回原 WORLD 位置、加权世界法线、primary/secondary colors 与原 UV。
- 用样本 index 选择，不推断原时钟，不做矩阵插值，不添加骨骼名或武器 socket 映射。

`comparison_v1/comparison.json` 使用固定 PPSSPP v1.20.4 原 Lighting.cpp/Math3D.cpp 算术主体与 test-only state/header adapter，在 x64 SSE4 模型下运行。全部 248,832 顶点的变换 bits 和颜色 bytes 差异为零；不是原 GPU 或 PSP 硬件像素采样。

`runtime_v1/verification.json` 实际以 g++13.2、O2、SSE4、禁用 FP contraction、Wall/Wextra/Werror 编译 reader/kernel/probe。reader 重新加载全部 72 个样本，输出与上面的独立参考逐字节一致，UV bits 全部保留。8 个损坏输入案例实际拒绝：magic、draw count、slot count、NaN、负权重、跨样本 geometry 变化、截断及 trailing bytes。

这是 standalone production-core 编译与运行。正式 UE C++ module 尚未通过 UBT；当前正式 `T3BReplayWorld` 的默认 source-bone／武器绑定和旧 face shading 未被本次采样序列替换。

## 实际 UE 动态回放

`work/t3b_unreal/Validation/ge_sample_series_runs/30e6de5c441f4e55ba482b1c1f02d427/`：

- 实际 UE5.8.4 CL58902052，D3D11/SM5，日志确认 NVIDIA GeForce RTX2080Ti；PID37704 自然 exit0。
- commandlet 执行脚本在启动前冻结；不使用 NullRHI 生成 PNG，不保存或修改任何资产包。
- 一份实际 DynamicMeshComponent，初次追加原 3456 顶点／1152 面；后续逐样本更新位置、原法线和颜色。保持原 UV 与三角形顺序；未经过 StaticMesh/Nanite 简化。
- 保留已有测试过的单面、unlit、translucent、rgb*2 原纹理材质。DynamicMesh 明确 NoTransform vertex-color-space。
- 原 WORLD 位置减去各组首样本的固定原点，再用 canonical units 和 XZY 坐标变换转到 UEcm。没有逐帧居中抵消角色移动。实际 actor/component transform 均为 identity。
- 固定 +Y 正交相机、512×768、manual exposure0、bloom/motion blur0；每个 GE 样本各一张实际 PNG，另有两个 hidden controls。
- actual_component_samples.bin 来自该组件的 CPU mesh position/color/normal 查询，不是复制输入，不称 GPU vertex readback。

`Tools/verify_aya_ge_series.py` 不导入解析器或导出器，直接读取独立软件输出、原 UV、实际组件文件及 PNG：

| 核对 | 实测结果 |
|---|---|
| 72 样本／248,832 点 position F64 | 转换期望与实际组件 bits 全同；最大分量误差0cm |
| primary color F32／normal F32 | 实际组件 bits 全同 |
| 抽取的实际 indices／UV overlays | 原1152面完整保留，顺序／重复面 multiplicity／原F32 UV全同 |
| idle_long 的60张PNG | 58种不同像素图；两个相同样本不被误报为失败 |
| 射击输入组的12张PNG | 12种不同像素图 |
| 原有183个UE资产包 | 运行前后及进程退出后SHA均不变 |

实际看图：Aya 服装、后袋、靴子及姿态随样本显示，动态样本着色已接入。手臂仍可透过身体；这里没有枪械；相机是校准机位。PNG 有变化证明回放可见，不证明每个 GPU 顶点／像素与原版相同。

交互浏览：运行目录下 `PREVIEW.html` 可按组播放／逐样本查看，所有图均为实际 UE PNG。它是采样检查工具，不是可玩 M1。

## 剩余工作与原始文件保护

还需恢复原主深度写入／透明混合与排序、texture combine/output color/fog，完成同原版机位像素对照，建立精确 CPU↔GE 时序，再与真实枪械和原生 SkeletalMesh 动画／正式战斗串联。不能把这一组 GE replay 作为已校准的枪口或已完成高清资产。

本次没有启动 PPSSPP，没有系统安装或桌面自动化。`out/AYA_GE_SAMPLE_SERIES_20261020/source_protection.json` 在2026-10-20 14:57UTC重新完整哈希：ISO、slot0即时存档、ppsspp.ini均与原保护SHA相同，无运行中的采集进程。完整高清重制 goal 继续 active。
