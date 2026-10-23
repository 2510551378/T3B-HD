# UE GE shader 主体的投影与曝光 GPU 检查

本轮直接编译并运行当前 `T3BGEOrdered.usf` 的 `MainVS/MainPS` 主体。独立 D3D11 硬件进程 PID 17696 在 NVIDIA GeForce RTX 2080 Ti（FL11.0）正常退出；三组矩阵、15 条 VS 输出记录及 1,280 个像素的独立检查全部通过。**这不是 UE module、ShaderCompileWorker 或 RDG 的实际验收。**

证据目录：`../../t3b_unreal/Validation/ge_world_shader_probe_runs/60d238a224c944c5a7138a0134590949/`。

## 实际执行的代码

- 新 `Tools/ge_world_shader_probe.cpp` 创建自己持有的无窗口 D3D11 hardware device，没有借用或修改 UE device。
- `run_ge_world_shader_probe.py` 冻结当前 usf、共享 `T3BGECommon.ush` 和 native probe 源码。只移除 `/Engine/Public/Platform.ush` include（当前主体不使用其中符号），并内联共享 ush；没有替换 UE 头文件或更改函数主体。
- 原入口 `MainVS/MainPS` 由实际 `D3DCompile` 编译为 SM5 DXBC；编译产物、源哈希、g++ 命令、实际 PID、进程退出码和 stderr 均保存。
- `verify_ge_world_shader_probe.py` 独立检查冻结源码与展开关系、实际进程身份、输入 fixture、矩阵与输出、HDR 输出和 discard。`audit_identity.json` 保存当前 producer、runner、auditor、报告与 DXBC 身份。

## 投影检查

使用 `ATTRIBUTE0/1/2` 的实际输入 layout 和真实 vertex shader。通过 D3D11 stream output 读回 clip position、UV 和颜色，避免从渲染图片倒推矩阵。五个独立固定输入点分别测试正 Y、负 Y 校准矩阵，以及含平移、非对称系数和非恒定 W 的矩阵。

Reflection 确认 `WorldToClip` 是 row-major matrix，offset 0、size 64；`ScenePreExposure` offset 64、`DrawId` offset 68。上传常量结构 80 bytes。独立参考使用 row-vector × matrix，在 float64 中求值，并按四项 float32 dot product 的绝对乘积和给出舍入上界。

正负 Y 的最大误差均为 `4.936009645462036e-08`，低于对应上界 `2.19698300885085e-06`；非对称矩阵误差为零。若使用转置矩阵，三组最大误差分别约 452.61、452.61、1901.94，因此 fixture 能区分行列方向。全部 UV/color 原 F32 bits 保留。

这里的矩阵是可独立计算的合成控制，并没有增加原游戏相机或动作采集。UE `FViewMatrices` 到 shader 的实际参数绑定、相机 API、viewport、large-world precision、裁剪与 RDG 仍须在 UE 中验证。

## 曝光及 discard 检查

真实 MainPS 输出到 `R32G32B32A32_FLOAT` 和 `R32_UINT` 两个 MRT，进行 staging Map 读回。本检查关闭 blending/depth 并使用固定单 texel float atlas，单独测量 shader 输出；不替代原版 alpha blend/depth 的 52 采集检查。

已知 texture RGBA `(0.25,0.5,0.75,0.5)` 与 primary `(0.5,0.25,0.75,0.5)`，先得到 saturate(rgb×2) 的 `(0.25,0.25,1)`，alpha 为 0.25。曝光为 0.25、1、2、8 时，每档 256 个像素都精确符合预期；曝光 8 的 RGB `(2,2,8)` 保留超过 1 的 HDR 值，alpha 没有随曝光改变。Owner 全部精确等于 `0x12345`。

第五组将 primary alpha 设为零，256 个像素的两个 MRT 都保持 clear 值，确认 discard 同时阻止颜色和 owner 写入。全部五组共 1,280 个像素检查逐 F32/uint 精确一致。该控制不覆盖原贴图过滤、SRGB、UE scene blending、auto exposure、tonemapping 或完整输出色彩。

## 结果与下一步

`independent_verification.json` 明确保留 `UE_module_built=false`、`UE_shader_compiler_used=false`、`UE_pass_executed=false`。原 `implementation_status.json` 是先前源代码实施记录，保持不改；本轮新增结果不能把其缺失的 UE 验收变成通过。

`protection.json` 再次确认原 ISO、slot0 存档和 PPSSPP INI 三文件 SHA 相同；184 个旧 UE package 全部相同，没有新增或删除 package。没有启动 UE/PPSSPP、操作桌面、下载或安装系统组件。UE runtime 源码与当前 shader 没有改动，新增的只是 probe、auditor 与证据。

下一步仍是获得既有 MSVC/Windows SDK 安装问题的答复、实际 UBT 编译，再在 UE 中执行已准备的 48 图采集与独立验收。正式 M1、动作时序、手部/枪口语义与高清资产仍未完成。
