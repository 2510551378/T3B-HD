# 原版采样相机接入实际 UE SceneCapture

本轮在实际 UE5.8.4／D3D11 中回放了12个同GE样本的Aya与枪械，并把原版采样相机用于SceneCapture。72个隔离彩色标记的GPU PNG中心与原相机投影比较，最大偏差 **0.5484361901722512个PSP像素**，通过1像素阈值；44,388个真实组件顶点的位置／颜色／法线bit核对通过。

[实际UE／native双栏预览](../../t3b_unreal/Validation/original_camera_ue_runs/5a76f5096f5c46be84c5d8f1260a1f29/PREVIEW.html) · [三栏深度对照](../../t3b_unreal/Validation/original_camera_ue_runs/5a76f5096f5c46be84c5d8f1260a1f29/NATIVE_UE_COMPARISON.png) · [独立验收](../../t3b_unreal/Validation/original_camera_ue_runs/5a76f5096f5c46be84c5d8f1260a1f29/independent_camera_verification.json)

这是原版机位在UE的实际验证，**不是新C++ GE深度pass通过，也不是完整材质／高清资产／M1完成**。

## 相机组合方式

本机 `SceneCaptureRendering.cpp` 从component world transform生成View，再追加UE的轴交换矩阵；`bUseCustomProjectionMatrix`使用所给projection。没有把原VIEW×PROJECTION直接当成UE projection，从而重复应用View。

新增 `Tools/ge_source_camera_capture.py`：从记录的原非完全正交VIEW求眼睛位置与方向，设置物理UE camera的近似正交朝向，再读取真实component world matrix。按实际UE View计算残差projection，使 `UEView × CustomProjection` 在齐次尺度归一化后保留原相机。没有把原VIEW的细小偏差丢弃为估计FOV。

该adapter同时用于12个样本，原camera fixture依然为上一轮 `AYA_ORIGINAL_GE_CAMERA_20261021/recovery_v2/cameras.json`，不补造动作时间。实际custom projection及component transform从UE property读回，auditor以NumPy重新组合，原matrix从保留F24 payload独立解码；没有直接采用producer的目标投影作参考。

`capture_weapon_ge_paired.py`与headless wrapper仅增加显式`--cameras`模式；旧固定正负Y校准仍为默认。源相机模式复用已保存的单面原材质，严格禁止该模式新建material package；480×272 render target，原body/weapon同dump配对，原位置／UV／颜色／逐组顺序保持。

## 实际GPU相机控制

每个样本从既有body顶点选6个分开的可见点，记录原body vertex index及真实component位置。在这些点放置面向相机的隔离彩色quad，用仅存在于 `/Engine/Transient` 的opaque/unlit vertex-color material渲染，正式角色在控制图中隐藏。

auditor检查标记位置确实等于原source变换及实际component读回，独立投影求预期像素位置，再从真实GPU导出的控制PNG按色相取中心。12×6=72项全部通过1PSP像素的raster中心阈值，最大约0.5484；这与上一轮native VS stream-output的约0.000040像素浮点投影误差是不同测量，不能混为同一精度指标。

没有读回UE FViewInfo或完整UE GPU vertex buffer。property组合检查属于CPU证据；GPU PNG标记单独证明实际SceneCapture确实采用正确机位。它不证明原场景遮挡、透明度、D16量化、完整PSP像素或色彩等价。

## 采集与仍存在的画面缺陷

真实run `5a76f5096f5c46be84c5d8f1260a1f29`，PID85340，自然exit0。12样本各body-only／weapon-only／combined共36图，加1空场控制与12标记控制，共49份frame PNG；另导出1份原weapon texture source PNG。

root已实际看过12样本联系表、sample0标记图和sample0/4/6/11三栏深度对照。机位、角色大小和画面裁切与native参考相符；UE sample4/6/7/11仍显示普通透明材质透体，背面出现脸或手臂。对照中native depth OFF出现相同类缺陷，native原深度ON改善。该证据支持继续推进已经实现但尚未实编的新按draw顺序blend＋主深度写入pass；没有称当前UE已修复。

原shader的独立FXC／native验证与本轮UE普通材质验证保持分开。当前运行的是无C++模块的content-only `T3BNativeProbe.uproject`，没有加载 `AT3BGEReplayActor`。正式M1默认world和资产绑定未更改。

## 失败记录与保护

三次producer失败均留档：

- `da3954abff44462a8cc79ba00e9fef50`：输入材质报告路径填错，补启动前文件存在检查后修正。
- `123b66ed6c904b95bff2e4242f8c5e65`：VertexColor expression真实输出名为空，`RGB`名连接失败；按本机MaterialExpressions.cpp修正。
- `189b0580af2c4b56bd50a0581b588ce6`：Python Quat缺少get_right_vector；改用已读取component matrix的轴。

首个auditor把hidden控制错误要求为逐byte零，实际图仅含中性0／1灰阶值；失败源码和JSON保留。本机PostProcessTonemap.usf包含量化dither分支，实际观察与其一致，但未逐项读回该shader参数。最终控制严格限定为0/1中性灰，没有用更宽容的颜色／材质等价阈值；所有几何bit和marker1像素阈值保持不变。

`source_protection.json`独立重查原ISO／slot0存档／PPSSPP INI与184个package，hash全部不变，无新旧package增加或删除。临时marker材质没有保存。`audit_identity.json`保存实际producer/helper/auditor和所查本机UE source身份。没有启动PPSSPP或进行桌面自动操作。

## 工具链安装状态变化

本轮用户明确回复“允许后台安装（推荐）”，此前MSVC／SDK问题已获授权，不再等待聊天许可。按既有方案下载Microsoft官方VS2022 Build Tools bootstrapper并验证：Authenticode Valid，签名Microsoft Corporation，file version17.14.37806.7，SHA256 `2a6aa7d94e38d457a4eb3930fc60056ecab06865b2eb925e5275b8473a017583`。

记录目录 `../../t3b_unreal/Validation/toolchain_install_runs/f041d28d9c114afbb23324f1d76b4c5a/`。保留原approved plan SHA、原参数、签名证据和安装脚本；目标 `C:\BuildTools\VS2022`，MSVC14.44及SDK22621，`--quiet --wait --norestart --nocache`。当前终端非管理员，启动脚本使用Windows RunAs请求用户系统提权，隐藏安装器窗口，保存真实handle／退出码后再验组件。

截至本记录，安装请求仍在提权阶段，尚无installer PID或组件安装成功证据；父PowerShell的exec session为31121（stage中的parent_pid89056）。不得把该状态写成正在下载组件或安装完成，不重启另一个安装器。用户已被询问是否看到系统提示，该诊断问题不是再次索要安装授权。后续应先重新检查同一session／真实process；只有确认终态后才能决定下一步。

官方CLI参数依据：[Microsoft安装参数说明](https://learn.microsoft.com/en-us/visualstudio/install/use-command-line-parameters-to-install-visual-studio?view=vs-2022)。工具链实际安装、cl/SDK文件发现、真正UBT构建与GE pass运行仍须分别验证。

### 后续真实终态

随后同一session31121返回exit1，Start-Process报告“操作已被用户取消”，父PID89056消失；这次提权请求已结束，安装器从未启动。terminal_status.json是最新状态，前段pending记录仅描述之前观察。未重复请求提权；保留既有诊断问题等待回复。聊天安装授权已收到，但不能代替Windows实际提权或组件安装证据。
