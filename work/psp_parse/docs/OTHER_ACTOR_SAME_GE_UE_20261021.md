# 原版异形与 Aya／枪械／街景：实际 UE 同帧回放

UE 5.8.4（CL 58902052）D3D11 content-only run `40fedc9fa49f4ad3ab9660645c77717e`，PID 87112 自然退出 0。12 组同份 GE 捕获中的原版异形，现已和 Aya、真实枪械、已匹配街景实例集在 UE 实际同屏渲染。数据接入检查通过；视觉／正式 M1 验收尚未通过。

## 实现

`capture_weapon_ge_paired_headless.py` 新增显式 `--other-actor-runtime`，要求已有 source cameras、street series 与可复用的武器材质；默认旧模式保留。wrapper 冻结并运行 producer／camera／street／actor helpers，持有隐藏 UnrealEditor-Cmd 进程并记录终态。新 `ge_other_actor_capture.py` 读取上一轮实际生产 skin/light 运行证明，严格要求全部 12 份 capture 身份与 Aya／枪械一致。

UE 使用 28 个临时 DynamicMesh 组件按原 packet 更新位置、normal、primary color；原 UV／三角顺序保留。每组 1,800 顶点，共 21,600 顶点读回。组件 identity transform，不额外将异形居中、抬高或跟随 Aya；原 WORLD 已体现在生产 kernel 的 world positions 中。原 draw group 在全部样本中都早于 Aya 和枪械，组件 priority 为 -100..-73，晚于街景、早于角色／枪械。它是原捕获姿态的 geometry replay，不是已导入 UE SkeletalMesh／AnimationSequence，也没有恢复 authored 动作时钟或 AI。

旧 `M_Twisted_000` 为双面材质（旧 source bundle cull=0）；当前捕获的 336 次原异形 draw 均 cull enabled=1。新建单独 `M_Creature_SourceCull` 候选，将 two_sided 改为 false，保持原透明／unlit graph 和原 texture。仅新增 1 个候选 uasset，旧材质与 184 个旧 UE packages 没有修改。新候选路径为 `/Game/T3B/NativeCandidates/OtherActorGEPaired/Run_40fedc9fa49f4ad3ab9660645c77717e/M_Creature_SourceCull`。

## 实际检查

- 新 `verify_ue_other_actor.py` 检查全部 336 draw／21,600 个实际组件点，position F64、normal／color F32 bits 同生产输出，UV bits 和三角顺序／重数同原输入；readback 流无跳过、重叠或尾部数据。
- 实际异形 Texture2D Source 导出的 256×256 RGBA 与该批捕获的有效原 CLUT 解码逐 byte 相同，原贴图保持 linear。新 material 实际使用该 Texture2D、原透明／unlit 属性，组件绑定该单面候选。
- 复跑 source-camera auditor：72 个独立 GPU marker checks 通过，最大误差 0.548436 PSP 像素，上限 1 像素。marker 位于 Aya 原采样顶点；它证明实际相机投影，没有宣称读回异形的实际 GPU skinning 顶点。
- 街景独立 auditor 通过 1,568 draws／358,488 点、73 个实际 Texture2D Source。同新异形隐藏时，12组 × body_only／weapon_only／combined／street_only／street_with_aya_weapon 共 60 张图，与此前已接受的街景基线逐像素相同。
- 新 12 张异形单独图和 12 张全部角色同屏图实际生成。异形单独可见 3,382–8,929 像素，加入异形后完整场景改变 3,032–8,804 像素（大于 1 LSB）。root 查看 sample0 同屏图与全部 `OTHER_ACTOR_CONTACT_SHEET`。
- 全 run 共 97 张实际场景／控制 PNG，75 张 Texture2D Source PNG，另有 3 张检查联系表。正式图像不贴回场景冒充 3D。
- 原 ISO、用户 slot0、ppsspp.ini 和 184 个旧 UE packages 在 run 结束后再次 hash 全同；新增材质包的实际 hash 单列保留。没有启动 PPSSPP 或重试系统安装。

## 仍未完成

当前普通 UE translucent 路径没有实现原版逐 draw 主深度写入。实际截图中 Aya 背面露出正面／手臂透体等已知错误仍可见，不能把数据检查通过称为画面修复。UE 回放仍用此前已匹配的街景集；新增独立背景相机与 fog／stencil 子集仅在 native reference 中实现。当前没有完整 PSP 栅格／D16 depth／framebuffer alpha-stencil 等价结果。

正式 UE C++ pass 尚未编译／加载；MSVC／Windows SDK 安装因先前 Windows 提权取消仍未解决，已有用户授权与 UAC 诊断待回复，不重复启动安装。新数据没有替换默认 M1，也没有完成敌人 AI、原伤害／受击／倒地、原碰撞、精确动作时钟、命名手骨／枪口或高清材质。完整高清重制目标保持 active。

下一步需推进真正的 UE 渲染适配和原战斗行为，避免在本轮已通过的姿态／图像子集上反复跑同一验证。工具链尚不可用时，可继续从保留原捕获恢复 FX／命中路径或原时钟证据。

[实际 UE 手动预览](../../t3b_unreal/Validation/other_actor_paired_ue_runs/40fedc9fa49f4ad3ab9660645c77717e/PREVIEW.html) · [异形独立检查](../../t3b_unreal/Validation/other_actor_paired_ue_runs/40fedc9fa49f4ad3ab9660645c77717e/independent_other_actor_verification.json) · [原文件保护](../../t3b_unreal/Validation/other_actor_paired_ue_runs/40fedc9fa49f4ad3ab9660645c77717e/source_protection.json)
