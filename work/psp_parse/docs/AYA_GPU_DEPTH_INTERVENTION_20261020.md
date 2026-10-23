# 原Aya／武器：实际GPU主深度干预对照

2026-10-20。上轮已确认原GE在alpha blend时写主深度，而现用UE普通透明base pass不写。本轮在独立D3D11硬件设备上，固定原模型／贴图／颜色／原draw顺序及校准相机，只切换深度写入，以区分深度作用和贴图问题。正式UE路径仍未修复，完整M1未完成。

## 实际运行

`work/t3b_unreal/Validation/ge_depth_reference_runs/ac1f31b9c5e142d1a07a2cbc5f1cf481/`

- 实际PID82388，自然exit0；DXGI查询实际设备为NVIDIA GeForce RTX2080Ti，D3D_FEATURE_LEVEL_11_0。
- `Tools/ge_depth_reference.cpp`／`.hlsl`及输入bundle在编译前冻结。g++13.2、C++17/O2/Wall/Wextra/Werror实际编译，使用已有MinGW D3D11依赖；未安装软件。
- D3DCompile实际编译vs_5_0／ps_5_0；DXBC、执行文件和源码身份留存。
- 没有窗口，没有借用或修改UE的device／context，也没有启动UE或PPSSPP。

首次编译run0e254e1e54f948a89c1a23e8139b2e28被Windows `near`宏干扰；保留失败源码／日志，变量改名isNearLayer后新run实际通过。没有把失败编译回填为成功。

## 原始输入与受控变化

使用已验证的12份同dump Aya／真实枪械。每帧106个身体draw＋1个枪draw，共3699点／1233面；body和gun顶点着色来自同一个已与原PPSSPP软件参考逐byte核对的production reader/kernel输出。

顶点输入为原WORLD结果减去共同固定原点，按canonical units和XZY转换成UEcm，然后转F32。原UV和RGBA light值保持；没有面法线明暗或手调socket。

每帧按原GE命令record/word排序，不按actor名字或“好看”决定顺序：sample0身体→枪，sample1…11枪→身体。每个draw保留独立原packet和MRT owner ID。

两张原atlas由原CLUT解码得到。实际GPU texture staging读回RGBA逐byte等于原上传数据，Format=R8G8B8A8_UNORM，非SRGB；bilinear/repeat，mip0。像素shader使用原GE primary颜色、MODULATE和RGB double，alpha仍参与SRCALPHA／INVSRCALPHA的ADD混合；没有换成Masked。

两组状态共同启用GREATER_EQUAL深度测试、单面BACK cull／FrontCounterClockwise=true、相同viewport／geometry／textures／blend／shader。仅DepthWriteMask分别ALL或ZERO。代码在draw完成后通过OMGetDepthStencilState、OMGetBlendState、RSGetState读回并检查实际状态对象。

## 采集内容

每个原样本×两个±Y正交机位×两个depth模式，共48个实际硬件采集；另有4个明确标为synthetic的合成控制。

每个采集同时读回：

1. R8G8B8A8_UNORM color：实际GPU Map原始bytes，再无修改编码为PNG。
2. R32_UINT owner：该像素最后通过测试并写入的draw ID。不是完整alpha贡献历史。
3. D32_FLOAT depth：实际深度纹理的staging Map数据。

颜色目标只写RGB、alpha保持校准背景值255；没有将该alpha读回宣称为PSP framebuffer/stencil语义。像素输出是原字节算术的D3D11校准，未接UE tonemapper。

## 独立核对与实际发现

`Tools/verify_ge_depth_reference.py`不导入builder，直接解析冻结bundle并检查逐draw输入hash／次序、原atlas、执行身份和GPU输出。

- 52个采集的readback extent、owner范围、有限深度和进程身份通过。
- 禁写组的全部depth值仍为clear0；原写入组的depth>0范围与owner>0完全一致。
- 所有24组实际模型对照的光栅／alpha union coverage完全相同。只改变深度写入，没有删几何或改变剪影来通过。
- 24组累计109953个RGB像素改变，100540个像素的最终draw owner改变。
- 实际sample11／−Y：最终owner为枪的像素从1028增加到3395；5364个RGB像素改变。该owner计数不表示“完整武器贡献像素”，也不是原PSP验证指标。

root实际查看sample11／−Y的两张PNG：开启原主深度写入后，原先被身体错误覆盖的枪身恢复可见，手臂的错误覆盖也改善。半透明贴图仍参与混合。该结果证明本受控GPU路径中的深度干预效应，不自动认证UE或原PSP像素。

## 合成控制：为何最近表面预通道不等价

两个相同范围的矩形，近层红、远层蓝，alpha=128/255，黑底；中心像素远离外边缘。实际GPU结果与独立整数颜色期望完全相同：

| 顺序／模式 | 期望＝实际RGB | 实际最终owner | 实际depth |
|---|---|---:|---:|
| 近→远，写depth | 128,0,0 | 1 | ≈0.8 |
| 近→远，不写depth | 64,0,128 | 2 | 0 |
| 远→近，写depth | 128,0,64 | 2 | ≈0.8 |
| 远→近，不写depth | 128,0,64 | 2 | 0 |

原风格逐次blend＋write在远→近时保留远层的蓝色贡献。先只保留最近深度再绘制近层会得到128,0,0，不能复现这一贡献。这个控制排除了把最近深度预通道或Masked当作原顺序混合等价修复的依据；它没有宣称测试过UE所有辅助pass。

四例为分析构造，不是新增原游戏观测。

## 范围与后续

这是独立native GPU reference，不是UE正式main-depth修复，不替代已有native SkeletalMesh或默认M1。自选±Y正交机位、D32深度、D3D11插值/UNORM舍入；原PSP16位深度量化、原camera、fog、shader输出色彩、完整场景／stencil均未通过验收。最终需要把已验证的blend＋depth-write＋逐draw顺序契约接到UE渲染路径，再做同机位原版对照。

本机只读复查仍未发现正式MSVC／Windows SDK组合。已按实际UE5.8.4 `Windows_SDK.json`和Microsoft官方组件说明保存可审阅方案：`work/t3b_unreal/Validation/toolchain_install_plan_20261020.json`，拟安装MSVC14.44（排除≤14.44.35210禁用范围）及WindowsSDK10.0.22621。此时尚待用户明确授权，没有下载安装器或执行安装。现有MinGW只能证明standalone core/GPU probe，不能据此称UE UBT已通过。

复现：

```powershell
python -X utf8 work/t3b_unreal/Tools/run_ge_depth_reference.py --compiler C:\Strawberry\c\bin\g++.exe
python -X utf8 work/t3b_unreal/Tools/verify_ge_depth_reference.py --run <新运行目录>
```

builder每次生成新UUID目录；验证器拒绝覆盖已有PNG／审计结果。交互预览位于正式运行的 `PREVIEW.html`，可以逐样本／逐机位对照两种真实GPU读回。
