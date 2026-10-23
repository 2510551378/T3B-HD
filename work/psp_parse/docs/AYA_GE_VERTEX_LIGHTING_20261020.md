# Aya 原版顶点光照：计算恢复与真实 UE 静态校准

本阶段恢复的是原始采集姿态的 **GE 顶点变换和 Gouraud 光照模型**。输入来自三份既有原版 PPDMP，共318次Aya PRIM、10368个顶点；颜色是由这些输入重建的结果，未采到原 PSP 硬件的最终光照输出。完整可玩高清重制仍未完成。

## 记录与新核心

`tools/recover_aya_ge_lit_inputs.py` 逐条重放原 GE words，在每个真实目标 PRIM 核对完整VTYPE/几何SHA、材质快照、原WORLD和逐draw BONE palette。保留原U16权重/32768、S8法线/128、S16位置/32768，不归一化权重，不用面法线或临时真人骨架替代。只接受本次实际观察的无COLOR_0、无索引/无morph、directUV、原三角形路径；数据保存在 `out/AYA_GE_VERTEX_LIGHTING_20261020/inputs/{inputs.json,lighting_inputs.bin}`。

新的 `work/t3b_unreal/Source/T3BRemake/{Public/T3BGELighting.h,Private/T3BGELighting.cpp}` 提供独立CPU核心，使用原PSP世界单位：先按原权重合成矩阵，再变换位置和法线，经WORLD并归一化world normal；恢复directional/point灯、attenuation、ambient/diffuse/specular、颜色half-offset整数舍入与secondary输出。本次x64/SSE4软件参考的specular half-vector使用近似RSQRT，不能随意换成另一种normalize后仍声称逐byte一致。未实现的spot、输入COLOR_0、through mode等明确拒绝。

该核心已在UE源码目录中，但本机正式C++工程仍缺SDK，未通过UBT或逐帧UE调用。当前UE校准使用它预计算后导入的顶点颜色；不是宣称UE内的完整动态光照已实现。

## 独立参考与验证

固定PPSSPP v1.20.4原版 [Lighting.cpp](https://github.com/hrydgard/ppsspp/blob/v1.20.4/GPU/Software/Lighting.cpp)、[Math3D.cpp](https://github.com/hrydgard/ppsspp/blob/v1.20.4/GPU/Math3D.cpp)及原headers保存在reference目录。测试编译直接使用未修改的原Lighting/Math3D算术体，旁边的compat headers仅适配保留的register storage和无关framework设施；不是运行整套PPSSPP软件renderer。所有源、适配层、编译命令、编译器、executable SHA均记录。

`comparison_v2/comparison.json` 是当前核心的正式报告：g++13.2、C++17、-O2、-msse4.1、-ffp-contract=off，318draw/10368vertex的world position、world normal及primary/secondary颜色全部与该参考一致；变换bit mismatch=0，颜色byte mismatch=0。输出二进制逐byte相同。`comparison_v1` 保留此前同结果；v2补齐scope guard和完整适配层身份。

`synthetic_edges_v2/verification.json` 的13个明确合成边界覆盖正/负diffuse、零normal/方向/half vector、零/负specular exponent、secondary channel、点光零距离和负attenuation等。`native_scope_tests/verification.json` 另核8个不支持/坏输入拒绝条件。两者均不是额外原游戏观测。

这只能证明对选定的原始输入正确实现了固定软件模型，不能代替PSP硬件或PPSSPP硬件backend像素。三份姿态也不能成为全60帧、所有动作或其它关卡的固定灯光。

## UE真实图像与Nanite问题

`export_aya_lighting_snapshot.py` 从第一份原姿态构造white/ge_lit静态校准对。两份binary只在COLOR_0区域不同，几何/UV/原面顺序/材质一致。只减去共同world origin并按既有canonical units换算，不旋转角色；因此图名front/back实际表示±Y观察轴，不一定是角色相对正面。颜色校准不替换44骨/60帧原生动画。实际复用已验证的单面、透明、unlit、原纹理材质，保持rgb*2与固定曝光。

首次实际导入默认启用Nanite。后续单独读取的设置为enabled=true/fallback_relative_error1；转换后的RenderData只有1105面，出现14个不属于源palette的新颜色。此结果和所有失败采集都保留，没有改阈值放行。

新命名空间复制两份校准mesh，仅通过官方 `StaticMeshEditorSubsystem.set_nanite_settings` 关闭Nanite并重建。实际UE5.8.4/D3D11 run9516045f29bc4b40a2569ad97e0b6a79/PID67096自然exit0，4张实际PNG，181旧包hash不变，只新增2mesh；原带Nanite资产不改。新color overlay没有源palette之外的色值。

独立NullRHI只读corner probe/PID77380自然exit0，再由 `Tools/verify_aya_ge_light_calibration.py` 解码源glTF与实际读回，严格使用F32位置和F32/FP16 UV的原word加cyclic绕序匹配，不用nearest或颜色反推身份：

| 层 | 实际转换面 | 精确源position/UV类匹配 | color byte差 | 缺少源multiplicity |
|---|---:|---:|---:|---:|
|SourceModel|1152|1152|0|0|
|RenderData→DynamicMesh|1151|1151|0|1|

缺失仅在原有duplicate class；不是证明raw index buffer已删哪一面。独立读回还核对4张PNG及同机位A/B：+Y共同foreground的meanRGB从white约(136.44,135.52,138.46)变为GE约(27.91,39.72,42.31)。这描述了实际可见光照变化，不是原版pixel-equivalence阈值。root实际查看两图，确认原白色基线变为较暗蓝绿色；穿透、透明排序、输出色彩和原机位对照仍待解决。

正式图像/严格报告路径：`work/t3b_unreal/Validation/ge_lighting_calibration_runs/9516045f29bc4b40a2569ad97e0b6a79/{ue_ge_lighting_calibration.json,root_independent_verification.json,CAPTURE_REVIEW.md}`。

## 剩余范围

仍需逐时间点恢复其它动作的实际灯光/矩阵，接入原生动态顶点着色或等价shader，并核对GPU采样和最终像素。原blend+mainDepth写入、fog、完整纹理combine、重复draw顺序、真正武器/枪口语义及正式UE战斗仍未完成。不能把这组静态校准资产作为完整主角或完成高清化的替代品。

source_protection.json再次核对ISO、slot0与INI原SHA全部不变。没有安装软件、恢复桌面自动化或重复SDK失败构建，所有本轮采集进程均已终止。
