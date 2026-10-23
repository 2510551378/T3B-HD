# UE 原生3D GE按序混合／主深度pass：实现待实际编译

2026-10-21。已实现UE侧3D replay actor、view extension及RDG pass，并把生产数据读取／像素组合核心接到实际D3D11参考重新验证。**UE module尚未通过UBT，也没有本阶段的实际UE画面；不能称UE遮挡修复已完成。** 完整M1／高清重制继续未完成。

## 代码职责与约束

| 文件 | 职责 |
|---|---|
| Public/T3BGEGeometry.h、Private/T3BGEGeometry.cpp | 读取已导出的T3BGPU1 compatibility geometry，保留纹理、107个原draw顺序和9F32顶点布局；不把它称为原PSP文件格式 |
| Public/T3BGEReplayActor.h、Private/T3BGEReplayActor.cpp | 创建两张原RGBA transient纹理，按捕获sample提交世界3D顶点；支持actor平移／旋转，明确限制unit scale |
| Private/T3BGEViewExtension.h/.cpp | 同world桌面view的PrePostProcess RDG pass，绑定实际SceneColor与SceneDepth，逐draw执行原alpha blend＋main-depth write |
| Shaders/Private/T3BGECommon.ush | 与native参考共享的MODULATE／RGBdouble／alpha-test组合函数 |
| Shaders/Private/T3BGEOrdered.usf | UE世界位置→当前View的WorldToClip、PreExposure、颜色与draw-owner输出 |

所有路径相对于 `work/t3b_unreal/Source/T3BRemake/`，shader相对于 `work/t3b_unreal/`。

actor加载真正的3D顶点、UV、primary colors和两张原atlas；不加载生成的PNG回放画面作为贴片。输入目前为已验证的12个同GE样本，每帧body106draws＋gun1draw，共3699点／1233面。原draw顺序由文件保留：首帧身体→枪，其余枪→身体。

`bSourceReady`只表示数据读取成功，不表示shader执行／渲染验收成功。默认不自动播放；`SetCapturedSample`选精确样本。可选均匀30fps只为预览，不宣称原动画时钟，不做循环／插值推断。原同帧武器WORLD已烘焙在3D样本中，本阶段不添加猜测socket或枪口。

颜色仍是捕获时的GE顶点光照重建；actor移动不等于恢复了新位置上的原游戏动态灯光系统。比例和共用固定origin来自前阶段校准，后续接完整场景／碰撞还须验证原根节点与地面锚点。

## 渲染实现

- 顶点stream严格为position3／UV2／color4，共36bytes。公开数据struct没有FVector4对齐带来的padding。
- 游戏线程生成不可变frame，通过render command发布；texture初始化先入队，在render thread抓取并保留RHI引用。RDG声明vertex、两张atlas以及color/depth读写依赖。
- world-view矩阵直接来自实际UE ViewInfo，HLSL明确row_major。shader是3D投影，支持自由相机，未嵌入校准PNG或只对一个画面做修补。
- 逐draw源alpha混合、RGB-only写颜色、GREATER_EQUAL主深度写入。owner R32_UINT MRT不混合。单面剔除跟随UE view的reverse-culling标记。
- shader在UE HDR scene color中使用PreExposure。HDR混合精度、tone mapping与PSP8bit逐次舍入不同，尚未认证输出像素等价。
- `r.T3BGE.DepthWrite`默认1；0仅用于受控不写深度对照。RDG depth access和RHI depth state同时切换。
- pass在UE普通透明之后、postprocessing之前执行。因此与其他普通透明对象的全场景顺序、motion vectors/TAA及完整场景融合尚未恢复；不能直接称默认M1完成。

现阶段明确限于单sample桌面SM5及以上、两张atlas、观察到的blend/cull/depth契约；没有假定支持mobile／MSAA／VR或原fog/stencil。actor自有view extension尚不实现通用PrimitiveSceneProxy的show-only／visibility规则。安装后先在清空场景中验证，再决定M1替换。

原 `T3BReplayWorld` 默认绑定、native骨骼候选和现有资产没有被替换。新actor为opt-in，避免未经UE运行验收就改变默认画面。

## Module与shader注册

`T3BRemake.Build.cs`增加RenderCore／RHI／Renderer；使用本机UE5.8 Renderer的Private/Internal头文件。该接口依赖明确是5.8版本相关，不能据头文件阅读称ABI已验证。

主module改为PostConfigInit，以便global shader类型在引擎shader初始化之前注册；StartupModule映射 `/T3B` 到项目Shaders目录。cooked data模式不要求物理shader源码目录。真实UBT、shader编译、cooked包与Live Coding行为仍待验证。

## 已实际执行的验证

新native GPU运行：

`Validation/ge_depth_reference_runs/6bb0e3db0bcd40cb98ba9f66aceae654/`

该运行由真实g++编译生产 `T3BGEGeometry.cpp/.h`；native reference已删除自己的独立读取循环，使用这个生产loader。native shader由原reference wrapper与UE `T3BGECommon.ush`共同组成，实际D3DCompile／D3D11硬件执行。

PID82312自然exit0，实际RTX2080Ti，48个原几何采集＋4个明确synthetic控制。与先前ac1f31独立native基线逐文件比较：**52次采集×3种GPU Map缓冲区＝156份原始bytes全部相同**。新的root独立GPU审计仍通过，depth干预统计不变。

9个损坏输入实际拒绝：magic、atlas count、texture ID、draw ordinal、非三角形vertex count、非有限位置、超过1的primary color、截断及trailing bytes。生产loader检查尺寸、计数、有限数与颜色范围，并在分配／绘制之前拒绝不完整数据。

`production_core_gpu_parity.json`保存逐byte比较和9次拒绝结果，`root_independent_verification.json`保存原GPU颜色／深度／owner核对。该证据覆盖生产loader和共享像素组合函数，不覆盖尚未编译的UE actor生命周期、WorldToClip包装、transient texture上传或RDG接入。

## 已准备但未执行的真实UE验收

- `Tools/capture_ge_ordered_pass.py`：真实加载新C++actor，12样本、±Y、depth0/1，48张实际PNG＋hidden controls；导出actor的submitted-frame数据。
- `Tools/capture_ge_ordered_pass_headless.py`：缺少实际 `UnrealEditor-T3BRemake.dll` 就拒绝启动；之后用真正T3BRemake.uproject／D3D11，冻结producer并保留process handle、DLL及当前源码身份。
- `Tools/verify_ue_ordered_ge_pass.py`：未来只审计真实成功运行，独立解析原bundle与submitted bytes，检查纹理索引／draw顺序、actor/camera transform、前景和depth干预图片差异。

三个Python文件只通过普通Python语法编译，**没有在UE里运行，没有生成UE验收成功报告**。submitted-frame是CPU提交内容，不是GPU vertex readback；未来图片检查也不会自动认证原PSP像素或全M1。

尚待原GPU depth readback／RHI状态诊断、原camera/fog/stencil和正式战斗验收。不要用脚本存在、source-ready或一个绿色acquisition标记替代这些要求。

## 当前构建前提

MSVC/Windows SDK安装确认仍待用户明确回答；本轮复查常见路径未发现正式组合，也没有下载安装器或执行安装。方案在 `Validation/toolchain_install_plan_20261020.json`。不把自动goal续行或日期更新当成授权，不重复提问。

获准安装或用户自行装好之后，应先fresh核版本和SDK头／库／rc，再执行真正UBT并解决实际诊断。当前不重复缺失依赖下的失败构建，不用假UE头文件或替代编译来宣称UE module通过。
