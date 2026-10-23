# UE M1 v4：当前运行入口

更新：2026-10-23。默认 `M1_SourceReplay` 地图已接入可玩战斗 Pawn / HUD / Director，详见 [UE_M1_V4.md](../../docs/UE_M1_V4.md)。v4 保留 v3 的 Aya 材质遮挡与 body/weapon 同步动作修复。

- 8,551 个原街景可见三角形用于胶囊移动、射线与相机遮挡；敌人命中使用当前 posed 三角形，与墙体比较最近距离。
- 已有锁定、持续射击、30 发弹夹、装填、敌人追击/近战、HP、受击/死亡、重启及 Overdive 镜头返回。玩法和碰撞属于 PC M1 适配规则。
- Overdive 为 0.32 s 进入、1 s 停留、0.32 s 返回、3 s 冷却的镜头适配，尚无原版宿主转移系统。
- 真实枪口射线准星；Mouse pitch 当前只改镜头，不改恢复动作的枪管 pitch。Aya 和武器共享原 affine 动作时间及 120 ms 循环过渡。
- UE 5.8.4 / CL 58902052 / module BuildId `55116800`；Editor 编译通过。最终模块 NullRHI / D3D11 严格战斗检查均 14 项通过；D3D11 4 shots / 4 hits / enemy HP 0 和 Overdive 返回通过，外侧镜头已目视复验。v4 冷 clone 安装、实际 D3D11 / NullRHI 战斗、source probe 与公开 Release 下载均已校验通过。
- 源码检查共 127 项（57 source-data + 29 动作 + 41 碰撞）。

安装 v4 匹配运行包后，从仓库根目录运行：

```powershell
.\scripts\run_unreal.ps1 -EngineRoot 'C:\Program Files\Epic Games\UE_5.8' -Game
# 原 Spectator / source probe 诊断：
.\scripts\run_unreal.ps1 -EngineRoot 'C:\Program Files\Epic Games\UE_5.8' -Game -ReplayOnly
```

WASD 移动、Shift 跑、Mouse View、RMB / Tab 锁定、LMB 连射、R 装填、E Overdive、Backspace 重启；Esc 释放鼠标，单击重新捕获。启动需要匹配的 UE Editor host；尚未 cooked，也尚未完成高清美术和完整原版系统。运行包[预定发布入口](https://github.com/2510551378/T3B-HD/releases/tag/runtime-assets-20261023-v4)与[安装方法](../../docs/ASSET_HANDOFF.md)。

## 历史开发记录

以下内容保留各阶段原始结论，含已过期的“当前/最新”“未安装 SDK”“尚未移植战斗”等表述。请以本页顶部和 [CURRENT_STATUS.md](../../docs/CURRENT_STATUS.md) 为当前状态；历史原始证据不被新结果改写。

> GitHub 协作入口：[../../README.md](../../README.md)，当前状态见 [../../docs/CURRENT_STATUS.md](../../docs/CURRENT_STATUS.md)。下文保留各阶段历史记录；本机数据路径不随 Git 发布。

## 最新：type23 可选 RCX 随机路径已进入生产 core

新增可选RCX→VRNDF2→type23 modifier路径，固定seed bridge实际通过；运行时默认仍不使用未知game seed。[VFPU算法与边界](../psp_parse/docs/FX_VFPU_RCX_20261021.md)。

正式UE／M1和原版seed时间线仍未完成；原ISO／存档和UE包不变。以下为此前阶段记录。

## 最新：VFPU RCX 随机算法已接入生产 core

按PPSSPP v1.20.4固定源码恢复vrnd init/generate，6个seed/kind测试、48次生成逐bit通过。游戏节点初始RCX尚未采集，type23继续使用真实观察vector，不替换成宿主随机。[验证与边界](../psp_parse/docs/FX_VFPU_RCX_20261021.md)。

正式UE／M1和原版随机时间线仍待完成；原ISO／存档与185个UE包不变。以下为此前阶段记录。

## 最新：type6／type23 与矩阵消费者关系已审计

确认type6/type23共享N+0x80状态，而实际矩阵helper读取另一P+0x60 alias；已有矩阵数学与GE输出证据通过。局部矩阵实时尝试只到达leaf entry，未形成完整writer join，因此没有把type6误接进渲染。[审计与边界](../psp_parse/docs/FX_MATRIX_CONSUMER_MAP_20261021.md)。

正式UE／M1仍未切换，原ISO／存档与185个UE包不变。以下为此前阶段记录。

## 最新：原版 type6 连续状态已由生产 core 推进

恢复key／wrap／vec4求值。实际程序只载入一次initial state，串联type23随机扰动、4次正常求值和2次完整回绕；7组状态逐bit同一原节点。另13真实操作、10合成opcode cases、6错误输入检查通过。[来源与验证范围](../psp_parse/docs/FX_VECTOR_CURVE_20261021.md)。

当前是连续数值链，尚未接其局部矩阵／最终画面；原时间单位／秒数、完整调度和可玩M1仍未完成。原ISO／存档与185个既有UE包不变。以下为此前阶段记录。

## 最新：原版随机 modifier 与实际目标已恢复

确认type23内部写三分量状态区+20、type24写百分比/转换区+60，不能照callback参数offset绑定。新增生产modifier core：2个真实回调与原返回逐bit一致，原scalar RNG三次seed链恢复，14合成opcode cases及6错误输入通过。[来源、实现与范围](../psp_parse/docs/FX_RANDOM_MODIFIERS_20261021.md)。

type23的VFPU随机种子控制仍未恢复，当前显式消费实际观察vector。完整属性时钟、UE正式运行和可玩M1继续推进；原ISO、存档和185既有UE包不变。以下为此前阶段记录。

## 最新：逐 draw 场景与动态颜色已接入 UE module 源码

新增生产scene loader／颜色求值、新校准actor／RDG pass和共享pixel shader。实际独立编译执行：79atlas、838draw、24颜色绑定完整保持，8错误输入拒绝；共享shader的3帧native GPU输出同原基线逐byte一致。[证据、UE运行参数与范围](../psp_parse/docs/UE_SCENE_COLOR_BRIDGE_20261021.md)。

正式UE actor／RDG／RHI尚未编译运行；新入口是默认关闭的原camera校准，使用独立source depth，不是PC gameplay depth／默认M1。原ISO／存档与185既有UE包不变。以下为此前阶段记录。

## 最新：原版颜色特效已回到同帧原角色与街景

3份同运行GE记录恢复Aya、原枪、异形、街景与选定特效，共838draw/109299GPU点/79原CLUT贴图。生产颜色流程的整帧GPU输出同原GE输入逐byte一致；937个特效遮挡pixel均由原场景深度验证，主depth/stencil不变。[实际预览与验证范围](../psp_parse/docs/FX_SAME_FRAME_SCENE_20261021.md)。

当前仍是native D3D11场景子集，正式UE C++／默认M1、高清美术和可玩战斗待完成；其他FX／sprites／HUD未纳入本组。原ISO／存档和185个既有UE包不变。以下为此前阶段记录。

## 工具链最新状态：本次授权安装仍未通过 Windows 提权

已按用户新授权尝试安装MSVC14.44与SDK22621。官方安装器重新验签通过，但Windows提权返回取消，installer未启动、组件未安装，本次未执行UE C++构建。[实际终态记录](Validation/toolchain_install_runs/5f96be975a50477eb0fa1b5764af4047/terminal_status.json)。不自动重复提权；下文关于安装授权/UAC的表述为各阶段历史。

## 最新：原版顶点颜色已与同运行 GE记录对齐

3组精确 CPU→GE对应确认改写后的颜色进入实际记录：24次draw观察、96个顶点。生产颜色core与现有effect geometry core已在同一程序串联执行，palette、原始顶点、local position/UV/RGBA及48个三角形的索引全部逐 byte 同原 GE输入。[数据、材质与验证范围](../psp_parse/docs/FX_VERTEX_COLOR_GE_20261021.md)。

逐draw原矩阵、CLUT和raster状态已保留，下一步验证新输入的native GPU输出，再接正式UE/M1。当前尚未切换默认M1，原ISO、slot0、INI及185个现有UE包哈希不变。

## 最新：原版特效颜色缓存与真实顶点改写已恢复

确认该武器特效使用顶点颜色 palette更新，而非直接写GE材质颜色。生产 C++ core实际复现6次颜色/缓存调用、5次palette转换，40个draw/160个顶点的完整改写bytes同原版，UV与position保持不变。原palette和8个draw的颜色引用已导出。[数据、原路径与验证范围](../psp_parse/docs/FX_VERTEX_COLOR_PIPELINE_20261021.md)。

当前是实际 CPU写入与独立core验证，同次GE/GPU消费、正式UE和默认M1接入仍待完成。顶点palette独立于texture CLUT；原ISO、slot0、INI与185个既有UE包哈希不变。

## 最新：原版特效颜色与百分比缩放 core 已验证

恢复 type16 的 RGBA key切换、回绕和内部求值，以及 type7 百分比换算。生产 C++ core实际执行11个真实更新点，116个原始 float分量逐 bit 相同；另10个明确合成的原指令样例通过。原颜色/缩放 key与共享参数块的真实调用顺序已导出。[来源、prefix范围与验证记录](../psp_parse/docs/FX_COLOR_SCALE_20261021.md)。

后续还需确认颜色经 parent/material/palette分支到实际 GE命令的完整链路。正式 UE module与默认 M1尚未切换；原 ISO、slot0、INI 和185个现有 UE资源包哈希不变。

## 最新：原版武器特效 UV 曲线已恢复并输出真实命令

恢复30次原属性回调绑定，type155的4次真实 key/回绕更新与生产 C++ core 的24个 float分量逐 bit 相同。另6次连续原版渲染确认 UV 滚动，从像素偏移、64×32纹理归一化到12条实际 GE UV OFFSET命令全部对应；当前生产 core 输出也逐 bit 相同。原初始/time-key payload与共享参数定义已导出。[解析、原数据和验证范围](../psp_parse/docs/FX_PROPERTY_CURVES_20261021.md)。

这是独立 core及真实 CPU 命令写入验证；正式 UE module与默认 M1仍待接入，其他属性/完整生命周期/高清美术与可玩验收继续推进。原 ISO、slot0、INI 和185个既有 UE包哈希不变。

## 最新：原版武器 FX 时间推进与回绕数值 core 已验证

原节点时钟的8次真实写入效果和1次渲染时间参数已恢复，生产 `T3BGEEffectClock` 实际独立编译执行，9项 F32 输出与原版逐 bit 一致。另13个明确合成的原指令数值样例通过，6个非法输入拒绝；原 loop 区间 `[0,2)`，推进与回绕 writer 分别为 `08b683f8`、`08b68e4c`。[来源、验证和待完成范围](../psp_parse/docs/FX_NODE_CLOCK_20261021.md)。

回绕前的属性/事件回调、参数曲线与秒数换算仍待恢复，正式 UE module 尚未构建，默认 M1 未切换。原 ISO、slot0、INI 和185个现有 UE 资源包保持原哈希。工具链安装仍是 Windows 提权取消、installer 未启动的终态。

## 最新：原枪视觉特效完整子 draw 与生产 geometry decoder

原ID18的14/15顶点两draw和ID19的8个四顶点draw已由原对象记录、实际CPU命令和GE连续PRIM对齐确认；两组采集共36个GE子draw对应。新增生产 `DecodeOriginalEffectStrip`，实际独立C++执行对207个顶点/135三角形的position、UV、颜色、索引逐byte一致。原矩阵/CLUT绑定保留，未作HD重绘。详见 [WEAPON_FULL_HANDLER_GE_20261021](../psp_parse/docs/WEAPON_FULL_HANDLER_GE_20261021.md)。

这仍是已确认源数据与独立core。FX时间行为、新相机billboard、正式UE module和默认M1可玩验收尚待完成；原ISO/slot0/INI及185个已有UE资源包保持原哈希。

## 最新：原枪 source1 到视觉 FX 的 CPU/GE 链路已验证

瞄准/移动瞄准新采集取得12个精确 CPU→GE draw 对应，覆盖3个记录帧及2张实际 CLUT 材质。生产 `ComposeOriginalWeaponMarker` 的28条 full-F32 输出与真实原版 state60 共448个分量逐 bit 一致；实际编译/执行的是独立 core。完整证据和范围见 [WEAPON_CPU_GE_CORRELATED_20261021](../psp_parse/docs/WEAPON_CPU_GE_CORRELATED_20261021.md)。

source1 已确认驱动所观察的视觉 FX；真实弹道/命中起点及完整子 draw/原时间行为仍待恢复。正式 UE module、默认 M1 枪口绑定和可玩验收继续待完成。原 ISO、slot0、INI 与185个原 UE 资源包保持原哈希。

## 最新：原枪 source1/source2 marker 原始矩阵接入独立 C++ core

恢复24个真实快照中一致的原始 marker 定义，直接以当前 GE WORLD 回放12组姿态/24条 marker；实际编译执行与独立计算通过。原 FX +5/+7 参数、跨采集几何关联与 F24 区间证据见 [WEAPON_SOURCE_FX_LINKS_20261021](../psp_parse/docs/WEAPON_SOURCE_FX_LINKS_20261021.md)。这是 source index 原始矩阵回放，真实枪口/弹道语义及同帧 CPU/GE 关联仍待确认，默认 M1 未切换。

正式 UE module 尚未编译；本次授权安装在 Windows 提权阶段返回取消，未安装工具链。详见 Validation/toolchain_install_runs/c793438269084fbd9e286606ddecd93a/terminal_status.json。原 ISO/slot0/INI 与185个现有 UE 资源包哈希保持一致。

# The 3rd Birthday — UE5 migration

## 当前：原版矩形粒子恢复，固定上游函数与实际 GPU 检查通过

从12份同帧捕获恢复6,975个原矩形、13,950端点。clip/fog、有效screenXY/Z16与26,867候选pixel的UV／颜色／depth逐byte同固定PPSSPP函数；1,075个可见quad已实际与原角色／FX／街景出图。128GPU采集及13个诊断样例通过，关闭sprites后颜色／owner／depth byte exact。[粒子预览与关闭对照](Validation/ge_sprite_runs/d73d3f8edb0b4c629d0c991f9b46768b/PREVIEW.html)／[来源与边界](../psp_parse/docs/GE_RECT_SPRITES_20261021.md)。

这是独立native reference。原场景仍3D，矩形按原语义在当前相机下展开，改相机需重算原端点；新格式与粒子尚未接UE C++。完整PSP像素、原clock／AI／碰撞／伤害、高清材质与M1继续推进，185个UE包及原ISO／存档不变。以下为先前阶段记录。

## 当前：新增原版三角条带 FX 与武器 emitter 候选

独立native D3D11恢复407次原FX draw、3,081展开顶点、10个原CLUT贴图变体，烟雾／闪光／红色碎片／地面暗影与原角色同帧可见。合并3,635draw／438,105 GPU顶点／88atlas，91GPU采集独立检查通过；关闭新FX后颜色和深度同原已接受基线。逐draw局部origin解决VIEW内placement的float32相消，未放宽投影阈值。[实际FX预览](Validation/ge_strip_fx_runs/eb127720dab34700b91773818e73350e/PREVIEW.html)／[证据与限制](../psp_parse/docs/GE_STRIP_FX_20261021.md)。

3个样本中一组原FX的weapon-local原点接近，支持枪口emitter假设；原attachment尚未定位，未替换M1 socket。新FX尚未接入UE C++，rectangle sprites／HUD／FBO postprocess、原时钟、AI／伤害／碰撞、高清化仍未完成。现有185个UE包和ISO／存档保持不变。以下为先前阶段记录。

## 当前：原版异形已与 Aya／枪械／街景在实际 UE 同帧回放

UE5.8.4/D3D11完成12组同捕获原异形的28-packet geometry replay。21,600个实际组件点／normal／color／UV／三角顺序及原256² Texture2D Source RGBA检查通过；72GPU相机markers通过，60张隐藏异形控制图同基线逐像素相同。针对原draw开启背面剔除，新增独立单面材质候选，184旧包和原ISO／存档保持不变。[实际UE预览](Validation/other_actor_paired_ue_runs/40fedc9fa49f4ad3ab9660645c77717e/PREVIEW.html)／[范围与证据](../psp_parse/docs/OTHER_ACTOR_SAME_GE_UE_20261021.md)。

**画面仍有缺陷**：Aya背面露出正面等透明主深度问题未修复；当前不是SkeletalMesh／动作时钟恢复、正式C++ pass或可玩的M1，背景／fog／stencil仍仅native参考更完整。高清材质、AI、伤害和原碰撞继续推进。以下为先前阶段记录。

## 当前：原版异形、Aya、枪械和街景已按同份 GE 捕获在 native GPU 同帧验证

新增原版11-bone异形的12组动态姿态，每组28draw／1,800点。生产skin/light输出21,600点逐byte同固定PPSSPP software reference；合并场景3,228draw／435,024 GPU顶点／78原CLUT贴图通过独立检查，异形在12组实际画面中均可见。[查看含异形的同帧预览与加入前后对照](Validation/observed_ge_scene_runs/f99ea978f2644fe3aa63b5af15c39251/PREVIEW.html)／[证据与边界](../psp_parse/docs/OTHER_ACTOR_SAME_GE_SCENE_20261021.md)。

这是独立native D3D11参考，新数据尚未接入正式UE C++ pass／M1；具体敌人名称、原动作时钟、AI／伤害／原碰撞与高清材质仍未完成。原ISO／存档／184旧UE包均未改。下方为先前阶段记录。

## 当前：原版逐 draw 场景 native GPU 对照通过；UE 正式编译仍缺工具链

新增12组独立GPU场景：2,892draw／413,424顶点、77原CLUT贴图，含此前40次未匹配draw。独立相机背景、原顺序、fog／depth-stencil子集与Aya／枪械同帧出图，64GPU采集通过独立检查。[实际手动预览](Validation/observed_ge_scene_runs/d16757dbab6645ababbe99e4d838841d/PREVIEW.html)／[证据与边界](../psp_parse/docs/OBSERVED_GE_SCENE_GPU_20261021.md)。这是native D3D11参考；新增源状态尚未接入UE C++ pass，原素材还未高清化，完整M1未完成。

**安装最新状态**：用户已授权MSVC14.44＋SDK22621；官方安装器已下载验签，但Windows提权返回取消，安装尚未启动，现有UAC诊断待回复。下文早期“等待安装授权”表述仅为历史记录，不再适用。未重复提权，没有后台installer在运行。

这是正式重制版的 UE5 C++ 工程初版。已有 UE 5.8.3（CL 58210709）的真实资产导入和蒙皮记录，以及 UE 5.8.4（CL 58902052）的离屏图像；具体版本以各运行报告的 engine_version 为准。首次 UnrealBuildTool 构建因 Windows SDK 缺失而失败，尚未进入 C++ 编译。当前安装为 UE 5.8.4，Build.version、编辑器文件版本与 Launcher manifest 一致。后台 commandlet 已保存并核验 76 张贴图、84 个基线材质和 1 个空地图。角色画面仍有明确缺陷，正式 replay 和战斗未通过验收。用户已停止桌面自动操作，后台开发继续。

## 最新：12组街景实例与角色／枪械已在UE逐采样配对回放

实际UE5.8.4/D3D11完成全部12组已匹配街景实例集：前4组140draw、后8组126draw，1,568draw／358,488点的原GE到component读回通过；73实际Texture2D Source RGBA匹配原CLUT。原机位72GPU markers再通过，sample0街景图同旧snapshot逐像素相同。复用render slots并隐藏14多余槽位，没有把3个WORLD变体编成对象运动轨迹。[逐采样实际预览](Validation/paired_street_series_ue_runs/f13b293ea4de4f258b16b4d7250f9339/PREVIEW.html)／[范围与证据](../psp_parse/docs/PAIRED_STREET_SERIES_UE_20261021.md)。

仍有40次未匹配VTYPE11f观察未渲染，已保留其原状态与7种原RGBA解码。594vertex draw使用独立VIEW/PROJ，贴图为云层；背景用途待确认，不能套main camera。当前普通UE材质的fog/stencil／透明主深度、高清素材、完整M1仍未完成。184旧包及ISO／存档／INI不变。

## 最新：原版街景、Aya和枪械已在实际UE同帧出图

同GE source sample0的140次原街景draw／31,656个顶点与Aya和真实枪械，已经使用同一原版相机在UE5.8.4/D3D11中实际渲染。独立原PPDMP重算核对component位置／UV／颜色／三角顺序；73张实际Texture2D Source RGBA同原有效CLUT解码。街景隐藏后的4个角色控制图与前轮逐像素相同。184旧包与原ISO/存档/INI未改，无新增package。

[实际街景＋角色预览](Validation/paired_street_ue_runs/f42f69bcedf741fd9515fcfc9d7a72c9/PREVIEW.html)／[范围与证据](../psp_parse/docs/PAIRED_STREET_UE_20261021.md)。这是480×272原素材同帧诊断接入；原fog/stencil／透明主深度、高清贴图、Twisted及完整M1仍未完成。后续样本存在3个WORLD变化，不把本快照当全程固定关卡。

## 最新：原版采样相机接入实际 UE SceneCapture

实际 UE5.8.4/D3D11 完成12个Aya＋原枪采样的原机位回放，44,388个组件顶点bit核验通过；72个隔离彩色GPU标记中心对原相机投影最大偏差约0.55PSP像素（阈值1像素）。184旧包及原ISO／存档／INI相同。[实际UE/native双栏预览](Validation/original_camera_ue_runs/5a76f5096f5c46be84c5d8f1260a1f29/PREVIEW.html)／[范围与失败记录](../psp_parse/docs/AYA_ORIGINAL_CAMERA_UE_20261021.md)。当前UE普通透明材质仍透体，新C++ GE pass未运行，M1／HD材质未完成。

用户本轮已明确授权后台安装MSVC／SDK；Microsoft官方installer已下载并通过签名检查，本次Windows提权请求返回“操作已被用户取消”，安装器未启动，尚无组件安装成功证据；错误及terminal_status.json已留档，没有重复提权。安装记录在Validation/toolchain_install_runs/f041d28d9c114afbb23324f1d76b4c5a；后续跟踪同一进程，不能重复启动或把pending提权记作构建通过。

## 最新：原版逐样本相机已恢复并完成 native 3D 对照

12 份原 VIEW／PROJECTION／viewport 按 PRIM 时刻恢复，覆盖1284次Aya/枪械draw。实际native D3D11运行生成24份原机位depth对照、44,388条GPU VS输出；与原世界点经过原相机的独立投影最大误差约0.000040个PSP像素。原GE depth clamp=1，已确认所选几何全在Z clip内部，未推广到场景。184旧包和原ISO/存档/INI不变，旧校准156 GPU buffers回归零差。

[逐样本原机位预览](Validation/ge_original_camera_runs/82e331c301ed4ecaa7832b97a9a673dd/PREVIEW.html)／[范围与证据](../psp_parse/docs/AYA_ORIGINAL_GE_CAMERA_20261021.md)。这是480×272原分辨率的独立3D reference，未接入正式UE相机/RDG，未恢复原时钟，也没有高清贴图或场景完成声明。

## 最新：shader 主体投影与 HDR 曝光实际 GPU 检查通过

当前 WorldToClip shader 主体由 FXC 实编并在独立 D3D11 硬件进程运行。3 组矩阵的 15 条 VS stream-output 记录符合独立参考；四档曝光与 alpha=0 discard 共 1,280 像素精确通过，超过 1 的 HDR 值保留。184 个 UE 包和原 ISO／存档／INI 相同。该结果不覆盖 UE shader compiler、相机参数绑定或 RDG，正式 UBT 与 UE 验收仍待工具链；安装确认没有得到回复。[范围与实际证据](../psp_parse/docs/UE_GE_WORLD_SHADER_GPU_PROBE_20261021.md)。

## 最新：UE按序3D GE pass已实现，待实际编译验收

新增 `AT3BGEReplayActor`、world ViewExtension和RDG pass，提交真正3D顶点／UV／颜色与两张原RGBA纹理，使用实际UE相机，按原draw顺序进行alpha blend并写主深度；没有用PNG替代3D，也没有改成Masked。module增加RHI/RenderCore/Renderer，加载期改PostConfigInit以注册global shaders。现有默认replay/native候选尚未替换。

生产 `T3BGEGeometry` reader与共享 `T3BGECommon.ush` 已用于真实native D3D11 run6bb0e3db0bcd40cb98ba9f66aceae654：52采集的156份颜色/owner/depth GPU读回与原参考逐byte相同，9坏输入拒绝。这个验证覆盖reader/sharedpixel，**UE actor、WorldToClip shader wrapper与RDG未编译或运行**；184旧UE包及原ISO/存档/INI hash均不变。

真实UE48图采集／独立验收脚本已准备，缺正式DLL会拒绝启动。MSVC/SDK安装确认仍待用户回答，尚未安装，不把环境日期更新当作授权。[实现与验证范围](../psp_parse/docs/UE_GE_ORDERED_PASS_IMPLEMENTATION_20261021.md)。正式M1／原机位像素／时钟／socket／枪口等仍待完成。

## 先前：实际GPU主深度写入干预

独立D3D11 runac1f31b9c5e142d1a07a2cbc5f1cf481完成48个原Aya/枪械几何采集＋4合成控制。相同原模型、texture/GE vertex color/draw order与校准相机，只切换depth write；实际颜色、D32深度、最后通过draw的R32 owner均由GPU staging Map读回。24组union coverage全同，累计109953RGB像素/100540owner改变；实际看图中原先被身体覆盖的枪身恢复，手臂错误覆盖改善。原alpha blend仍保留。合成控制还证明nearest-only深度预通道不能等价代替顺序blend+write。

[GPU实际左右对照](Validation/ge_depth_reference_runs/ac1f31b9c5e142d1a07a2cbc5f1cf481/PREVIEW.html)与[检查记录](Validation/ge_depth_reference_runs/ac1f31b9c5e142d1a07a2cbc5f1cf481/CAPTURE_REVIEW.md)。这是独立nativeGPU reference，UE renderer尚未修复，原camera/fog/PSP16bitdepth/完整输出色彩仍未验收。184旧UE包和原ISO/存档/INI hash保持相同。

正式UE C++编译依赖仍未发现完整MSVC/WindowsSDK组合，已保存Validation/toolchain_install_plan_20261020.json并向用户询问是否允许官方后台安装；尚未得到确认，也未下载或安装。完整证据与边界见 `../psp_parse/docs/AYA_GPU_DEPTH_INTERVENTION_20261020.md`。

## 先前：12个同GE样本的Aya与真实枪械回放

实际UE5.8.4/D3D11运行96556b7a90d140459ecbb45e4cb359b5将原12份dump中的Aya106draws与真实243顶点枪械配对，原WORLD/BONE各自恢复、VIEW/PROJECTION一致。原draw顺序在sample0为body→weapon、1..11为weapon→body，实际priority逐帧切换。44388个component位置/法线/颜色bits与software reference一致，UV/拓扑保留；真实UE枪贴图SourceRGBA同原GE解码，12张body-only像素与上轮对照全同，184旧包hash不变。

[实际动态预览](Validation/weapon_ge_paired_runs/96556b7a90d140459ecbb45e4cb359b5/PREVIEW.html)可切±Y和body-only/gun-only/combined；[检查记录](Validation/weapon_ge_paired_runs/96556b7a90d140459ecbb45e4cb359b5/CAPTURE_REVIEW.md)保留实际图及两次失败。原GE启用alpha blend且写主depth，当前普通UE透明basepass不写depth；因此透体与枪身被身体覆盖仍未通过。24718部分alpha texels不允许把Masked近似叫原blend等价。

这些是同dump的采样配对，30fps只为展示。named socket/握把中心/枪口、原精确时钟与正式M1均未完成；旧60source-bone/weapon/defaultreplay绑定未改。完整来源、真实UE报告及深度契约见 `../psp_parse/docs/WEAPON_GE_PAIRED_20261020.md`。

## 先前：72个原GE样本的实际UE动态回放

已从原idle_long60＋射击输入12份逐帧PPDMP恢复7632次Aya draw的WORLD/BONE/原法线/灯光/CLUT材料。新production `T3BGESeries` reader/kernel以standalone g++实编运行，248832顶点的变换与颜色逐byte同固定PPSSPP软件参考，8坏输入拒绝；正式UBT仍未通过。现有 `T3BReplayWorld` 默认source-bone/weapon/face-shade尚未改成新采样组。

实际UE5.8.4/D3D11 run30e6de5c441f4e55ba482b1c1f02d427在同一DynamicMeshComponent更新72样本并导出72实际PNG；独立读回位置/法线/颜色bits全同，抽取拓扑保留原3456点/1152面/原UV及重复面，183旧包hash全同。预览[PREVIEW.html](Validation/ge_sample_series_runs/30e6de5c441f4e55ba482b1c1f02d427/PREVIEW.html)与[画面检查](Validation/ge_sample_series_runs/30e6de5c441f4e55ba482b1c1f02d427/CAPTURE_REVIEW.md)。

30fps是人为预览间隔，原CPU↔GE时序未知；原60帧射击源动作只有2份GE，不能把新两采集组混绑旧武器。画面手臂透体、主深度/透明/色彩与武器同步仍未验收，素材仍为原PSP分辨率。详细来源、独立参考、cache修正与边界见 `../psp_parse/docs/AYA_GE_SAMPLE_SERIES_20261020.md`。

## 先前：原版顶点光照核心与实际 UE 校准

新增 `Source/T3BRemake/Public/T3BGELighting.h` / `Private/T3BGELighting.cpp`，从原GE palette/WORLD、加权法线与directional/point灯计算Gouraud颜色。原始输入覆盖3份采集、318draw/10368vertex；standalone g++编译后与固定PPSSPPv1.20.4原Lighting/Math3D软件实现的变换bit和颜色byte全部一致。13个合成边界与8个不支持输入拒绝检查通过。该核心尚未经过正式UBT或原生角色逐帧调用，UE当前使用预计算顶点颜色进行静态校准。

实际 UE5.8.4/D3D11 run9516045f29bc4b40a2569ad97e0b6a79比较同一源姿态的white/GE两模式，材质/曝光不变，角色从过亮白色基线变为原采集蓝绿色光照。独立精确corner匹配确认SourceModel1152面与转换RenderData1151面的position/UV/color均对应源数据；剩余1duplicate multiplicity与rawindex边界保留。初始自动Nanite生成1105面/14个源palette外色值，已通过新副本仅关闭Nanite、实际重建与读回消除；181旧包hash不变。完整图像、原失败记录和严格验证见 `Validation/ge_lighting_calibration_runs/9516045f29bc4b40a2569ad97e0b6a79/CAPTURE_REVIEW.md`。

此校准是原版单个静态姿态，不替代45骨/60帧的原生角色或完整战斗；其它时间点灯光、透明主深度、输出色彩和原机位像素仍待恢复。完整原始输入/模型边界见 `../psp_parse/docs/AYA_GE_VERTEX_LIGHTING_20261020.md`。

## 先前：恢复 Aya 原版剔除并持久化 native 候选

三份原 PPDMP 的318次 Aya PRIM 全部启用单面剔除；旧 TwoSided=true 来自 C 预览 fallback。`../psp_parse/out/AYA_CULL_ORIENTATION_20261020/FINDINGS.md` 给出逐draw原始寄存器与1152面绕序证据。

实际 UE 5.8.4 同进程 A/B run8198e8faa071458c834fa911389cc582 的8张图中，单面材质恢复了背心后片、牛仔后袋和靴子后跟；基线反面近似正面镜像的问题在这些姿态中已修正。只改变 TwoSided，其余图/UV/法线/透明混合/曝光不变。root独立Pillow读回核对相机component transform、同帧45骨姿态、PNG像素和176旧包hash。见 `Validation/native_cull_comparison_runs/8198e8faa071458c834fa911389cc582/CAPTURE_REVIEW.md`；胳膊透背与肤色偏亮仍存在，未宣称完整保真。

新持久化候选 `/Game/T3B/NativeCandidates/AyaSourceCull/Run_831698320b0d40c8becacb7e91609889/aya_source_cull` 将已测试单面材质直接设为 FullUV mesh 的默认 slot0，引用原 compact skeleton；不用临时 component override 才能生效。独立 UE5.8.4 进程只读重载通过：`Validation/native_source_cull_binding_runs/84e06f072fb04a658d6cc945ea8704c2/verified.json`。实际45骨层级、FullUV设置、15个LOD构建参数及3449原始LOD顶点计数与源FullUV一致，179个现有包hash不变。此前失败运行保留，最后一次失败仅是把Struct内存地址当构建设置比较；成功重载改用逐属性值比较，没有放宽值或覆盖失败证据。候选尚未替换正式 PMC。

后续 glTF 导出已改为从原 GE cull_enabled 生成 doubleSided。新 `../psp_parse/out/AYA_NATIVE_SOURCE_CULL_20261020/aya_native.gltf` 的独立delta报告证明仅材质记录变化，bin与全部贴图逐byte同旧冻结版本，60帧数值验证通过。新的glTF没有另做UE导入；上述UE候选由已实测FullUV资产复制而成。旧 C 对照 manifest/material 和原候选均保留其基线身份。

## 当前安装与新验证结果

`Validation/environment_engine_reply_20261020.json` 确认当前 UE 5.8.4 必要文件存在、Launcher 的 incomplete=false；仍未发现完整 MSVC/Windows SDK，vswhere 也不可用，因此编译器发现不完整。此次只做文件/组件检查，没有安装软件、启动新编辑器或重复失败构建。之前的 UE 5.8.3 验证不自动覆盖 5.8.4。

Aya 独立 FullUV 候选已实际重建并在独立 RHI 进程读回。三帧的转换结果全部 UV 保留原 F32 值，消除了之前最大 0.000213623046875 的 FP16 损失；10347 个位置样本与旧候选逐 byte 相同。根独立验证直接解码冻结 glTF/bin 核对，报告为 `Validation/native_render_data_runs/3a5b71bdf90d4ba9af564917577ff0a7/root_independent_full_uv_verification.json`。重复面与 16 面身份歧义仍保留，未称全量 GPU 保真。

旧 D3D11 离屏图像 run01e0bdc53e704bf1b8f63944bf63f62e 实际 engine_version 为5.8.4，记录了 frame0/30、前后两机位共四张。该旧基线的反面近似正面镜像；上面的新单面材质A/B已改善这个问题，旧图与报告保留。原版三份 GE 记录的318次Aya draw光照输入见 `../psp_parse/docs/AYA_GE_LIGHTING_STATE_20261020.md`，对应原版三灯着色仍未实现。

## 已有代码与数据

- `T3BRemake.uproject`、C++ runtime/editor targets、`T3BReplayGameMode` 和 `T3BReplayWorld`。
- 原街景：140 draws、31,656 vertices、81 render-material states；材质、UV、顶点 RGBA 与原始相对位置保留。
- Aya、真实枪械与原版异形：三组 60 个原始时间样本；身体和武器共享已验证时间轴，异形来自独立 capture。
- `Content/SourceData/`：4 份逐字节相同的原版 binary、76 张无损 RGBA PNG、84 个材质绑定和 provenance manifest。不是高清贴图重建。
- 引擎无关 C++ reader/affine skinning 已实测：57 项检查通过，329,940 个动作点与冻结 C probes 逐 bit 相同，街景全部 position/UV/RGBA 保留原始位。

`T3BReplayWorld` 通过 ProceduralMesh 桥接原始 affine 矩阵。它是供原版数据验收的 UE replay，尚未移植 C 原型的射击、碰撞、AI 与 Overdive，也不是最终生产角色的 native Skeletal Mesh 管线。

## 原生骨骼迁移的新证据

[原始60帧/44骨的local SRT报告](../psp_parse/out/AYA_LOCAL_SRT_FEASIBILITY_20261020.md) 已独立检查2640个骨骼样本：local矩阵未见显著shear，SRT最大分量残差约1.03e-7。原quaternion非单位化，其旋转矩阵为 `||q||² R(q/||q||)`；原生导入必须保留这部分uniform scale，不能直接normalize并设scale=1。

这份数学报告支持 native SkeletalMesh 迁移；当前正式 runtime 仍是 affine ProceduralMesh 桥接。原生交换资产须明确处理两个 root、原权重总和略低于 1 和 GE float24 截断，更多动作仍需恢复。数学可行性不能代替真实 UE 蒙皮和画面验收。不要把 GE skinning 矩阵直接当作骨骼 local transform。

原生候选现已实际导入 UE，并通过第二进程只读重载：`Validation/native_import_runs/64e9826c75854a7ba8f7f36eabefb4cf/README.md` 给出完整资产路径与复现命令。新增 SkeletalMesh、Skeleton、AnimSequence 共 3 包；45 骨骼包括 44 原 source bones 和 synthetic root，全部原父层级保留，60 个动画 keys，长度差约 7.39 μs。唯一 slot 实际绑定已验证的 `M_Aya_000`；原 161 包与新 3 包重载前后 SHA 不变。真实参考姿势与转换后的 glTF local TRS 最大平移分量差约 0.000513 cm，scale 也已保留。

该候选尚未替换正式 replay。原生 importer 的坐标为 `(pc.x,pc.z,pc.y)*100`，PMC 为 `(pc.z,pc.x,pc.y)*100`，相对变换是 X/Y reflection，不能只调 yaw 宣称对齐。UE 原生 render-buffer 蒙皮顶点、GPU 渲染、原 draw order/depth-write 和战斗仍需验收。首次 glTF 自动材质生成因内置 `MF_Unlit_Body` 的 AlphaMode 输入报错而失败，日志保留；成功路径关闭自动材质生成，再按实际 slot 绑定已验证的原材质。

真实 UE **SourceModel CPU 蒙皮**现已有 60 帧、207360 点的读回与对照。`GeometryScript` 路径实际使用组件动画变换调用 `FSkeletalMeshOperations::GetPosedMesh`；临时 actor 的 yaw90 + scale(1,-1,1) 实现完整 X/Y reflection，实际 world-copy 与交换矩阵最大差约 2.13e-14 cm。默认采样对冻结 C 的最大点差约 0.08124 cm；独立进程强制 raw 动画的受控实验降至 0.02133 cm，源/资产/时间/拓扑/参考均保持一致。完整结果在 `Validation/native_skinning_probe_runs/{c64431c073744987b3bcb7965caa3a92,48c1c01b67ae420290c829a9da5317b3}/README.md`。

这次只验证 SourceModel CPU 变形；NullRHI 的 RenderData 路径无法取得 MeshObject，GPU/render-buffer 尚未验收。反射后的前 12 个三角形绕序及 split-normal 得到实测确认，未扩大为全部切线/像素验收。`a.ForceEvalRawData` 是本机源码 `WITH_EDITOR` 条件内的控制，不能直接用作 cooked 游戏的保真方案。剩余误差包含未完全隔离的统一采样网格、源权重与 float 等因素，不能全部归因某个 ACL 参数。

独立 compact 候选已实际解决导入副本问题：每 primitive 改为局部 attribute accessor 后，真实 UE SourceModel 总点数从 366336 降为 3456，未引用点从 362880 降为 0，1152 个三角形及全部原属性保留。独立新进程在同一 raw 策略下测得的 60 帧 local/aligned 点文件与旧候选逐 byte 相同，误差无劣化；正式 PMC 和旧包未改。新候选位于 `/Game/T3B/NativeCandidates/AyaCompact/Run_fbcb0ef145134ee58227c6c44f4835cb/`，完整证据见 `../psp_parse/out/AYA_NATIVE_COMPACT_20261020/README.md`。

另一次真实 D3D11 离屏 commandlet 已取得 RenderData→原生 CPU skinning→DynamicMesh 的 3 帧数据，见 `Validation/native_render_data_runs/550c3d234d124e0382d260212efc1d35/README.md`。转换输出为 3449 点/1151 面，完整 UV 对应显示 FP16 精度损失，少一个非退化重复面 multiplicity；该转换层会跳过重复面，尚不能断定原始 LOD buffer 删除了该面。严格对应的1135面相对冻结 C 最大位置差约0.03888cm，另16面身份仍是推断。此工作没有认证全量 raw render-buffer、GPU 顶点/像素或 draw-order/depth-write 等价。

## 本机构建与资产导入状态

本机引擎目录为 `C:\Program Files\Epic Games\UE_5.8`，现代 Launcher `.item` manifest 的 `bIsIncompleteInstall=false`。首次实际构建日志见 `Validation/first_unreal_build.log`：UnrealBuildTool 报 `Sdk: not found. Required version 10.0.19041.0`，Build.bat 返回 6。需要先补齐兼容的 Windows C++ 工具链和 SDK，再重试正式工程；本次没有安装系统组件。构建脚本要求显式提供引擎目录，不下载或重装引擎。

`Tools/check_environment.ps1` 检查引擎文件、Launcher 注册、MSVC 与 Windows SDK。它只做文件/组件发现，不安装软件或启动编辑器；报告不能代替 UnrealBuildTool 编译验收。当前 `Validation/environment_inventory.json` 确认必要引擎文件存在，MSVC/SDK 尚未发现，VS 查询器也未发现，因此编译器搜索仍不完整。

[UE 5.8 官方开发环境要求](https://dev.epicgames.com/documentation/en-us/unreal-engine/setting-up-visual-studio-development-environment-for-cplusplus-projects-in-unreal-engine)：通用开发推荐 VS 2026 18.0+，也支持 VS 2022 17.14+；安装 C++ 游戏开发工作负载及兼容 MSVC、Windows SDK。最终以本机 UnrealBuildTool 的诊断为准。

在本目录执行：

```powershell
& .\Tools\check_environment.ps1 -EngineRoot 'C:\Program Files\Epic Games\UE_5.8' -ReportPath '.\Validation\environment_inventory.json'
python -X utf8 Tools/stage_source_bundle.py
python -X utf8 Tools/verify_source_bundle.py
& .\Tools\build_unreal.ps1 -EngineRoot 'C:\Program Files\Epic Games\UE_5.8'
& .\Tools\run_editor.ps1 -EngineRoot 'C:\Program Files\Epic Games\UE_5.8' -ImportSourceAssets
```

无需 C++ 构建的 content-only host `T3BAssetImport.uproject` 与正式工程共享 Content。实际命令如下，采用隐藏的 `UnrealEditor-Cmd -unattended -NullRHI`，不打开桌面编辑器：

```powershell
& .\Tools\import_source_assets_headless.ps1 -EngineRoot 'C:\Program Files\Epic Games\UE_5.8'
```

运行 `0fac54502ca140d4accffa2e5a7bc618` 已成功保存 76 张原始分辨率纹理、84 个基线材质，以及空的 `/Game/T3B/Maps/M1_SourceReplay`。`Validation/asset_import_runs/0fac54502ca140d4accffa2e5a7bc618/verified.json` 核对本次 PID/run_id、输入 hash 和全部 161 个包的文件大小/SHA。先前两个失败运行日志保留；实际 UE 源码确认并修复了 Coordinates→UVs 和 VertexColor 空输出名的 API 差异。此结果不证明 shader、像素、角色或战斗已运行。

第二个真实 UE 进程已只读重新加载这些资产，验收报告为 `Validation/asset_reload_runs/c1994df2f25e40d89f80b978a8f731cc/verified.json`：76 个 Texture2D 的尺寸/alpha/采样与 metadata、84 个 Material 的签名/UV/颜色/严格 alpha 判定和 1204 条图连接全部核对，1 个空 World 成功加载，所需包引用存在，161 个文件前后 SHA 不变。运行日志为 0 errors / 0 warnings。检查脚本不会重新导入或保存原包：

```powershell
& .\Tools\verify_source_assets_headless.ps1 -EngineRoot 'C:\Program Files\Epic Games\UE_5.8'
```

该验收范围是保存后的资产结构与依赖，仍未运行 C++ replay、GPU 像素或战斗。

另一次真实 UE 进程通过 `TextureExporterPNG` 从保存后的 Texture2D source art 导出全部 76 张 PNG；外部 Python/Pillow 独立解码后，RGBA（含 alpha 和透明像素中的 RGB）与原始 staging 逐字节相同。报告为 `Validation/texture_roundtrip_runs/70d48c64a961495bb7017679bb9c3a31/verified.json`，161 个原包未改变。这证明资产中的 source art 保留，不能替代 GPU 压缩/采样和 shader 画面验证。

```powershell
python -X utf8 Tools/verify_texture_source_roundtrip.py --engine-root 'C:\Program Files\Epic Games\UE_5.8'
```

进入关卡 Play 后，GameMode 创建唯一 replay actor 与观察用 Spectator。Console commands：

```text
T3B.Replay.Pause 1
T3B.Replay.Seek 0.5
T3B.Replay.Probe
```

最后一条读取真实 procedural component 的 CPU vertex buffer/world positions，写入 `Saved/SourceReplay/` 和本次 probe metadata；随后执行：

```powershell
python -X utf8 Tools/verify_unreal_replay.py
```

没有真实 UE 输出时，该验证器会拒绝验收。CPU world-position 验证也不能替代 GPU 像素、材质和可玩验证。

## 渲染差异与后续验收

标准 UE Translucent 材质尚不能重现原版 23 个街景 draw 的混合加主深度写入；3 个角色材质也存在相同问题。总共 11 个材质状态明确记录在 manifest 的 `unsupported_render_states`。CustomDepth 和 velocity depth 不能代替主深度。

场景原始 RGBA、float UV/repeat、alpha>0 数学判定已保留。实际 UE 绕序、透明排序、纹理采样、顶点颜色量化和输出色彩仍需匹配机位验证。原版 fog/stencil、全部动作/AI/碰撞格式、章节与高清资产继续解析与制作。

## 证据

- `Validation/source_bundle_staging.json`：binary/PNG staging。
- `Validation/source_bundle_independent_verification.json`：84 个材质绑定、RGBA、sampler、flags 与配对时间轴的独立复核。
- `Tools/source_core_verification.json`、`Tools/README.md`：真实 standalone C++ 构建、57 项检查和全部冻结 C probes 对照。
- `Docs/UE_MATERIAL_IMPORT_CONTRACT.md`：官方 API 与渲染状态边界。
- `../psp_parse/docs/CONTINUATION_CHECKPOINT.md`：完整解析工作检查点。

正式引擎选择依据见 `../t3b_hd/docs/ENGINE_DECISION.md`。旧 C 原型位于 `../t3b_hd/`，用于 source 与可玩行为对照。
## 最新：原版 GE 矩阵模式 0/1 已进入 production core

新增 `T3BGEOriginalMatrix.h/.cpp`，按已冻结的原版 opcode 顺序实现 mode0/1：F32 非融合矩阵乘、`f12` 与 `P+30.xyz` 缩放、effective parent、global basis、translation 与前三列 bottom-row 清零。独立 probe + Python reference 已通过 2/2 cases、32/32 words bit-exact；再用同一 PPSSPP 运行的真实 matrix input/p60/global/state sidecar 对 6 个 retained stages、96/96 words bit-exact，证据见 [original_matrix_core_v1](Validation/original_matrix_core_v1/verification.json) 与 [actual_sidecar_verification](Validation/original_matrix_core_v1/actual_sidecar_verification.json)。

该回归使用 non-commuting synthetic matrices；已有 PPSSPP `actual_v3` 的真实矩阵阶段仍是独立证据，本轮没有虚构缺失 input sidecar，也没有把 mode2/6 接到 UE。正式 UE 构建仍受 MSVC/Windows SDK 安装终态限制。

## 最新：Aya HD 材质候选（非生产）

保留原始 256² atlas，并生成了独立的 AI-enhanced、UV-safe 和 detail-only 保守候选：[aya_506dc44780fe0539_hd_uvsafe_candidate.png](Content/SourceData/textures/aya_506dc44780fe0539_hd_uvsafe_candidate.png)、[aya_506dc44780fe0539_hd_conservative_candidate.png](Content/SourceData/textures/aya_506dc44780fe0539_hd_conservative_candidate.png)。UV-safe 版本的原 atlas occupancy mask nearest round-trip exact；保守版本下采样仍有 123 的最大通道误差，且 face identity 未验证，gate 仍为 `review_required`，没有接入默认 M1 或替换原材质。审计见 [aya_hd_texture_candidate_v1.json](Validation/aya_hd_texture_candidate_v1.json)。

## 最新：UE source bundle reader/skin 独立 gate 通过

在没有 MSVC/UE editor 的情况下，使用同一份 `T3BSourceData` C++ 实现做了独立 probe：[source_bundle_probe_v1.json](Validation/source_bundle_probe_v1.json)。原街景、Aya、武器和 Twisted 的数量契约及全部 60 个保存姿态均通过 raw affine skinning 检查；这为后续正式 UE import 提供了可复核的输入 gate。

这不是 UE build 或 editor render 验收；原始资源和 bundle hash 保持不变。

## 最新：UE SourceData 与 M1 输入已逐项对齐

[source_bundle_runtime_identity_v1.json](Validation/source_bundle_runtime_identity_v1.json) 验证 scene、Aya、weapon、Twisted 四组 UE source binaries 与已通过 M1 C/SDL2 runtime 的输入逐字节一致。该 gate 覆盖输入身份，不替代正式 UE build 或 editor render。

## 最新：SourceData manifest 完整性 gate 通过

[source_bundle_manifest_v1.json](Validation/source_bundle_manifest_v1.json) 已检查 manifest 的 staged outputs、84 个 provenance inputs、76 张 RGBA texture 的尺寸与 hash，以及 scene/Aya/weapon/Twisted 二进制 header/counts。UE editor import/render 仍待正式工具链。



### FSD index probe

Private/T3BFSDIndex.* 和 Tools/fsd_index_probe.cpp 现在可独立读取 raw/3rd.fsd 的已验证结构：761 条 8-byte record、0x730 起始、sentinel=1。报告见 Validation/fsd_index_probe_v1.json。第二字段保持 opaque，未赋予 room/entity/package 语义。



FSD 原始输入已加入 Content/SourceData/raw/3rd.fsd。SourceData manifest gate 和 [fsd_source_bundle_identity_v1.json](Validation/fsd_source_bundle_identity_v1.json) 均通过，源文件与 staged 文件逐字节一致。



FSD reader negative verification 已通过：坏 version/tag/sentinel/截断输入全部拒绝，报告见 Validation/fsd_index_probe_verification_v1.json。



### approach_fire action clip

SourceData 额外 staged models/aya_approach_fire.bin 与 models/weapon_approach_fire.bin，对应已验证的 C runtime approach_fire pair；逐字节 identity 见 Validation/action_clip_source_bundle_v1.json。



T3BActionClip 已提供 engine-independent synchronized pair validator；approach_fire SourceData probe 通过 44/1 bones、3456/243 vertices 和 60-frame equal time axis。报告见 Validation/action_clip_probe_v1.json。



### 2026-10-21 UE Game target build

工具链安装已完成：Visual Studio Build Tools 2022、MSVC 14.44.35207、Windows SDK 10.0.22621.0。将同一 source tree 非破坏性复制到 ASCII 路径后，UE 5.8 `T3BRemake Win64 Development` 完成 35/35 actions，包含 UHT、C++ compile/link，输出路径和 hash 见 [ue_game_build_t3bremake_v1.json](Validation/ue_game_build_t3bremake_v1.json)。中文工作区源工程保持不替换。Editor target 仍未验收：它额外依赖 SwarmInterface 所需的 .NET Framework SDK。

### 2026-10-21 action clip negative verification

`verify_action_clip_probe.py` 已通过 valid、truncated weapon、mismatched body 三个 case：合法 pair exit=0，截断输入与不同 sample-time 输入均 exit=1。报告见 [action_clip_probe_verification_v1.json](Validation/action_clip_probe_verification_v1.json)。


### 2026-10-21 UE action clip runtime switch

`AT3BReplayWorld` 现在读取 manifest 的 `action_clips`，用 `T3BAction::LoadSynchronizedPair` 验证 staged `approach_fire`，并提供 `T3B.Replay.ActionClip approach_fire` / `reference` 切换。默认仍是 manifest actor 的 reference clip；这只是 SourceData visual replay 的显式动作预览，不把它声明为原版 gameplay state machine。UE Game target 35/35 build 证据见 [ue_game_build_actionclip_v1.json](Validation/ue_game_build_actionclip_v1.json)。


### 2026-10-21 Aya source-bone role audit

新增 [AYA_SOURCE_BONE_ROLE_AUDIT_20261021.json](../psp_parse/out/AYA_SOURCE_BONE_ROLE_AUDIT_20261021.json)：将 44 个 source record 按冻结 hierarchy 与 draw/palette metadata 分为 35 个 directly weighted、4 个 weighted-bone ancestor、5 个 other nonweighted。该报告只描述结构角色，不推断 anatomy name；9 个没有同帧 GE mapping 的 index 仍未接入。


### 2026-10-21 CLUT capture coverage audit

将工作区保存的 17 个 frame-capture root、264 个 `frame_*.ppdmp` 全部重新输入 CLUT/TEXTURE0 matcher。重新去重后仍为 206 个 runtime payload、84 个 exact/subsequence 命中、122 个未命中；与原报告的 signature set 完全一致，新增命中为 0。证据见 [RUNTIME_CLUT_CAPTURE_COVERAGE_VERIFICATION_20261021.json](../psp_parse/out/RUNTIME_CLUT_CAPTURE_COVERAGE_VERIFICATION_20261021.json)。


### 2026-10-21 original weapon marker SourceData

已将通过原版 marker contract 的 208-byte `T3BWMK1`（source index 1/2）staged 为 `Content/SourceData/models/weapon_source_markers.bin`。`AT3BReplayWorld` 加载 manifest 时实际调用 `T3BGE::LoadWeaponMarkers` 校验该数据；UE Game target 35/35 build 通过。该数据只证明原 source marker 矩阵，仍没有赋予 gameplay socket 或 muzzle 的语义名称。证据见 [weapon_marker_source_bundle_v1.json](Validation/weapon_marker_source_bundle_v1.json)、[ue_game_build_weapon_marker_v1.json](Validation/ue_game_build_weapon_marker_v1.json)。


Marker bundle now links to the independent original-runtime verification: 12 samples, 2 markers/sample, max F64 matrix/direction error `1.11e-16`, and 5 negative controls. The shared source-marker SHA is checked before the UE SourceData entry is accepted.


### 2026-10-21 runtime marker probe output

`T3B.Replay.Probe` 现在在读取 SourceData marker 后写出 `Saved/SourceReplay/weapon_markers.json`，包含 source1/2、原始 weight、3x4 GE root 和两组 local matrix；输出明确写入 `semantic_names_inferred=false`。序列化路径已通过 UE Game target 35/35 编译。


### 2026-10-21 Game runtime smoke boundary

用 Game target 启动 `M1_SourceReplay`、Null RHI 和 `T3B.Replay.Probe` 时，UE 在 loose/未 cooking map 加载阶段触发 `FBufferReader` 越界断言（exit 3）；因此没有把 `weapon_markers.json` 运行输出标成已验证。下一步需要 Editor 或 cooked map 验证。报告见 [ue_game_runtime_smoke_v1.json](Validation/ue_game_runtime_smoke_v1.json)。
