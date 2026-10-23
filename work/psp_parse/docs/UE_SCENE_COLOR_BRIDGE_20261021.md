# UE 工程中的逐 draw 场景与原颜色 core 桥接

上一阶段的原矩阵、CLUT、颜色和遮挡只由 Tools 内的 native harness 消费。本阶段新增 UE module 内可复用的场景读取／颜色求值 core，并接入新的 UE actor、RDG pass 与共享 pixel shader 源码。core 和 shader 数值已实际独立执行；UE actor／RDG／RHI 本身尚未正式构建或运行。

[实际 native core／共享 shader 预览](../../t3b_unreal/Validation/scene_color_bridge_runs/e388cd172e374cc6a4c704aec17625ca/PREVIEW.html) · [独立验证](../../t3b_unreal/Validation/scene_color_bridge_runs/e388cd172e374cc6a4c704aec17625ca/independent_verification.json) · [待执行 UE 校准参数](../../t3b_unreal/Validation/ue_source_scene_calibration_plan_20261021.json) · [源码快照与原文件保护](../out/UE_SCENE_COLOR_BRIDGE_20261021/checkpoint.json)

## 数据与职责

`Source/T3BRemake/Public/T3BGEScene.h`／`Private/T3BGEScene.cpp`：

- 读取已验证的 `T3BSFC1` scene 和 `T3BPCG1` color bindings，保留任意已支持 atlas、draw 顺序、各 draw local→clip、fog、CLUT 引用及 raster flags。
- 严格限制文件／数组范围、有限 float、UNORM color、支持的 blend／stencil 契约和原始顶点颜色引用；拒绝未支持的状态。
- `EvaluateSceneFrame` 在每次选取 sample 时执行现有生产 source×parent RGBA、mode、palette、原顶点 patch 和 effect geometry decoder。不是把预先改好颜色的 GE buffer 当生产颜色输入。
- 对应 draw 必须匹配原矩阵／UV／顶点／状态及实际 CLUT texture。整个 frame 求值成功后才返回，失败不会留下部分改写的 scene。

数据仍是 3 个原记录 sample、79 atlas、838 draw、109,299 GPU 顶点；其中 24 个选定特效 draw 重新执行颜色流程。输入身份同上一阶段，未生成原版新采样时刻或 authored clip。

## UE 源码接线

新增 `AT3BGESceneReplayActor`，提供 `LoadSourceScene` 与 `SetCapturedSample`。载入前核验全部 frame，创建原 RGBA transient Texture2D，并保留 texture RHI 资源。默认不开启校准、不自动播放、不移动既有 M1，也没有用展示 fps 伪造原版时钟。

新增 `FT3BGESceneViewExtension`：以逐 draw 原矩阵、79 atlas、wrap／clamp、fog、alpha test、RGB double、source alpha／double alpha／additive blend、cull、depth clip 和已支持 stencil 契约建立 RDG／RHI 提交。单 sample desktop view；MSAA／stereo 未支持。

这是明确的 **source-camera calibration** 入口。它直接绘制真实 3D 顶点，使用独立 source depth／stencil 并替换校准 color view；原 clip depth 不能冒充另一 PC 相机的 gameplay depth，因此不写入 UE 现有相机主深度。Actor transform 非 identity 会拒绝提交。新的 PC 相机／场景交互仍需后续恢复统一世界变换并实际验证。

新增 `T3BGEScene.usf` 与 `T3BGESceneCommon.ush`。UE shader 使用后者的原颜色／fog／alpha 算术；primary color 和 fog 使用同 native reference 的 noperspective 插值，UV 保持 perspective。UE pre-exposure 在共享算术后单独应用，曝光／tonemap／目标格式的实际结果仍待 UE 运行检查。

旧 `AT3BGEReplayActor`／两 atlas pass／旧数据格式未改。新入口是独立显式校准路径，未切换默认 M1。

## 实际执行与失败留档

`ge_scene_probe.cpp` 实际编译上述生产 core，载入原 scene／bindings，重新求值所有 3 帧，再写回 source transport。完整输出与原 scene bundle 逐 byte 相同，覆盖 838 draw 和全部 24 color bindings。

8 个错误输入被实际拒绝且未写出部分结果：scene 截断／尾部多余 bytes、binding 截断、不支持 flags、非有限 position、错误 effect projection、错误 source RGBA、错误 effect CLUT texture。

`ge_scene_runtime_gpu.cpp` 使用相同生产读取／求值函数，读取真实原输入，而后提交 native D3D11。当前 UE pixel helper 的原文本被原样内联到测试 wrapper；没有改写公式。最终 owned run `e388cd172e374cc6a4c704aec17625ca`／PID 98980 自然退出 0，RTX 2080 Ti：3 次实际 GPU 捕获，79 atlas staging readback、109,299 VS 输出及 3 帧 RGBA／owner／depth-stencil，全部逐 byte 同上一阶段已验证的同帧原 GE 场景。已实际查看其中记录 2 的 PNG，另外两帧由 byte equality 覆盖。

首次 core 编译因缺少显式 Registers header 和 `-Werror` indentation 失败，旧源码保存在 `failed_build_v1`，修正后实际通过。首次 GPU run `4dba7f82c3a249f096515c861ceafa9d` 的 loader／8 个拒绝检查已通过，但旧 D3DCompile adapter 没有 include handler，shader 编译失败（PID 99276 exit1）；改为内联保留的原 helper 文本，新 run 通过。失败运行和日志均保留，没有把失败报告改成通过。

## 仍需完成

正式 UE C++／UHT／shader build 尚未运行；最近 MSVC／SDK 安装在 Windows UAC 阶段取消，本轮没有再次提权。未以 native 成功替代 UE actor load、RDG 生命周期、RHI pipeline 和 UE 最终 GPU 读回。已保存具体 class、bundle 路径／SHA、sample 和后续验收项，工具链成功后可按该参数运行。

当前仍不具备完整 authored 动作时钟、新 PC 相机、受击／倒地、敌人 AI、伤害／原碰撞与高清美术；其他 FX、sprites、HUD／FBO 也尚未纳入本 3 帧场景。完整重制目标保持 active。

原 ISO、slot0、INI 和 185 个既有 UE packages 的 SHA 全部保持一致；本轮未启动 PPSSPP／UE，也未改既有 Content 包。当前 23 个工具／生产／UE 接线源快照已冻结。

下一步应实际构建／运行 UE 接线（需工具链），或恢复共享属性 type23／24、type6 RNG、真实时间与生命周期。继续重复这 3 帧 native byte equality 不再算新的接入进展。
