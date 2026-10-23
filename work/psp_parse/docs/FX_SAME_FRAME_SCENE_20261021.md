# 原版颜色特效与同帧 Aya／枪械／异形／街景组合

此前颜色 core 只在黑色背景上验证。本阶段把同 3 份 CPU→GE 关联记录里的 Aya、原枪、已识别异形与街景重新恢复，生产颜色／palette／顶点改写流程在实际场景中执行，已核对原顺序、原矩阵、CLUT、fog、混合和深度遮挡。

[实际场景与关闭特效对照](../../t3b_unreal/Validation/fx_scene_gpu_runs/3765b564f94b4d3f904b06290044d764/PREVIEW.html) · [GPU 独立检查](../../t3b_unreal/Validation/fx_scene_gpu_runs/3765b564f94b4d3f904b06290044d764/independent_verification.json) · [来源与保护记录](../out/FX_SAME_FRAME_SCENE_20261021/checkpoint.json)

## 原输入与角色恢复

输入来自 `FX_VERTEX_COLOR_GE_20261021/color6_GE16_v1/concurrent_GE_0000..0002.ppdmp`。未启动新 PPSSPP 或拼接其他帧的姿态。根据已确认的完整 vertex SHA，在每份记录找到 Aya 106 个 packet、原枪 1 个 draw、已识别异形 28 个 packet；3 份共 405 draw／16,497 顶点。逐 draw 重新导出原有效 GE BONE／WORLD、寄存器、position、normal、weights 和 UV。

现有生产 `T3BGELighting` 实际重新编译执行，所有 transform／normal／primary／secondary bytes 与固定 PPSSPP v1.20.4 software reference 相同，mismatch 为 0。新独立检查再从原 PPDMP 核对上述所有输入 bytes，避免把旧捕获的角色结果当作新帧。此处光照仍是 software model 重建，不是已采到的原硬件最终颜色。

街景保留本记录全部符合既有已证照明／三角列表契约的 VTYPE11f draw（141／137／131），另加入每帧 8 个已完成 CPU 颜色关联的原特效 draw。合并共 838 draw、109,299 GPU 顶点、79 个原 CLUT RGBA atlas。各类均在最终 draw-owner buffer 有实际可见像素。

角色按各 draw 的原世界 bounds 取局部 origin，减少大坐标与 VIEW 抵消；原矩阵及 GPU 投影仍独立核对。未改变相机或拟合位置。最大原画面投影误差为 0.000320 PSP pixel，小于原定 0.01 阈值。特效直接保留原 local position、原 WORLD／VIEW／PROJECTION 与 UV，仅应用原 scale／offset 一次。

## 实际 GPU 与干预

最终运行 `3765b564f94b4d3f904b06290044d764`，owned PID 82024 自然退出 0，RTX 2080 Ti／D3D11。现有 source-state renderer 与 shader 保持，两个 adapter 仅重命名旧 executable entry。原 GE 直接输入与当前生产颜色 core 的全部 VS 输出及整帧 RGBA／owner／depth-stencil 均逐 byte 相同。

每帧实际运行 7 种组合，共 21 捕获：原 GE 输入、生产颜色流程、改写前颜色、关闭选定特效、孤立选定特效、原 draw 顺序中特效之前、特效之后。改写前颜色在相同当前矩阵／UV 下与关闭特效结果全部 bytes 相同；这不代表上一完整游戏帧。

| 原记录 | 孤立特效覆盖 | 场景中特效覆盖 | 被原场景深度拒绝 | RGB 改变 pixels |
|---|---:|---:|---:|---:|
| 0 | 1711 | 1456 | 255 | 1172 |
| 1 | 2056 | 1781 | 275 | 1413 |
| 2 | 2234 | 1827 | 407 | 1424 |

独立检查对减少覆盖的全部 937 个 pixel，读取孤立特效最后存活 draw，利用实际 VS clip 输出、pixel center 和对应三角形的 screen barycentric 插值得到特效 Z，再比较特效之前的实际 D24 主深度；全部违反原 GEQUAL 条件。没有仅凭图片看起来被挡住就判断遮挡成立。

特效前后 prefix 的 depth／stencil bytes 相同；完整场景关闭特效前后的 depth／stencil 也相同。RGB 差异仅在最终实际存活特效 owner 覆盖内。blend 与 depth-stencil 继续由每 draw 的实际 D3D state getter 核对。

已实际查看 3 帧完整 PNG：Aya、原枪、原异形、街道／警车／橱窗与橙黄色特效同帧存在。没有将这些画面称为高清美术完成或精确枪口语义恢复。

## 当前范围与下一步

这是 native D3D11 场景子集。其他未纳入条带 FX、矩形 sprites、HUD 和 framebuffer passes 仍明确排除；未声称完整原游戏 framebuffer、PSP 固定点／D16 栅格像素一致。场景遮挡已在当前 D24S8 reference 中验证，两个颜色输入路径共享 renderer。

正式 UE C++ module／默认 M1 尚未接入本阶段数据。MSVC／SDK 的最近安装在 Windows 提权阶段取消，本轮没有重试 UAC；没有启动 UE 或改已有资源包。原 ISO、用户 slot0、INI 与 185 个既有 UE 包逐文件 SHA 保持一致。完整 authored 动作时间、武器／枪口命名、敌人 AI、原碰撞、伤害／受击／倒地与高清化继续待完成。

下一步应把已验证的动态颜色输入接入正式 UE replay pass，或推进共享属性与时钟／生命周期恢复；不再重复这个同帧子集的 native equivalence 检查作为新进展。正式 UE 编译依赖仍需本机提权安装成功，届时必须实际构建并运行，不能以本报告代替。
