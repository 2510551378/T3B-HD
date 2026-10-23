# 同原版 GE 帧的街景、Aya 与枪械实际 UE 接入

当前 `slot0_fire_verified/frame_0000.ppdmp` 中，140次原街景draw与此前导出街景的原顶点／WORLD能逐项对应，且与Aya和枪械使用同一原VIEW／PROJECTION。本轮将这份同帧街景恢复到当前角色使用的UE厘米坐标，实际在UE5.8.4／D3D11中出图。

[实际UE预览](../../t3b_unreal/Validation/paired_street_ue_runs/f42f69bcedf741fd9515fcfc9d7a72c9/PREVIEW.html) · [街景＋Aya＋原枪图](../../t3b_unreal/Validation/paired_street_ue_runs/f42f69bcedf741fd9515fcfc9d7a72c9/00_original_street_with_aya_weapon.png) · [独立验收](../../t3b_unreal/Validation/paired_street_ue_runs/f42f69bcedf741fd9515fcfc9d7a72c9/independent_street_verification.json)

这是原素材和机位下的实际3D场景接入进展；不是高清材质成品或完整关卡／M1完成。

## 恢复的内容

`recover_paired_street_snapshot.py`先核对当前PPDMP身份，重放每个目标PRIM的矩阵、寄存器、texture与有效CLUT，再匹配既有街景资源的vertex identity＋WORLD。没有通过draw编号范围或包大小猜场景。

全部140次draw均为VTYPE0x11f，原F32 UV、RGBA8、POS16，无骨骼权重或法线属性；合计31,656顶点／10,552三角形。原材质参数和73张解码RGBA必须与既有导入资产对应，否则拒绝复用。保留81个材质状态索引，包括blend、depth-write和cull差异。

本批全为lighting enabled、四个light channel关闭、material update=7、emissive=0、global ambient全白。按固定软件lighting的ambient整数公式，所有0..255输入channel满足 `((2*c+1)*511)>>10 == c`，因此这里原vertex RGBA可保留；没有借用Aya的无COLOR_0灯光核心，也没有捏造缺失法线。该条件不推广到其它场景。

坐标直接从当前原POS16／WORLD求原world点，再沿用已验证Aya／gun的origin、units和XZY转换到UE厘米；没有复用旧场景的Aya相对anchor或额外居中、缩放。新 `T3BSTG1` 是本工程导出桥接格式，不是原PSP格式：20byte header、140个5u32 draw header、36byte `<3d2f4B` 顶点。

恢复目录 `out/ORIGINAL_SCENE_GE_REPLAY_20261021/snapshot_v1/`保存binary、原draw全部registers、WORLD/VIEW/PROJECTION、texture／CLUT身份、73PNG及执行源码。原PPDMP继续作为完整未修改证据。

## 实际UE采集

运行 `f42f69bcedf741fd9515fcfc9d7a72c9`，PID87020，自然exit0；content-only `T3BNativeProbe.uproject`，实际UE5.8.4／D3D11。

新helper `ge_paired_street_capture.py`建立140个临时DynamicMesh component，复用既有M_Street材质和Texture2D，不保存新资产包。实际读回component位置／颜色、每个triangle index与UV，并从73个实际Texture2D逐项导出Source PNG。`capture_weapon_ge_paired.py/_headless.py`仅增加显式`--street-snapshot`模式，要求原机位及复用材质；只采source sample0，不把快照混绑其它时刻。旧模式默认仍保持12样本行为。

场景原draw record17..752全部早于Aya884..1199和gun1204，scene透明priority=-1000+i保持场景组在角色组之前。UE普通透明材质的深度行为仍与原GE不同，priority不能充当主深度修复。

出图包含hidden、body-only、weapon-only、body＋weapon、隔离相机marker、street-only和street＋Aya＋weapon。root实际看过组合图：原路面、建筑、警用路障、托盘、树及路桩与Aya／枪械处于同一机位；没有用背景PNG代替场景几何。实际输出480×272，预览只是2倍放大。

## 独立验收覆盖

`verify_ue_paired_street.py`从同一原PPDMP重新获取PRIM状态和原raw vertices，重新计算WORLD与当前UE坐标转换，核对：

- 全部140draw／31,656个component position F64 bits、vertex color F32 bits。
- 原UV F32 bits、triangle顺序与multiplicity；81材质索引、实际单／双面属性及组内priority。
- 73个真实UE Texture2D **Source** PNG逐RGBA等于该原帧有效CLUT解码，SRGB=false。该结果不是GPU texture mip/filter或最终图像的像素等价。
- 同帧Aya／gun的3,699个component顶点读回与上一轮已接受数据逐byte相同。
- 实际camera property与上一轮相同；街景隐藏时hidden／body-only／weapon-only／combined四个控制图与上一轮逐像素相同。

街景单独图有96,575个超过1LSB背景噪声的像素，加入Aya／gun后3,910个像素变化；这是可见性证据，不是原机pixel fidelity误差指标。

场景component transform当前以UE序列化的6位小数repr记录，默认spawn的translation/rotation/scale为identity；没有将repr的内存地址拿来比较，也未把其精度称作完整world-matrix bit readback。实际position bit验收针对component local数据，当前临时actor使用identity。

## 明确仍未实现的状态与时间变化

140个源draw均开启fog和stencil；112个blend关闭，23个blend且写depth，5个blend且不写depth。原fragment参数、fog1/fog2/fogcolor和stencil ops完整保留，当前普通UE材质没有据此宣称等价实现。原GE深度pass仍未在正式C++模块中编译／运行。

本轮后续还对12份原dump只读检查了同geometry资源的WORLD覆盖，`series_world_coverage.json`记录：samples0..3可对应140个旧geometry＋WORLD实例；samples4..11可对应123个相同实例，另3个同geometry资源出现不同WORLD。其它旧draw在这些样本中未被观察到，不能据此断言已删除或属于不可见geometry。**不得将当前sample0快照当全程固定街景。**三个WORLD变化的实际语义尚未确认，不能直接命名为tree/billboard或破坏动作。

没有包含其它原weighted actor、Twisted、FX、HUD、遮挡外几何或完整关卡；原collision、triggers、navigation仍未恢复。原材质仍是PSP分辨率，正式M1默认world未切换。新快照用于可核对的场景接入与后续GE pass扩展。

## 保护与后续

`source_protection.json`重查184个既有UE package和原ISO／slot0存档／PPSSPP INI，全部hash相同，无新增／删除package。没有启动PPSSPP、系统安装或桌面自动操作。此前已授权的工具链安装仍因Windows提权取消而未启动，既有UAC诊断问题未获回复；未重复弹出安装器。

下一步应按实际逐帧WORLD恢复街景变化，再把source fog／stencil／blend＋主深度纳入统一渲染验证；同时等待UAC诊断以完成真正的MSVC／SDK安装和UBT。当前同帧组合图不替代这些验收。

本轮另保留官方PPSSPP v1.20.4 [Rasterizer.cpp](https://github.com/hrydgard/ppsspp/blob/v1.20.4/GPU/Software/Rasterizer.cpp)供后续fog插值调查。尝试读取不存在的PixelFunc.cpp得到404，已在source manifest明确记录，未把该文件称作已获取或编译的参考。
