# Aya 与真实武器：同 GE dump 的12个配对样本

2026-10-20。本轮恢复并实际回放了12个身体／枪械同帧GE样本，同时明确了原透明／主深度契约。完整M1仍未完成；本次没有更改旧60帧source-bone／weapon时间轴。

## 原始配对证据

输入来自 `AYA_GE_SAMPLE_SERIES_20261020/inputs_v2` 中 `slot0_fire_verified` 的12份完整PPDMP。每份原dump都含106个Aya packets与一个真实枪械PRIM。idle_long的60份dump没有匹配枪械，未在idle中插入猜测模型。

枪械使用先前原WORLD追踪已确认的完整 `VTYPE + geometry bytes` SHA：

`168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a`

VTYPE=0x522、243顶点／81三角形、stride16、一组原U16权重、S8法线和S16位置。`tools/recover_weapon_ge_paired_series.py` 独立重放material/CLUT与矩阵命令，保留每次原WORLD、BONE、VIEW、PROJECTION及PRIM记录坐标。每份dump内，枪械的VIEW/PROJECTION与106个Aya draws逐项相同，因此可以在共同原WORLD空间观察身体和枪械。

没有从骨骼名字猜挂点，没有手工调枪位置或旋转。配对是同一个GE dump内部的配对，不是两个CPU capture的时间对齐。原CPU↔GE精确时间和武器命名socket／枪口语义仍未知。

`out/WEAPON_GE_PAIRED_20261020/inputs_v1/inputs.json` 保存所有原dump SHA、材质与纹理/CLUT SHA、逐draw定位与body-frame映射。原GE解码武器RGBA逐字节等于既有staged原纹理。

## 计算与实际 UE

固定PPSSPPv1.20.4原软件Lighting/Math3D参考对2916枪械顶点的变换bits／颜色bytes差异为0。`comparison_v1/comparison.json`为完整记录。`runtime_v1/verification.json`用同一个production `T3BGESeries`/`T3BGELighting`实际加载和计算12个一draw样本，输出与独立参考逐byte相同、原UV bits保持，8个损坏输入被拒绝。

新 `Tools/ge_weapon_series_probe.cpp` 是一draw系列的test driver，production reader/kernel没有因武器另写一套算术。仅standalone g++编译；正式UE C++ module仍未UBT通过。

正式接受的实际UE运行：

`work/t3b_unreal/Validation/weapon_ge_paired_runs/96556b7a90d140459ecbb45e4cb359b5/`

- UE5.8.4／D3D11，PID35964自然exit0，执行producer启动前冻结。
- 两个真实DynamicMeshComponent，身体3456点/1152面，枪械243点/81面。二者使用同一个固定原点、canonical units和XZY→UEcm变换；actor/component均identity。
- 使用逐draw重建的原法线与GE顶点颜色、原F32 UV；不采用旧C的面法线明暗。
- 武器材质从现有 `M_Weapon_000` 复制，仅恢复原单面剔除；保留已有原linear纹理和rgb*2/translucent/unlit基线。候选保存在首次运行a8dd的独立命名空间，最终运行只读复用，不修改旧原包。
- 两个固定正交机位±Y、512×768、manual exposure0、bloom/motion blur0。每个样本各有body-only、weapon-only、combined三种实际PNG；两机位共72张，另有2张首样本hidden-control图。

## 原绘制顺序：已实际修正

初版把身体priority0／武器priority1固定下来。root独立审计发现原始顺序并不固定：

| GE样本 | 原目标draw顺序 | 最终实际组件priority |
|---|---|---|
| 0 | 106个身体draw → 武器 | 身体0／武器1 |
| 1…11 | 武器 → 106个身体draw | 武器0／身体1 |

该12帧集合没有武器插在106个身体draw中间的情况。producer按每份dump计算并检查两种完整顺序，再设实际component priority；遇到真正interleave会拒绝，不能静默仍当两组件顺序支持。

首次a8dd实际采集成功，但 `root_independent_verification_failed_v1.json`明确因固定顺序未通过，原报告未改写。随后5de484运行因GE command tuple意外覆盖render-target变量而失败、零样本；错误日志及原包hash保留。修复变量名后，96556运行完成，并通过新的root独立审计。未为了使武器看得更清楚而恢复错误顺序。

## 独立验证结果

`Tools/verify_weapon_ge_paired.py`不导入恢复器。它直接核对原dump／source绑定、独立软件参考输出、实际component读回及实际PNG：

| 核对对象 | 结果 |
|---|---|
| 身体41472＋武器2916＝44388个顶点 | 转后position F64、normal F32、color F32 bits全部相同 |
| 实际首末样本拓扑／UV | 原顶点/三角形顺序/重复面multiplicity与F32 UV全部保留 |
| UE实际武器Texture2D导出Source PNG | RGBA逐byte同原GE解码CLUT纹理 |
| 12张+Y body-only图 | 逐pixel同上轮72样本回放中相同身体样本 |
| 每机位12张combined图 | 各12种实际不同像素图，武器对照和combined均可见 |
| 原184个UE包（包括首轮新增孤立材质） | 最终运行前后及exit后全部SHA不变，无新包 |
| 每帧组件priority | 与原目标draw顺序一致 |

实际读回是DynamicMeshComponent CPU数组，不是GPU顶点readback；PNG变化不认证原机位PSP像素。该检查不证明命名右手骨骼／握把中心／枪口矩阵已恢复。

## 深度／混合问题：原契约已确认，修复尚未完成

`out/AYA_DEPTH_BLEND_20261020/depth_blend.json`从上述7632个Aya draws及12个gun draws直接读取原state，7644次目标PRIM使用相同深度／混合状态：

| 状态 | 原GE值／含义 |
|---|---|
| ZTESTENABLE | 1 |
| ZTEST | 7＝GE_COMP_GEQUAL |
| ZWRITEDISABLE | 0＝启用深度写入 |
| ALPHATEST | greater0，mask255 |
| BLENDMODE | ADD，SRCALPHA／INVSRCALPHA |
| STENCILTESTENABLE | 0 |
| CULLFACEENABLE／CULL | 1／0 |

枚举及depth accessor以实际下载留存的[PPSSPP v1.20.4 ge_constants.h](https://raw.githubusercontent.com/hrydgard/ppsspp/v1.20.4/GPU/ge_constants.h)与[GPUState.h](https://raw.githubusercontent.com/hrydgard/ppsspp/v1.20.4/GPU/GPUState.h)核对，SHA在reference_sources.json。不是把ZWRITEDISABLE=0误读成禁止写入。

本机UE5.8.4 `TranslucentRendering.h::GetTranslucentPassDepthStencilState`普通透明base-pass的两个分支首模板参数都是false，即该pass不写深度。文件SHA和源函数片段保留。该结论不声称UE所有辅助pass都不能写深度。

原Aya atlas含24718个部分透明texels、40818个全不透明texels、0个alpha0 texels；不能直接改Masked就宣称原混合等价。depth-state差异与透体相符，但逐像素因果归属、其它色彩／雾／alpha处理仍未隔离。

root实际查看最终sample11的±Y两张combined图：枪管与原动作移动，但部分枪身会被身体覆盖，手臂透体仍在。这是未完成的主深度／透明问题，不是通过的握把／遮挡校准。最终预览保留这个缺陷。

## 后续与保护

需要真正支持原blend＋main-depth-write＋目标绘制顺序的渲染路径，原机位画面对照、精确动作时钟、武器命名挂点／枪口及正式战斗仍未完成。当前默认source-bone/native候选及正式M1没有被这12个GE样本替换。

交互预览位于最终运行目录 `PREVIEW.html`，可切换±Y和仅身体／仅武器／combined，并显示每帧原draw顺序。30fps仅展示速度。

本轮没有启动PPSSPP、安装系统组件或桌面自动化。`out/WEAPON_GE_PAIRED_20261020/source_protection.json`在2026-10-20 15:18UTC完整哈希确认ISO、slot0存档和ppsspp.ini保持原SHA，无运行中的采集进程。完整高清重制goal继续active。
