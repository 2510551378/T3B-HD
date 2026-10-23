# Aya 与枪械原版相机恢复及 GPU 对照

12 个同 dump 射击输入样本的原 VIEW、PROJECTION 和 viewport 已按 PRIM 时刻恢复，覆盖 Aya 1,272 次 draw 和真实枪械 12 次 draw。独立 D3D11 实际运行生成了 24 份 depth OFF/ON 对照，以及 44,388 条 GPU vertex stream-output 记录。与原世界点经记录 VIEW／PROJECTION 的独立投影比较，最大误差为 **0.00003986104880482344 个 PSP 像素**。这是投影检查结果，不是最终图像误差。

[逐样本预览](../../t3b_unreal/Validation/ge_original_camera_runs/82e331c301ed4ecaa7832b97a9a673dd/PREVIEW.html) · [12 样本图](../../t3b_unreal/Validation/ge_original_camera_runs/82e331c301ed4ecaa7832b97a9a673dd/CONTACT_SHEET.png) · [独立原寄存器验收](../../t3b_unreal/Validation/ge_original_camera_runs/82e331c301ed4ecaa7832b97a9a673dd/independent_source_register_verification.json)

## 原数据与观察

输入仍为 `AYA_BONE_GE_ACTIONS/slot0_fire_verified/frame_0000..0011.ppdmp`。新 producer `tools/recover_original_ge_cameras.py` 先核对既有 body/weapon 输入 SHA，再独立推进 PPDMP command words；矩阵只接受实际出现的 uploads，不从未恢复的 INIT 矩阵猜值。每个目标 PRIM 的 view/projection payload 必须与旧冻结 body/weapon 数据相同，viewport 等寄存器必须与原 lighting input 的 256 项 payload 相同。

每帧全部 107 个目标 draw 使用相同相机、viewport、offset、region/scissor 和 depth range。矩阵在不同样本间变化；由 projection diagonal 推导的垂直 FOV 为约 40.00055°、35.20058°、29.20006°，随后九份为 28.00026°。这些是从矩阵求出的角度，没有恢复 authored camera 参数或原时钟。

实测 viewport scale `(240,-136,-32767.5)`、center `(2048,2048,32767.5)`、offset `(1808,1912)`，drawing/scissor 是完整 480×272，depth range 0..65535。GE depth clamp 实际为 **1**。第一版 producer 错误预设 clamp=0，因此拒绝数据；`recovery_v1/failure.json` 和失败源码保留。修正按实测值检查后的 `recovery_v2` 单独保存，没有覆盖失败证据。

## 坐标转换

原 GPU bundle 已将 source-world 点减固定 origin、按单位换算为厘米，并交换 Y/Z。新恢复保存这一步的逆变换 A、原 view V、projection P，以及 GE viewport 到 D3D NDC 的 remap R，输出 row-major F32 `A × V × P × R`。

原 screen 坐标按固定 PPSSPP v1.20.4 `TransformUnit.cpp` 的连续变换计算：`clip.xyz / clip.w × viewportScale + viewportCenter`，XY 再减 offset。D3D NDC 的 X/Y 按 480×272 映射，Z 则保留 source depth / 65535 的 reversed-Z 方向。没有把非完全正交的原 VIEW 强制改成 FTransform，没有用估计 FOV 重新生成 projection。

`recovery_v2/cameras.json` 保存所有原 payload、逐 PRIM 位置、registers、衍生矩阵及 unknown timing；`original_camera_matrices.bin` 是供本轮 renderer 读取的 **T3BCAM1 导出格式，不是 PSP 原生格式**。它与既有几何 bundle 按 sample identity 配对，不混入旧 60 帧 CPU socket timeline。

## 实际 GPU 与独立验证

运行 `82e331c301ed4ecaa7832b97a9a673dd` 的自有无窗口进程 PID 81488 正常 exit0，GPU 为 RTX 2080 Ti。使用当前项目 `T3BGEOrdered.usf` 的 MainVS/MainPS 主体：仅移除未使用的 Engine Platform include 并内联共享 ush；这不是 UE shader compiler。位置、UV、原 Gouraud colors、两张原 RGBA atlas 与逐 draw 顺序都来自已验证 bundle。

新增 `ge_original_camera_reference.cpp` 复用已有 native GPU 状态及读回代码。`ge_depth_reference.cpp` 新增显式 opt-in world shader／80byte constants 分支，旧默认32byte calibration 分支不变。actual VS DXBC 同时用于 stream output，真实 clip position、UV、颜色经 staging Map 读回；图像、owner、D32 depth 也从真实 GPU targets 读回。

独立 auditor 逐 draw 核对 input byte hash、源 world→厘米/XZY 的 F32 结果、原 camera payload，并从冻结原 PRIM 的寄存器二进制重新解码 viewport/offset，避免把 producer 的衍生字段当独立参考。44,388 条实际 GPU 记录的 UV/color bits 全部保留；合成矩阵的浮点计算在 dot-product 舍入界内。原点→原 camera→screen 与 GPU 的最大偏差如上，低于预先采用的 0.01 PSP pixel 投影检查阈值。

所有选定源顶点 clip W 为正、Z 严格位于近远平面内，source normalized depth 范围约 0.16638..0.25176。相同三角形内部也位于该区间，因此本批数据中打开 depth clamp 不会改变近远裁剪；这不支持对全场景关闭 depth clamp。

12 组 OFF/ON 的 union coverage 完全相同，累计 8,398 个 RGB 像素、7,684 个最后 draw owner 改变。sample6/7 的枪械最后 owner 为零，仍提交原 243 顶点及原 draw，没有强制透体显示。Owner 只说明最后通过的 draw，不能充当全部 alpha 贡献、枪口标记或原最终 framebuffer 的可见性证明。

root 已实际看过联系表。sample0 的枪身和全身可见；后续原机位出现瞄准和转向、腿部越过画面下沿，没有重新居中修饰构图。全部图片保持原 480×272，预览只是放大显示，未称高清材质或完整场景完成。

## 回归与保护

修改 native harness 后重新实际运行旧校准模式 `a6b4f9f1e3784ccd9d717ac96588cd2f`，PID85156 exit0，独立52采集检查通过。相对旧 `6bb0e3db0bcd40cb98ba9f66aceae654`，156 份 RGBA／owner／depth 原始 GPU buffer 全部逐 byte 相同；`optional_world_mode_regression.json` 保留结果。

新 camera run 的 `protection.json` 确认184个旧 package、原ISO／slot0存档／PPSSPP INI 全部hash不变；11份既有UE runtime/shader/module源文件也不变。没有 UE/PPSSPP 启动、桌面自动操作或系统下载／安装。`audit_identity.json` 保留当前producer源码、官方source URL/SHA和原auditor身份；后续加强viewport独立寄存器检查的auditor与报告另存，不改旧验收记录。

## 剩余工作

本轮只把原采样相机接入独立native 3D参考。正式 UE ViewExtension、实际 UE 相机传参与主深度仍未运行验证，M1 没有因此完成。下一步需将同一原机位用于UE采集对照，验证SceneCapture的自定义projection与实际VIEW组合；C++正式UBT仍待工具链安装答复。

原PSP固定点coverage、D16 depth量化、fog、完整场景、最终输出色彩、连续动作时钟、命名右手socket／枪口、高清贴图和可玩战斗仍是独立未完成项。不得把本轮12份采样叫完整原动作时间轴。
