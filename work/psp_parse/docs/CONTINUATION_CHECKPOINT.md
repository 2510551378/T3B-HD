> GitHub 协作入口：[../../../README.md](../../../README.md)，当前状态见 [../../../docs/CURRENT_STATUS.md](../../../docs/CURRENT_STATUS.md)。下文保留各阶段历史记录；本机数据路径不随 Git 发布。

## 最新：HD sampling A/B 截图已冻结

同一 `inspect-aya` 场景的原 atlas/4x sampling side-by-side 已生成：`work/t3b_hd/build/m1_hd_sampling_ab.png`，比较报告 `m1_hd_sampling_ab.json`。1920×1080 截图的变化区域约 0.804%，difference bbox 落在 Aya/weapon 区域（x=748..1024，y=307..877），未观察到场景/姿态整体漂移；这仍是 C/SDL2 A/B，不是 UE render 验收。

## 最新：M1 HD sampling 已有独立可运行入口

新增 `work/t3b_hd/run_m1_hd_sampling.ps1` 与 `build/m1_hd_sampling_package_v1.json`。脚本实际运行 `--hd-sampling --test-source-spawn` exit 0，4 次命中、敌人死亡、枪口方向 norm=1。资产清单和 hash 已冻结；默认原版路径仍不变，正式 UE5 仍是独立待验收目标。

## 最新：C/SDL2 M1 新增可选 4x 原 atlas sampling 路径

为推进高清化但不污染原版校验源，新增 `--hd-sampling`：Aya 256² atlas 与 64² weapon atlas 各生成独立 Lanczos 4x BMP，alpha 使用原图 nearest 保持裁切边界，默认运行路径仍使用原分辨率。HD sampling 实际 source-spawn 回归通过（4 hits、enemy dead、muzzle norm=1、exit 0），`--test-source-clips --hd-sampling` 也通过 source pair、manifest、transition、clamp 和 sync checks。截图与审计见 `work/t3b_hd/build/hd_sampling_verification.json`。这是采样分辨率提升，不是缺失纹理细节的恢复；当前下采样 mean RGB(A) error 约 4.17、max channel 253，故 status 为 `passed_with_limits`，不宣称像素等价或 UE HD 材质完成。

## 最新：UE SourceData manifest / textures / actor headers 已通过完整 gate

`verify_source_bundle_manifest.py` 已逐项检查 `manifest.json`：84 个 provenance inputs、全部 staged outputs、76 张 PNG 的尺寸与 PNG/RGBA hash、scene header/counts、Aya/weapon/Twisted 的 `T3BSKN2` header/counts/flags。报告为 `work/t3b_unreal/Validation/source_bundle_manifest_v1.json`，status=passed；这一步仍不替代 UE editor import/render。

## 最新：UE SourceData 与已验证 M1 runtime 输入逐项 byte-identical

新增 `work/t3b_unreal/Validation/source_bundle_runtime_identity_v1.json`：scene、Aya fire、weapon fire、Twisted 四组 UE `Content/SourceData` 二进制分别与 C/SDL2 M1 当前使用的 exact inputs 逐字节一致，包含 weapon 的 `weapon_fire_reverse_capture.bin` 对应关系。四组 hash/bytes 全部匹配；这只证明导入输入一致，不等于 UE editor/runtime 已渲染通过。

## 最新：UE source bundle 的 engine-independent reader/skin gate 已通过

正式 UE 工具链仍未安装，但 `T3BSourceData` 已在独立 C++ probe 中编译并运行：当前 source bundle 的原街景 140 draws / 31,656 vertices / 81 materials，Aya 44 bones / 106 packets / 3,456 vertices / 60 poses，weapon 1/1/243/60，Twisted 11/28/1,800/60。所有保存帧都执行了 raw affine `PoseOriginal`，共检查 Aya 207,360、weapon 14,580、Twisted 108,000 posed points，并通过 finite/coverage/coordinate checks。证据见 `work/t3b_unreal/Validation/source_bundle_probe_v1.json`。

这证明 UE import 前的数据 reader 和 affine skinning contract 可独立复现，不等于 UE UHT/RDG/editor render 已通过；原 ISO、存档与 source bundle 输入 hash 未改。

## 最新：真实右手 timeline 已纳入 M1 运行时 provenance，未强行混接 source pair

`aya_true_right_hand_timeline.csv` 的 24 行证据（frame 0–23、source bone 36、GE draw 1037、palette slot 12）现在无论 source-pair 是否可用都会加载。source-pair 正常路径仍只使用同一 capture 的 Aya/weapon transforms；右手 timeline 在本轮实际 source-spawn 回归中 `loaded=1`、`used=0`、`bound=0`，4 次真实网格命中与敌人死亡仍通过。这样把真实数据纳入运行时 provenance，同时避免把不同坐标/采集时序硬混为 active socket。证据见 `work/t3b_hd/build/true_hand_binding_verification.json`。

下一步需要同一 capture 的 hand/source-pair 坐标 join，或原版 writer 的直接矩阵消费证据，才能把 `bound` 从 0 提升；当前不宣称 gameplay socket 已恢复。

## 最新：M1 原版角色／武器／场景运行时回归已在本机实际通过

在 `work/t3b_hd/` 工作目录中直接运行现有 C/SDL2 原型：`--test-original-scene --original-spawn`、`--test-ranged`、`--test-source-spawn` 和 `--inspect-aya` 均 exit 0。原版街景实际加载 140 draws / 31,656 vertices / 10,552 triangles；Aya 44 source bones、1,152 runtime triangles，真实武器 81 triangles，枪口方向 norm=1。远距与原版 spawn 两组测试均为 4 次真实网格命中、enemy_hp=0、enemy_dead=1，并验证 `overdive_seen=1`、`overdive_return=1`。截图和日志冻结在 `work/t3b_hd/build/m1_runtime_validation_20261021/verification.json`。

这确认了当前 C/SDL2 M1 slice 的可运行行为与原版资源接入；正式 UE5 runtime 仍未构建，碰撞是已证明的 visible-static adapter，原版 AI/碰撞/完整状态机尚未恢复。Aya 仍使用原始 256² atlas，HD 候选没有进入运行时。

## 最新：Aya HD 材质候选已生成并冻结为非生产资产

保留原始 `AYA_EXACT_MATERIALS/aya_506dc44780fe0539.png` 不变，新增 AI-enhanced 贴图候选、UV-safe 1024² 版本和 detail-only 保守版本：`work/t3b_unreal/Content/SourceData/textures/aya_506dc44780fe0539_hd_candidate.png`、`aya_506dc44780fe0539_hd_uvsafe_candidate.png`、`aya_506dc44780fe0539_hd_conservative_candidate.png`。UV-safe 版本重新施加原 atlas 的 occupancy mask，nearest round-trip mask exact；原候选下采样 occupancy IoU 为 0.9573，保守版本下采样最大通道误差仍为 123，且 face identity/material-island semantics 尚未验证，因此生产 gate 保持 `candidate_reprojection_approved=false`。审计见 `work/t3b_unreal/Validation/aya_hd_texture_candidate_v1.json`。

该候选只用于后续 UV/渲染对照，未替换原材质、未改 manifest、未接默认 M1；必须先通过同一 Aya mesh 的 UV island 与原 GE 颜色/alpha/深度对照，才能进入 runtime。原 ISO、slot0、INI 与既有资源保持不变。

## 最新：原版 GE 矩阵模式 0/1 已接入独立 production core

本轮把 `WEAPON_GE_MATRIX_MATH_20261020` 已冻结的两条原版路径落成 `T3BGEOriginalMatrix`：mode0 按原 opcode 顺序对前 3 个 input columns 做可选 `f12` F32 缩放后执行完整 `parent * input`；mode1 按 `global.basis * (input.basis * f12 * P+30.xyz)` 计算前三列、以 effective parent 计算 translation，并保留原版对前三列 bottom row 的 `+0` 清零。mode0/1 的 float32 multiply/add 顺序固定为 non-fused。

`original_matrix_core_v1/verification.json` 由独立 Python reference 与 C++ probe 逐字比较通过（2/2 cases、32/32 output words bit-exact）；进一步用同一运行的 `marker_ge_emit` input/p60/globalMatrix、state `+0x30 XYZ`、以及 `actual_v3` 的 mode/f12 作为真实 sidecar 输入，`actual_sidecar_verification.json` 对 6/6 retained stages、96/96 output words 全部 bit-exact。该验证终于形成了真实 input/output join，但只覆盖这 6 个已保留阶段；mode2/6 等未覆盖路径继续拒绝，不能宣称全模式等价。

原 ISO、slot0、INI 与 185 个 UE 包 hash 不变；正式 UE/UHT/RDG 构建仍待 MSVC/SDK，goal active。下一步优先把该 core 对接已有真实 raw register/memory sidecar，或继续恢复矩阵 writer 的同一 draw content join；不把 synthetic regression 当作实际运行时新样本。

## 最新：type23 已接入可选 RCX→VRNDF2 生产路径

前轮progress（VFPU RCX算法恢复、矩阵consumer分离审计）；本轮progress。T3BGEEffectModifiers增加ApplyOriginalType23ModifiersFromRCX：显式接收VFPURCXState，按启用channel顺序每channel生成3个VRNDF2，再走已验证type23算术；默认仍观察vector路径，不替代未知game seed。固定seed0x12345678、6vector bridge实际通过，vfpu_modifier_bridge_v2 checkpoint/snapshots7。

PPSSPP RCX算法本身vfpu_runtime_v5已6seed/kind、48生成bits同；game node RCX seed未采，不能宣称PRNG时间线。type6/type23 N+80与matrix P+60仍分离，未接matrix。原ISO/slot0/INI3+185UE包全SHA同，正式UE/defaultM1未改，goal active。文档FX_VFPU_RCX_20261021.md更新。下一步需在原版debugger能导出RCX或同一VRND caller时采seed，再进行type23完整随机时间链；仍不把默认seed当原版。

## 最新：PPSSPP VFPU RCX 随机算法已恢复（节点seed仍未采集）

前轮progress（type6连续链、矩阵消费者关系审计）；本轮progress。新增T3BGEVfpuRandom.h/.cpp：按固定PPSSPPv1.20.4 MIPSVFPUUtils.cpp逐bit实现vrnd_init_default/seed、A/B/C/D/E解包、LCG69069、B xorshift、Pell-like C/D、E carry与RCX回写，提供VRNDI/VRNDF1/VRNDF2。ge_vfpu_random_probe+verify_vfpu_random_runtime实际6seed/kind cases、48次生成全byte同Python reference；v5 checkpoint source snapshots5。

这只恢复算法/RCX布局，不声称本次游戏节点初始RCX。原type23仍显式消费实际观测VRNDF2 vector；cpu.getAllRegs没有VFPU S/T/D prefix/RCX controls，不能用default或host random代替。文档FX_VFPU_RCX_20261021.md。原ISO/slot0/INI3+185UE package SHA保持。正式UE/M1仍未切换，goal active。

## 最新：type6／type23 共享目标与局部矩阵消费者已分离审计

前轮progress（type6 key/wrap/evaluate连续链）；本轮progress。根out/FX_MATRIX_CONSUMER_MAP_20261021。根据同一key9_state6_v1原属性快照：节点N=097d1d10，type6参数N+80=097d1d90；type23 target lookup同一capture也解析N+80=097d1d90，共享内部状态。type14/type155 parameter alias都是P+60=097d1e80；既有WEAPON_GE_MATRIX_MATH actual_v3 actual retained stages verifier证明matrix helper实际读取P+60并输出GE matrix。N+50是local matrix pointer。

第一次FX_LOCAL_MATRIX matrix3_v1实时尝试实际到达type14 entry和local leaf entry，保存local matrix/angles/scale/position/component indices及代码identity，但下一等待收到external CPU stop，localMatrixCalls=[]，process terminal exit1；没有把它算成功writer或直接join。静态审计明确：type6/type23 N+80不能直接当matrix P+60；可能经type14/共享记录/其他handler间接连接，当前无同一writer content join。生产UE不接此未经证明映射。失败原始JSON/日志保留。

audit_fx_matrix_consumer_map.py/verification.json通过，checkpoint/source_protection/current_tool_snapshots5；原ISO/slot0/INI3+185UE包全SHA同。无UE/安装/Content，defaultM1未改，goal active。文档FX_MATRIX_CONSUMER_MAP_20261021.md。下一步在已知type14/matrix consumer caller上窄化实时stage gate，或用同一GE draw content join，成功前不改矩阵接线；继续恢复VFPU RCX/scheduler/单位/原碰撞伤害。

## 最新：type6 key／wrap／vec4求值与同节点连续状态链已恢复

前轮progress（23/24 target/RNG/modifier）；本轮progress。根out/FX_VECTOR_CURVE_20261021。新增T3BGEEffectVectorCurve.h/.cpp Change/Wrap/Evaluate：state Current/Base/Velocity/Acceleration四vec4；XYZ helper保留W，evaluate全部4lanes，Horner base+((A*(t*.5)+V)*t)，不得强制W0/1。key commonhelper65f48..6616c stateValue确实复用previousKey.A；wrap662e0..664e0+vecadd/sub8bfcff4..d05c先旧时间累计再rebase，新carry A先*.5再*t²，keyBase不直接盖累计。type6 target offset20与23内部target一致，空间/骨骼/角度语义未命名。source_bank_v1导出FEP11690/11930已消费44bytes XYZ keys(0,0,45),(0,0,-40),(0,0,0)，无allocation认领。

observer可选VECTOR_DETAILS保留完整helper runtimecode及dispatch-entry-return；VECTOR_EVAL_ROWS连续函数采样，VECTOR_TRANSITIONS选evaluate/evaluate/wrap两轮，不是游戏调度实现。4采集均terminal exit0、自有BP/input清理/进程停：reset21_vector_v1 session84037/PID98256；key9_vector_random_v1 session11484/PID56060；key9_evaluate6_v1 session81444/PID92888；最终key9_state6_v1 session6351/PID95464。后者同次key9+random23/24+live6state transition，wrap完整原入口f12/f13及new/old key实测，无跨运行拼before-state。

combined_audit_v3原opcode13操作（key1，另一reset捕获wrap3/eval3，同节点eval4/wrap2），208完整状态F32、全512bytes匹配；带stage时SP/RA/initializedVFPU也同。新replay_fx_vector_curve.Machine继承旧finite prefix/swizzle支持，界定4个函数范围。nestedEval由helper最后vsub证明prefixdefault，其他entry仅default-compatible，不冒充直接control读取。runtime_v4实际core13操作208float全bits同+10明确synthetic原opcode cases+6invalid拒绝。runtime_v1真实通过但synthetic wrap因同地址current/previous被合成器覆盖而失败，修独立fake regions后v2通过，production无需修；v3/v4新eval/完整state inputs，旧source保留。

关键continuous_runtime_v1：同exe链接Modifier+VectorCurve，载入一次initial16float与实际VRND输入，做23modifier→4evaluate+2wrap，无每步beforestate输入，7×16float=448bytes同原same-node。例CurrentZ 206.5113831→146.3463135→86.1812439→86.1812439→26.0161743→-34.1488953，W1/2/1/1/2/1。时间仍source units，wrap t0/old2来自本次ABI；normal f13是unused寄存器不当旧时间。原clock Node+30在callback内仍2，随后writer才0。random_audit_v3另核同次23/24/helperseed。negative_evidence_v1三个SHA一致坏样本：oldTime/carry断链/WrapW指定gate拒绝（carry改unusedCurrent也必须reject）。

checkpoint/source_protection/current_tool_snapshots19完成，原ISO/slot0/INI3+185UE包全部SHA同。无UE/Content/安装。正式UE仍toolchain UAC取消，勿无新steering提权；defaultM1未改，goal active。文档FX_VECTOR_CURVE_20261021.md。下一步将真实连续vector状态追到handler局部矩阵/GE命令consumer再接GPU/生产renderer，避免继续重复本数值链；还需scheduler/秒数/VFPU RCX/AI原碰撞伤害/高清化。

## 最新：type23／24 内部目标与随机扰动已恢复，生产 core 实测通过

前轮progress（UE source scene/core/shared shader bridge）；本轮progress。根out/FX_RANDOM_MODIFIERS_20261021。重要解释纠正：definition2/type23 declared+a3 offset60、definition4/type24 offset80的ABI别名仍正确，但callback忽略此目标，重取C+90 node、C+94 active definition，按header+4 index查header+8 u16表，写node+60+offset。实际type23内部target=paramWindow+20（先前type6三分量状态区），type24=+60（百分比/转换区），不是把23当scale/24当color。source_bank_v2导出原44-byte consumed prefix和header/lookup来源与内部offset，不认领allocation。

trace_fx_property_callbacks.js新增可选FX_PROPERTY_RANDOM_DETAILS=1（默认无改）：完整23函数38c/24函数3e8原码identity，逐channel loop/VRND后/ready/advanced、scalar helper entry-return/seed、原lookup/static tables/vectorcache与constants。最终key9_random_v2/session73200/PID97244 exit0，9keycallbacks，23开启channels0/1 mode0，24开启channel0 mode2 independentXYZ，3个LCG调用。单自有BP，清理输入/BP，自有进程停。v1/session85196/PID96940同样terminal exit0但RNG日志文件名复用，hash identity失败，被最终negative明确拒绝；actual executed JS留存，v2加call ordinal修正。

analyze_fx_random_modifiers audit_v1重做base9callbacks绑定/FEP/module/ABI与全sidecar，replay_fx_random_modifiers原opcode逐条执行23=162/24=201指令，中间params/VFPU/stack/RNG seed-return、完整512bytes同实际。VRND依赖显式实际post-VRNDF2输入（RCX controls未恢复），debugscalar->physical layout显式映射；首次loop stack提供未初始化W原input，vone/vzero随后覆盖。LCG原helper08afc000：u32(seed*1103515245+12345)，返回low31；实测bf8665f8→551b2ad1→b2431936→8e046037。type24 converted(2.5,2.5,2.5)→(2.1648917198,1.8926726580,2.5)，percentW1/currentW0。23/24内部偏移不能同ABI参数offset混用。

新增生产T3BGEEffectModifiers.h/.cpp与ge_effect_modifiers_probe：Type23显式VRNDF2/center输入（无替代host RNG），Type24显式seed引用、独立或共用axes、源F32时序，atomic target update。runtime_v2实际2真实callback32目标float bits+seed同；14明确synthetic原opcode cases mode0/1/2/255、axes、channelsdisabled，以及6非法输入通过。runtime_v1发现type23 mode1代码和mode2都是vsub（不同type24正偏移），已按原码修正，旧exe/source/output保留。failed_oracle_v1保留PC字典覆盖bug/后补stack/vzero说明；negative_evidence_v2三个坏证据seed/VRND/internaltarget指定gate拒绝。finalizer_v1期望较晚错误label，实际更早generated-vector gate正确拒绝，修标签用新v2目录。

checkpoint/source_protection/current_tool_snapshots12已冻，原ISO/slot0/INI3+185UE包全SHA同。无新UE/安装/Content；正式UE module、默认M1仍未切换，goal active。文档FX_RANDOM_MODIFIERS_20261021.md。下一步把内部target lookup+modifier连原属性调度/时间状态，恢复type6求值和VFPU RCX seed、单位秒数。注意LCG其他caller推进共享对象seed尚未跟全，不可每FX私设种子；type23不能称已恢复VFPU PRNG。最近MSVC/SDK仍UAC取消终态，勿无新steering重试。

## 最新：生产场景／颜色 core 已进 UE module，新校准 actor／RDG／shader 源码接线

前轮progress：same-frame原场景native组合／937px深度证据；本轮progress。根out/UE_SCENE_COLOR_BRIDGE_20261021。新增生产T3BGEScene.h/.cpp LoadSceneGeometry(T3BSFC1)/LoadSceneEffectBindings(T3BPCG1)/EvaluateSceneFrame：读取任意支持atlas与逐draw原矩阵／fog／flags；每次选sample执行source-parent/mode/palette/patch/geometry，匹配原draw数据与texture再atomic返回。ge_scene_probe实际同core编译读取3帧79atlas/838draw/109299点/24color，重新序列化全bundle byte同；8错误截断/trailing/flags/nonfinite/错projection/sourceRGBA/CLUT实际拒绝不落部分输出。

新增AT3BGESceneReplayActor（默认bEnableSourceCalibration=false，LoadSourceScene/SetCapturedSample，无autoPlay/时钟，identity actor transform）、FT3BGESceneViewExtension（任意atlas/RDG/逐draw state）、T3BGEScene.usf/Common.ush。明确原camera calibration真实geometry，以独立source depth/stencil+color view替换，不写另一个UE camera主depth，故不是PC自由相机/gameplay/M1；UE preExposure/tonemap另层尚待验。旧AT3BGEReplayActor与两atlas路径不改。UE actor/RDG/RHI源码接线，正式C++/UHT/shaderbuild未运行，勿称已在UE实际出图。

run_scene_color_bridge.py冻结core+UE源码，ge_scene_runtime_gpu实际从原scene/bindings调用同生产函数、共享UE pixel helper原文本（nativewrapper内联，无改算术），最终run e388cd172e374cc6a4c704aec17625ca/PID98980自然exit0，3captures/79textureupload/109299VS+RGBA/owner/depth全byte同前3765...原GE场景基线，独立verify_scene_color_bridge通过。实际看记录2 PNG，其余exactbytes。初core编译缺Registers include/indent Werror的源码在failed_build_v1；初GPU run4dba.../PID99276 exit1因无include handler，loader/negatives通过但shaderfail，原日志保留；改内联helper后新run通过，不回填。23 current_tool_snapshots/source_protection/checkpoint。

Validation/ue_source_scene_calibration_plan_20261021.json保存具体actorclass /Script/T3BRemake.T3BGESceneReplayActor、scene/effect路径SHA、sample0/1/2和需实际UE验收项，executed=false。原ISO/slot0/INI3与185UE包SHA全不变。无新UE/PPSSPP/安装。最近toolchain run5f96be...session90274 UAC取消终态，勿无新steering重试。完整goal active；文档UE_SCENE_COLOR_BRIDGE_20261021.md。下一步实际UE构建待外部工具链，独立恢复shared23/24/type6 RNG/原clock和生命周期；勿重复此native三帧验证当新进展。

## 最新：生产颜色 core 已与同次 Aya／原枪／异形／街景在实际 GPU 组合

前轮 progress（孤立特效GPU proof通过，安装终态UAC取消）；本轮 progress。根 out/FX_SAME_FRAME_SCENE_20261021，工具 prepare_fx_same_frame_scene.py（recover/export）、ge_fx_scene_gpu.cpp/run_fx_scene_gpu.py/verify_fx_scene_gpu.py。直接从此前color6_GE16_v1同3份PPDMP提取完整已识别Aya106+weapon1+other28，3组405draw/16497vertices。skin_inputs_v1，lighting_v1重新固定PPSSPP software reference+生产T3BGELighting实际执行，transform/color mismatch0；独立GPU verifier又逐byte回原PPDMP核对regs/BONE/WORLD/rawpos/normal/weights/UV。scene_v1加原街景141/137/131draw和每帧8个CPU关联特效，838draw/109299GPU点/79原CLUTatlas。只有这些确认类别，其他FX/sprites/HUD/FBO显式排除，非完整scene。

最终 native run3765b564f94b4d3f904b06290044d764/PID82024自然exit0/session无存活。21captures，直接GE/生产palette→patch→geometry完整VS及RGBA/owner/depth-stencil bytes同。3帧scene effect覆盖1456/1781/1827，isolated1711/2056/2234，减少255/275/407共937px；独立按actual VS triangle+barycentric Z和prefix actual D24核对，全部fail GEQUAL。加入前后prefix与完整关闭target control主depth/stencil同，RGB改变1172/1413/1424只在final targetowner。before颜色control同noeffect所有buffers，不是上一完整帧。max源projection .000320 PSP px<.01。三帧实际view过，角色原枪异形街景同帧，橙色特效可见；没声称muzzle命名/弹道恢复。

out checkpoint/source_protection与9工具/production/source snapshots已冻结；原ISO/slot0/INI3文件+185UE包全同。无新PPSSPP/UE/安装。本阶段native D24S8子集，不是PSP最终pixel真值、完整场景或正式UE/M1。正式C++仍因最近run5f96be975a50477eb0fa1b5764af4047/session90274提权取消无installer PID，勿无新steering重试。完整goal active。文档FX_SAME_FRAME_SCENE_20261021.md，preview在最终run/PREVIEW.html。

下一步优先实际UE接入已确认动态color/material/geometry，编译待toolchain成功；可独立推进shared23/24属性/type6 RNG/动作clock生命周期。不要继续重复孤立或同帧native等价为新进展，不把旧12组姿态和本次3帧混作同一个时间轴。

## 最新：原特效 palette→geometry→native GPU 实际验证通过

证据 out/FX_PALETTE_GPU_20261021；最终 native run 96c007b73ee04d5cb5055ad87d887f3a/PID10308 exit0，13captures/24source draw/144GPU vertices。GE输入与生产core输入的VS/RGBA/owner/depth逐byte同，最大投影误差5.856e-6 PSP px。3帧原CLUT特效与改写前颜色/白贴图对照实际查看；已冻结验证器与源码，首次sparse-register KeyError修复留档。原ISO/slot0/INI和185UE包哈希不变。孤立黑底原材质特效，不是PSP最终pixel真值/完整场景或UE/M1验收。文档 FX_PALETTE_GPU_20261021.md。当前用户已再次明确授权后台安装MSVC14.44/SDK22621，新run5f96be975a50477eb0fa1b5764af4047已终态：session90274 exit1，Windows提权返回用户取消，无installer PID/组件安装，勿无新指示重复提权；见terminal_status.json。完整重制goal active。

 ## 最新：原版特效颜色已在实际 GPU 验证

3组原版记录、24次draw的生产颜色/geometry core已在实际D3D11执行；VS、RGBA、owner、depth与直接原GE输入逐byte一致。13次GPU采集及改写前颜色/白贴图对照通过。[预览与验证范围](../psp_parse/docs/FX_PALETTE_GPU_20261021.md)。

这是孤立原材质特效，正式UE module、完整场景组合和默认M1仍待接入。原ISO、存档与185个现有UE包保持原哈希。以下为此前阶段记录。

## 最新：顶点颜色 CPU→GE 精确对齐，生产颜色/几何 core 串联通过

本轮 progress。根 out/FX_VERTEX_COLOR_GE_20261021。trace_fx_color_material_emissions.js新增可选FX_COLOR_GE=1，在首次exact rifle/descriptor10c78/type155 ID19入口arm有界并发gpu.record.dump，采VIEW writer8c01088输入/实际13word packet、原枪WORLD/mainVIEW（8c3b588槽），writer与modulated bytes同；CPU完成后remove/resume own stop再await GE task。color6_GE16_v1真实6CPU calls/5palette updates+16GE PPDMP，failure/geFailure null；session41150/PID68756 terminal exit0，清理输入/BP，自有进程已停止。原无GE默认路径保留。

CPU_write_audit_v1重新原palette/cache/vertex完整链，5palette/40draw/160vertices通过。新analyze_fx_vertex_color_GE.py按全部8连续原draw的VTYPE/PRIM4/count/raw vertex bytes、完整12VIEW payload，以及此前最近的完整geometrySHA原枪WORLD/mainVIEW高24做唯一content join。最终correlation_v3显式expect-matched-rows3：CPU1→GE0/startOrdinal310，CPU3→GE1/312，CPU5→GE2/294，每组8draw，共24draw/96vertices的after bytes同GE，before匹配0。CPU2/4在此记录subset无对应，不判从未render；16record并非全都CPU配对。palette flush另stack（dispatcher09ffe650、flush083ffeb0），不依墙钟顺序猜帧，当前仅3观测锚定，非通用invocationID/全部调度证明。

每draw原WORLD/VIEW/PROJECTION、全部regs、CLUT/known、texture/material留档。唯一原texture仍64x32 RGBA SHA75ee19dc59a0118645523e2711eec0c7e3cfc950a9d8bc0abaa313794d91941d，新PNG实际view过；无HD重绘。实际UVscale1.84375/1.9375、offset.5/0、repeat、alphaTest/df a6/colorDouble等状态保留，与vertex palette分离。matching primitives兼容现effect decoder结构，runtime_geometry_id读取实际binder g5而非hardcoded5。

新增Tools/ge_effect_tinted_strip_probe.cpp，一进程真实链接当前生产T3BGEEffectVertexColor.cpp +既有T3BGEEffectGeometry.cpp，输入actual source RGBA/parent/flag、原palette/colorIndices、CPU BEFORE vertices与GE regs；执行parent→mode→palette→patch→DecodeOriginalEffectStrip。runtime_integrated_v2实际g++ C++17 O2 ffp-contractoff：24draw/96vertices/48tri的palette、raw patched GE bytes、local pos/UV/color/topology全部byte同独立GE解码；不是直接把after GE当core输入。UV只应用原scale/offset一次。4坏接口输入lighting/UVgen/PRIM/truncated实际拒绝。negative_join_v1三个SHA一致合成坏证据（错after color、错rifle WORLD、错VIEW input）在指定覆盖/packet gate拒绝。correlation_v1/v2旧producer各自snapshot保留，final v3新增匹配覆盖gate；runtime_v1初版passed，v2当前final proof/源码冻结。

source_protection原ISO/slot0/INI3文件+185UE包全同前基线；current_tool_snapshots15当前工具/生产源，actual launch-time observer/runner另存。没有UI/UE/Content/安装重试。GE命令/输入record消费现在有新证据，最终GPU framebuffer pixels仍未验；正式UE module未build、默认M1未切、HD/战斗AI碰撞伤害与完整可玩未完成，完整goal active不complete/blocked。文档 FX_VERTEX_COLOR_GE_20261021.md。

下一步将新的逐draw color bindings/完整原矩阵/CLUT/raster参数用于native GPU renderer验证（Tools/ge_strip_fx_reference.cpp及相关run/producer可参考旧原FX GPU链），再正式接UE pass/M1；不要以local geometry bitexact替代GPU变换/raster/像素。其他cache调度/0与1条目颜色分支/shared23/24/type6 RNG/单位换算/完整生命周期继续待恢复。MSVC/SDK仍UAC取消终态，勿无新steering重复提权。

## 最新：原版 FX 颜色实际走顶点 palette 缓存，40draw/160vertices真实改写已恢复

本轮 progress。证据根 out/FX_COLOR_MATERIAL_20261021。重要修正：选定rifle descriptor10c78/type155 ID19的group+10=2是顶点颜色条目数，不是GE material mode enum；08b60080真实走多色缓存，不是08c005bc→01998 mode7写55/58/56/57。新color6_v1发现多色分支后严格失败保留；最终color6_v2成功6个同node render calls。两个hidden isolated PPSSPP进程均terminal/stopped（v1 session24989/PID92168 exit1；v2 session96839/PID62832 exit0），输入/BP已释放。无UI/UE/安装重试。

实际链：source type16 RGBA ×P+40 parent F32→type155 record+4b颜色flag（本次1/pass-through）→60080 bank cache→60758 drain→5f684 palette modulation→5f780写原vertex。6callsRGBA交替：(128,44.7999992371,4,0)/(128,56,8,48)；第0call last bytes相同cache hit，其后5次queue。bank+24 cachebase、+28pending、+2cprocessed、+30capacity；32-byte entry前16RGBA、+10目标objectPtr、tail12不改，object+10 lastRGBA更新。memcmp raw16，+0/-0也不同。当前一个group/一个drawheader，实际processed+1；不外推通用cache调度。

原vertex palette两条RGBA=ffffff00、80808080（与texture CLUT分离）。实际5f684先rgba*1/128，再sourceByte*factor，trunc.w.s，上界>=256置255，SB存低8bits，无通用lower clamp。暖色输出ff6f0f00/80380830，低alpha帧ff590700/802c0400。独立scalar MIPS/COP1 replay在5次converter的output/GPR/FPR全同；现有shader doublealpha仍另层不混入此CPU公式。vertex patch读取真实inner+4 color reference ptr，每ptr确实指向converted palette条目；VTYPE11e stride16/color offset4，5次×8draw×4vertex=40draw/160vertices，完整after buffers逐byte同，UV/pos/padding未变。没有新的同次GE消费/GPU像素证明。

新analyze_fx_vertex_color.py/replay_fx_render_color.py，最终vertex_color_audit_v2通过。v1 audit曾把pre-JALR a2当record，原69d68 delay slot实为t0→a2，修正为原opcode验证与dg[8]→renderer S4 record，原数据未改。新增生产T3BGEEffectVertexColor.h/.cpp：source-parent调制；colorflag6=(1-A/128)下界clip、10=(2-A/128)上界clip、9/11/12=A/128上界clip、其他pass；raw cache predicate；vertex palette scalar算术；11e/11c palette-index patch。runtime_vertex_color_v2实际g++当前core：6actual颜色/cache、5palette、40draw/160vertices全输出bytes同；17明确synthetic原scalar opcode/layout/cache样例（mode6..12等、负值SB、signed-zero/full cache、stride12）+6非法输入通过。v1因-Werror misleading-indentation编译失败留日志，修braces后v2通过，未降检查。

source_bindings_v1/vertex_color_bindings.json导出8draw/32vertex模板与colorIndices、2色palette，5个观察的非color geometry/reference byte同。模板颜色是某次旧真实tint，使用前必须全部按当前palette改写；layout SHA不是通用resourceGUID，也不是新ISO内offset确认。negative_evidence_v1三SHA一致坏证据（palette output、vertex position、false cache bool）在指定独立gate拒绝。源码/args/exe/input/ref/output/actual launch-time JS与runner均保留；current_tool_snapshots12当前工具/生产源。current observer已修正继承的limits文字为vertex writes，v2实际executed JS/旧report label保留不回填，最终proof/docs明确没有本branch material-command writes。

source_protection原ISO/slot0/INI3文件+185UE包全同前基线。正式UE module仍未build、默认M1未换、高清美术/AI/碰撞/伤害/完整可玩未完成，完整goal active不complete/blocked。文档 FX_VERTEX_COLOR_PIPELINE_20261021.md。parent VFPU prefix controls未直接导出，当前6个F32 products实测相同，不泛化所有prefix；cache容量/数量有界，其他0/1颜色条目branch未port。

下一步优先同次CPU palette→vertex buffers与GE PRIM的raw vertices内容join，确认实际GPU消费，再把color bindings接既有effect geometry decoder/native GPU renderer。trace_weapon_marker_ge_emit.js/capture_weapon_ge_correlated.ps1有此前bounded gpu.record.dump并发、首次target-entry arm、完整DL/CPU-GE content join做法可复用。不要把本轮vertex-write proof当GE-consumption或直接把palette当textureCLUT；保留原UV offset高24一次应用、原矩阵/material/blending独立。也需继续共享23/24、type6/RNG、其他FEPbranches与秒数转换/生命周期。MSVC/SDK仍UAC取消终态不重复提权。

## 最新：原版 FX type16 颜色与 type7 百分比缩放 core恢复，11真实更新逐bit通过

本轮 progress。证据根 out/FX_COLOR_SCALE_20261021。新 reset21_color_v1：沿用exact rifle/descriptor10c78/type155 ID19选择，21外层callback triples，其中type16的3次reset各增采08b8fa48→08b8f954→08b8fa50嵌套evaluator。额外运行时identity保存完整color callbacks898..fa60、type6前后函数943d4..94508、scale94968..949fc、scalar record finder6ac94..add8。单自有CPU BP、hidden isolated portable/slot0/INI副本；实际session59748/PID54716 terminal exit0，输入/BP已释放。

color_scale_audit_v3在重新baseaudit这21条及前轮key9_v4后，独立逐opcode回放type16 key1/reset3/nestedEvaluate3和type7 key1/reset3，共11操作/116原float分量，整个512-byte参数窗口同return。新 replay_fx_color_scale.py支持当前lv/sv、mtv、vadd/vsub、vscl、vzero、vpfxT、finite vmin/vmax，固定5份官方v1.20.4源码SHA并沿用vindices。未知opcode、无保留read、越界write、非有限值拒绝。debugger仍未导出VFPU S/T/D controls：3color reset由同node前type7尾部vzero及纯scalar dispatcher/finder建立default prefix，3nested evaluate由wrapper最后vsub建立；余5key/scale entry仅default-prefix回放与实际输出相容，勿外推所有prefix/硬件模式。

新生产T3BGEEffectColorScale.h/.cpp：Color state=RGBA/base/velocity各4float，keyrecord前32bytes=base+velocity。key08b8f898..954保留状态/旧key差叠新key、当前RGBA复制base不clamp；reset08b8f9b4..fa60旧f13累计后按新f12重基并真调evaluator；evaluate08b8f954..9b4按原独立F32 base+velocity*t、vmax/min clamp0..255且equal选T使-0→+0。原source单位0..255，不加double-alpha或提前归一化。实际颜色(128,56,8,48)、velocity0，无真实fade动画声明。

type7 key94968..949d0前三percent=(state-old)+new，再乘原F32 .01(3c23d70a)；输出Scale.W=0，Percent.W保留。reset949d0..949fc前三percent=Scale*100，Percent.W=0，Scale4全不动。新实际第一reset percentY248.5345916748047→248.53457641601562，1ULP差保留；actual scale约(2.0192435,2.4853458,2.5)已受共享class23贡献，不能每帧覆为authored2.5。type6实际语义/RNG/原矩阵合成尚待后续，不把percent数值core等同完整姿态。

runtime_color_scale_v2实际g++当前生产core，11actual/116F32bits全同；10明确synthetic原opcode operand样例覆盖不同key/非零RGBAvelocity/越界clamp/负零/小数/缩放W保留与置零/舍入，5非法transport/domain输入拒绝。Scale output pad4zeros不计入116原分量。negative_evidence_v1三坏证据（改color before base、scale return W、nested RA）均指定独立gate拒绝。源码/args/exe/input/ref/output SHA冻结。source_bank_v2导出type7初始116f0/time11990的已消费12bytes XYZ百分比(250,250,250)，type16初始11730/time119d0的32bytes RGBA/rate；8actual operands同原；reset序[0,1,3,5,6,7,9]/key序[0,1,2,3,4,5,6,8,9]同实际。alias2/3共60、4/5共80保留，class23/24未port。v1 sourcebank旧executed脚本单独保留；final v2增加实际order/alias gate。早期numeric proofs/v1仍留，final audit_v3/runtime_v2是当前严格finite guard版。

source_protection原ISO/slot0/INI3文件+185UE包同前基线；current_tool_snapshots13当前工具/生产源。无UE/Content/安装/桌面操作，正式UE module未build、默认M1未换、HD/伤害AI碰撞/可玩验收未完成。完整goal active，不complete/blocked。文档 FX_COLOR_SCALE_20261021.md。

下一步优先原type16→parent/material颜色调制→08b60080→08c005bc→08c01998实际material命令。60080包含直接RGBA pack、单色palette乘整型/128、动态palette更新多个分支；不要只用paramRGBA当最终材质。01998 mode7会写55/58/56/57，需采真实binder输入、branch/palette bytes、DL cursor/return命令后再接M1。可基于trace_fx_curve_uv_emissions.js的单BP链路新增专用color sampler，但本轮没有该实际capture/新GE或GPU pixel证据。也需恢复共享23/24和type6/RNG以及秒数换算/FX完整生命周期。MSVC/SDK保持原UAC取消终态不自动提权。

## 最新：原版 FX 属性回调、type155 连续 UV 曲线与实际 GE 命令写入恢复

本轮 progress。证据根 out/FX_PROPERTY_CURVES_20261021。exact rifle/descriptor10c78/type155 ID19选择后，单CPU BP按dispatch→actual entry→return采集；最终reset21_v2=21回调/3组7类，key9_v4=9回调/1组9类。combined_audit_v3通过30实际class/record/parameter bindings，其中type155 reset3次+普通key1次，独立原scalar MIPS/COP1 interpreter输出整个512-byte有界参数窗口逐byte同真实return，6字段外不变。不把其他26回调宣称算术已恢复。

实际definition index/type/param offset：0/1/0，1/6/20，2/23/60，3/7/60，4/24/80，5/16/80，6/61/b0，7/62/f0，8/14/110，9/155/110（offset十六进制）。60/80/110是原共享块，不能各definition独立分配再相互覆盖。type155仅+8..1c六float=2base/2velocity/2acceleration；record+10..24六float。普通key08b9a3ec..a514保留差值换key，v0不写；reset08b9ad1c..aebc按f13旧时间累计、f12新时间重基并原4096/trunc处理，v0=1。此前审计错误统一v0=1已修正，combined_audit_v1失败不当positive，最终v3。

新生产T3BGEEffectCurve.h/.cpp包含Change/Wrap/EvaluateOriginalEffectCurve与BindOriginalEffectUV。runtime_curve_v2实际g++当前core：4次actual/24F32bits全同；8明确synthetic原opcode operand样例含不同key/非零acceleration/小数/负数/极值通过，5坏输入拒绝。source_curve_bank_v1/source_curve_bank.json导出原初始payload117a0（entry11674，start/end0/0）与time-key payload11a40（entry1190c，0/2），均curve(0,0,32,0,0,0)，4actual新旧operand前40bytes同原asset；7reset indices/10defs/3alias组同时导出。只此descriptor，source seconds单位未知。

uv6_v1六次同node实际render按69d64→8b9a71c→8bbfbc4→8c00aa8→8bbfcbc采样。原pixelU=0/32/64/96/128/160，phase0/1交替；真实texturebank→slot→object→header尺寸64x32，U归一化为0/.5/1/.5/1/.5。原binder接受等于width而保留1，不能用[0,1) fmod。原FPU evaluated/binder/emitter全同；return实际DL context不变、cursor+8、两words=4a/4b+F32high24，uv_audit_v1独立通过12实际UV OFFSET words。runtime_uv_v1实际当前生产core：6actual/24F32+12words全同，8明确synthetic与5坏输入通过。输出接旧GE decoder时先pack high24，不能offset应用两遍。当前证明止于CPU写命令，没有新同次GE消费dump/最终pixel对照，亦不由64x32认领CLUT身份。

旧reset14_v1成功但0x180代码window短于完整reset，最终用0x200的reset21_v2。key14_v1/key20_v2失败于采集器4-byte对齐假设，真实记录可2-byte对齐；已支持bounded byte read。key20_v3仅9complete后达stop上限仍未满足20，严格保留failure；key9_v4实际成功。所有7自有PPSSPP采集进程terminal/stopped，无GUI/UE/安装重试。source_protection原ISO/slot0/INI三文件+185UE包同前基线，current_tool_snapshots13当前工具/生产源；每次launch-time JS/runner单独保留。正式UE module未build、默认M1未切、完整FX生命周期/HD/AI/碰撞/伤害/可玩验收未完成。goal active，不complete/blocked。文档 FX_PROPERTY_CURVES_20261021.md。

下一步恢复type16颜色及type6/type7实际参数语义，并追共享type23/24/14的初始化/更新顺序；可复用exact descriptor单BP采集。新UVobserver确认真实shader状态输入，但勿重复同数值验证当新进展。M1后续应消费source_curve_bank的原keys、原phase与共享state；source clock manager的秒数换算、其他FEP branches、boundary所有事件仍待恢复。MSVC/SDK保持UAC取消终态，不自动重复提权。

## 最新：原版 FX 节点时钟 writer 与回绕恢复，生产 C++ core 实际执行通过

本轮 progress。证据根 out/FX_TIME_SOURCE_20261021。最终 node_clock8_v6 在原 dispatcher 08b69d64 选择 type155/ID19、descriptor10c78/def9，保留完整原 rifle 指针链、3source/243vertices/VTYPE522/geometry SHA 与 FEP192身份。移除 CPU 选择断点后，只用 N+30 单个 write/change memory BP，9实际停止点观察到8个完整效果：08b683f8推进0→1/1→2共6次，08b68e4c回绕2→0共2次。最后pending store排除。值是在下一个真实写入停止点读到，不冒充instant-after single-step证明。advance trap PC08b683f4为COP1分支，store在delay slot+4。

clock_audit_v6独立重读原module、反汇编、GPR/FPU、live node/state/descriptor/context、下一实际字段与原FEP，8effects+1dispatch时间参数通过。原loop区间u16 [0,2)，实际delta/rate均1；实际动态时间仍只有0/1/2。原回绕08b68e04..e50在boundary callbacks之后重读time：trunc.w.s、SUBU modulo32、signed DIV/MFHI、独立F32 fraction/add，不能naive fmod。dispatcher08b69d34另用当前N+4c indexed record+4 signedS16 start，null保留bits；与matrix-helper f12不同。update_static_v1保留完整updater68118..68744与manager68744..68840；两个node lists180/184，rate1b4/globaldelta/carry134静态已定位，完整生命周期仍未移植，不能硬编码30Hz/seconds。

新增生产 T3BGEEffectClock.h/.cpp 三numeric APIs及ge_effect_clock_probe.cpp；verify_effect_clock_runtime.py在runtime_clock_v1实际g++ C++17/O2/ffp-contract=off编译执行，9actual操作F32逐bit同原。13明确synthetic cases（9原opcode interpreter回绕＋4signed/null时间）通过，6非法输入拒绝；源、args、exe/input/ref/output SHA冻结。negative_evidence_v1另有3坏证据合成反例，改下一字段、effectiveDelta、live interval在指定独立gate拒绝。不是新原版姿态/完整FX生命周期或正式UE执行；默认M1未替。

失败 node_clock12_v1(COP1分类)、v2及node_clock6_v3(stepInto重复同PC/ticks、没有实际after)全部保留；node_clock8_v4/v5观察成功但字段较窄，最终只用v6作完整证据。6个隔离采集进程terminal，输入/BP已释放；source_protection.json原ISO/slot0/INI三文件及185UE包与前基线相同。current_tool_snapshots保存8当前工具/生产源，actual launch-time JS/runner另保留。文档 FX_NODE_CLOCK_20261021.md。完整goal active，不complete/blocked。MSVC/SDK仍为UAC取消终态不重试，formal UE module/M1可玩/HD美术/原AI碰撞伤害仍未完成。

下一步追08b689b8与08b68b8c的真实边界/属性更新，尤其08b68ce4 JALR callback，恢复局部矩阵、颜色/UV曲线与FEP时间键。不要把已通过clock numeric core反复验证当新进展，也不要略过回调直接接成完整FX循环。manager输入delta13→C10的秒数单位及上层转换尚未知。

## 最新：完整inline FX子draw恢复，15顶点companion归属确认，生产effect geometry core通过

本轮progress。新增可选MARKER_CAPTURE_FULL_HANDLER_DL：在callback_return读首emit cursor→当前dlSnapshot的完整有界CPU窗口，同context/单调cursor/alias校验，逐PRIM读原vertices；type155另采object→header→group→drawHeader→innerRecords。原opcode独立确认group stride为0x44（08b5ee28=26730044），修正了初始0x38假设。初始aimfire12_v1及strafefire16_v1均仅1group，保留0x38已用字段前缀，不能当完整record；最新strafefire16_v2采完整0x44且按真stride寻址，旧producer/raw保留，没覆盖成通用成功。

证据根out/WEAPON_FULL_HANDLER_GE_20261021。选定aimfire12_v1=12handlers/36CPU PRIM，full_correlation_v1完整12GE子draw对应1记录帧；strafefire16_v2=16handlers/48CPU PRIM，strafe_full_correlation_v2完整24GE子draw对应2帧。均hidden portable副本/配置/slot0副本运行，原INI不写入；三个自有进程均terminal exit0且已停止，当前无PPSSPP。旧strafefire16_v1同为成功采集但group为prefix，本轮最终proof选v2。

analyze_weapon_full_handler_ge.py从固定module13原word核object字段与loops，重读raw header/records和CPU完整命令，不信producer标注，原record必须逐条同实际VTYPE/primitive/count/VADDR；首record等实际emit s3。按前轮首draw完整content anchor后，GE中连续每PRIM的raw bytes/VIEW/格式/count同CPU，窗口已写受支持raster scalar也核对。每draw原WORLD/VIEW/PROJ/CLUT/texture/材质保留。full_visual_FX_subdraw_bindings.json36观察。总3GE记录帧，不是36独立姿态/射击。

每个实际4-handler组合：type152 ID15两个handler各一个4vertex；type155 ID18一个handler真正含14+15两个draw；type155 ID19一个handler含8个4vertex。至此15companion和ID19后7个draw有原对象→CPU命令→GE证据，不再凭相邻/同原点推断。两张原CLUT仍a8e415...(256²)与75ee19...(64x32)，无HD重绘。type152窗口末尾含projection恢复；type155含depth-write/cull/UVoffset恢复。当前路径08b5e3a8是generic inner-record loop调用PRIM emitter，不是这里直接写BONE，勿仅凭命中该PC认领右手/骨矩阵上传。

新增生产Public/Private/T3BGEEffectGeometry.h/.cpp，DecodeOriginalEffectStrip支持实际unweighted/unlit PRIM4 VTYPE102 stride10/11e stride16，原u16 UV、s16pos、RGBA8888或ambient、独立F32 UVscale+offset，奇偶strip拓扑保留含退化。UV已应用一次，后端不能重复乘。Tools/ge_effect_geometry_probe.cpp实际调用同core；verify_effect_geometry_runtime.py从36已对应GE子draw构建原输入，runtime_effect_geometry_v1实际g++编译执行，207源vertices/135triangles/405indices，position/UV/color/index全部bytes同独立raw解码，4坏输入拒绝，源码/命令/exe/输入/ref/output和逐draw绑定冻结。局部几何core，不是正式UE module或最终GPU/M1验收；每draw原矩阵/材质仍需另供，原FX时钟未实现。

negative_full_handler_v1三合成反例（缺companion snapshot、改原inner record、改producer count）在指定独立gate拒绝。current_default_selftest.log当前observer默认flags174个Mock全部通过，session33340 exit0；full-handler可选分支由真实采集+独立审计证明，不冒称Mock覆盖新分支。matrix_math_v1/strafe_matrix_math_v2原mode0/1+VIEW实际stage bitexact，prefix controls仍未导出，不外推通用JIT/VFPU。current_tool_snapshots保存当前工具，实际captures另有executed JS/PS runner，production源码在runtime目录冻结。

source_protection.json原ISO/slot0/INI三文件+185现有UE包全同前基线，无Content/原存档/原ISO改动。文档WEAPON_FULL_HANDLER_GE_20261021.md。goal仍active；MSVC/SDK UAC取消终态不重试，正式UE仍未编译；M1完整可玩/HD美术/伤害AI碰撞弹道未完成。

下一步优先原FX节点update/参数构造与时间源：N+4c indexed time slot在08b69d20..34影响f12，matrix.entry.allRegisters有真实FPU bits；原node+50 input、P+30 scale、local颜色/UV mutable data有前后snapshot。追实际更新writer/原FEP pre/post callbacks，恢复可驱动M1的FX生命周期，而不是把3捕获帧当完整authored动画。已确认几何/marker/material可以接入后续正式M1，但目前无新相机billboard/完整state恢复渲染或playable验收。

## 最新：source1→真实视觉FX→GE draw/CLUT同运行对齐，生产F32 core逐bit复现28条CPU记录

本轮实质progress，使用隔离portable PPSSPP/配置/slot0副本隐藏运行，原INI不写入。capture_weapon_ge_correlated.ps1新runner；trace_weapon_marker_ge_emit.js新增可选同暂停点完整WORLD/3source records、并发有界gpu.record.dump、首次精确武器/FEP入口arm、mode0 08b657f8/a4完整同次原码双恢复。单自有BP/ABI/按钮analog清理保持。三个自有process均已terminal/stopped，当前无PPSSPP，未重试安装。

新根out/WEAPON_CPU_GE_CORRELATED_20261021。aimfire12_v1实际12CPU+4GE但0精确匹配，initial_capture_audit_v1只证输入一致，visualFX observed=false，不冒充成功。改首次target入口arm+16GE后：aimfire12_v2=12CPU/16GE，correlation_v2精确CPU4/5/6/7→GE0四draw；strafefire16_v1=R+square+leftx.7，16CPU/16GE，strafe_correlation_v1精确CPU4..7→GE0及12..15→GE1八draw。所有failure/geFailure null，runnerexit0，按钮/analog/BP清理成功。

analyze_weapon_cpu_ge_correlated.py重新原CPUemission审计，raw vertices/VTYPE/PRIM/count+完整12VIEWpayload完全相同，且同GE流此前原枪的WORLD/主VIEW高24同时同CPU完整WORLD/view.globalMatrix；原枪243/VTYPE522/full geometrySHA身份。总12唯一对应、3实际GE记录帧，不是12独立姿态/12射击。PPDMP无CPUcommandPC，唯一完整内容join不是普适invocation ID。

每组matrix-entry与emit-entry的3source/WORLD bytes同，28source定义同前T3BWMK1 catalog；source1+40×完整WORLD separate F32组合逐bit同真实P+60。新生产T3BGEWeaponMarkers::ComposeOriginalWeaponMarker和Tools/ge_weapon_marker_cpu_probe.cpp实际g++执行原F32逐乘加，runtime_F32_v1 12条/3WORLD/192components 0bitdiff；strafe_runtime_F32_v1 16条/4WORLD/256components 0bitdiff，共7不同WORLD/448components。F32真实CPU core与旧EvaluateWeaponMarkers的GE F24→F64 bridge区分，正式UE module未执行、默认M1没切。

verify_weapon_ge_matrix_math.py原opcodes对新12+16组mode0/1和VIEW共56stage输出bitexact，matrix_math_v2/strafe_matrix_math_v1；全部selected helper同次fullruntimecodeidentity已齐，补上旧mode0缺口。但entryprefix未导出，actual_runtime_math_verified等全模式/无条件字段仍false，不改成通用证明。negative_correlation_v1三合成坏证据（错WORLD、SHA有效错source、错GEhash）均在指定新gate拒绝。

visual_FX_bindings.json保留12个观察，完整FEP descriptor/definition/资源/原input/实际state60/武器WORLD/GE材质。四种链：descriptor10ba0 def7 type152 ID15/record2b58 mode1 local+Z5；10be8 def5 type152同ID/record mode1 +5但scale不同；10c30 def7 type155 ID18/2690 mode0 +5；10c78 def9 type155 ID19/26a8 mode0 +7。definitionIndex必须连descriptor，不能混成全局7。实际两张CLUT4 ABGR8888解码PNG已view：256² a8e415...给两type152；64x32 75ee19...给两type155。每draw完整CLUT、knownhash、shader registers/UV等留档；无高清重绘。type152 mode1 camera basis，不能quad normal当枪方向；原方向取source1+Z。source1的视觉FX consumer已直接观察，gameplay bullet/raycast/damage origin、原作者命名muzzle仍未知，source2用途未知。

motion_and_coverage.json：瞄准source1原点轴跨度1.8374/1.7151/2.2693 PSPunits、+Z首样角变1.42135°；移动7.23535/1.99718/2.75557、3.57766°。只是短窗口7WORLD/3匹配GE帧，不替代完整连续动作或authored FX clock。

source_protection.json三原ISO/slot0/INI+185UE包全部同前基线；无UE/Content改动。current_tool_snapshots是本轮结束current工具，不冒称launch-time PS runner attestation；每个actual capture单独有真实executed JS hash/file，runtime编译源已冻结。文档WEAPON_CPU_GE_CORRELATED_20261021.md。完整goal active，不complete/blocked；原HD美术/碰撞/AI/伤害/正式可玩M1未完成。

下一步优先每handler完整CPU DL window：callback_return读取首个emit.entry.dl.cursor到当前dlSnapshot cursor的有界命令窗口（检查alias/单调/上限，勿猜跨buffer），解析后续VADDR/BASE/PRIM/材质，并在callback暂停读实际vertices。当前只首PRIM，ID18的14vertex之后15vertex companion仍未归属；不能仅同原点/相邻draw命名。已有GE匹配可做对照；确认后再接完整视觉FX子draw和M1跟随验收。MSVC/SDK仍取消终态不重提权。

## 最新：原枪 source1/source2 原始矩阵接入实际 C++ core，+5 FX 偏移取得交叉证据

本轮实质 progress，未启动 PPSSPP/UE/UI。analyze_weapon_fx_source_links.py 重新审计6 emission/24 dense marker snapshots；source0+80/source1+40/source2+40 共192原始bytes在24份快照完全一致，原parent [null,source0,source0]。recovery_v1/source_markers.bin 是208-byte T3BWMK1，两条marker只称source1/source2，semanticName=null。check_weapon_fx_quantization_intervals.py另证原source0+80高24与全部12枪GE BONE相同。

新增生产Source/T3BRemake/Public+Private/T3BGEWeaponMarkers.h/.cpp，Tools/ge_weapon_marker_probe.cpp。最终runtime_v2直接原local source1/2 × 当前GE WORLD，不经量化BONE求逆；BONE只核当前rifle bind。实际g++编译/执行生产core，12sample/24markers，独立原bytes NumPy F64最大差1.1102230246251565e-16，限1e-9；5坏输入实际拒绝。实际源码快照/命令/exe/output SHA保留。独立core执行，不是UE module执行，不是同帧unquantized CPU pose；默认M1没换。runtime_v1旧GEskin绕行路径和其compiled source snapshot保留；recovery_v1.reconstructed_marker_frames也属旧诊断，最终姿态以runtime_v2为准。

source1 +Z对应原枪raw −X；旧CPU真实type152/ID15/record2b58与type155/ID18/2690 input translation=(0,-0,5)，ID19/26a8=(0,-0,7)。未拟合+5给rawlocal [-1.0843449784,0,0.1264725663]；与样本1/2/11 FX簇差0.00125033/0.00063736/0.00228895 rawunits。CPU原14vertex bytes唯一匹配GE sample1record1246，ID19 4vertex唯一匹配sample1record1252；通用ID15quad匹配36draw，不可当专属资源。所有这些CPU/GE VIEW包不同，不能叫同次调用/同帧/muzzle确认。

intervals_v1按GE F24低8位未知区间和separate F32逐乘加，直接source1→WORLD→+5→VIEW，6条14/15vertex draw/3独立原点的VIEWtranslation分量区间相交；同簇offset0或7均不相交。这里只是量化区间相容性，相关变量未求联合解，prefix/JIT范围不外推，也不把真实另一effect的+7判为全局错误。

原PRIM2全量38条，只sample3=21/sample4=17，VTYPE19c/F32pos/RGBA8888/2端点，无UV，主VIEW/PROJ/FB一致。原bytes/registers/矩阵/枪局部方向完整留档；最近端点和有限线段距FX候选0.5317989246 rawlocal，不直接当枪口；亦不能排除早先发出的运动粒子。

证据根 out/WEAPON_SOURCE_FX_LINKS_20261021/{recovery_v1,runtime_v2,intervals_v1}，文档 WEAPON_SOURCE_FX_LINKS_20261021.md。source_protection.json：ISO/slot0/INI三文件+185 UE包全部同前基线。当前3分析producer冻结executed_*.py。无HD重绘/原碰撞/AI/伤害/动作时钟/完整可玩完成声明，完整goal保持active。

本轮新授权安装run c793438269084fbd9e286606ddecd93a/session17080已真实exit1，Windows RunAs错误操作已被用户取消，installer未启动；terminal_status.json为当前终态，status_snapshot待UAC是历史。MSVC/SDK仍未验证安装；不要自动重复提权或无工具链UBT。

下一步优先同一实际emission调用/GE帧采CPU完整WORLD+source1/state60+handler VIEW/geometry并关联GE消费，补齐实际实例与真实枪口/弹道语义；不要把现有几何复用和区间相容性当该验证已完成。原source1/2本地矩阵已有真bytes和core回放，勿再用拟合tip替代原数据，但正式M1开火绑定仍需同帧验证。

## 最新：原VTYPE119矩形sprites完成固定上游函数＋实际GPU恢复，128采集通过

本轮实质progress。recover_ge_sprite_inputs.py恢复同12捕获13950端点/6975矩形、1张32²RGBA atlas，out/GE_RECT_SPRITES_20261021/source_inputs_v1。build_ge_sprite_reference.py实际编译固定PPSSPP v1.20.4 unmodified ComputeTransformState/ClipToScreenInternal/Dot43/ClampFogDepth/ProcessRect/DrawRectangle+Math3D/fastmatrix，显式test-only状态/记录/bin适配；reference_v2成功。reference_v1缺smmintrin/dithergetter编译失败留档。来源Clipper.cpp官方tag下载保存在ref目录URL/SHA，TransformUnit/Rasterizer已有完整原source复制SHA。source函数未改，texture/alpha/depth/blend没执行，full drawing scissor bins不是完整原GPU像素reference。

ge_sprite_geometry.py独立F32模型；export_ge_sprite_geometry.py reread原PPDMP核raw输入，与实际ref逐byte核13950clip/fog+outsideflags、有效screenXY/Z16、6662parts及26867candidate pixel XY/UV/fog/RGBA/Z16。313原rect被clip拒绝，6662记录中1075有drawing覆盖→6450quad点。实际source无fogsplit，visible方向全(False,True)。geometry_v1/geometry.json通过，raw端点+矩阵保留。rect按源posttransform screenaligned语义，capture-camera-dependent，不能叫任意新相机worldquads；其他scene仍真3D。

T3BGEF3新40byte position3/UV2/sourceFog1/color4；原vertices插fog0保留旧36、新40checksums。merge_ge_sprite_scene.py scene_v1metadata旧checksum问题未GPU执行，executedproducer+issue留；scene_v2已修。实际Native ge_sprite_reference.cpp/.hlsl/run_ge_sprite.py，pixel pervertex flatfog从输入UV.z选，旧worldfog保持；bit65536sprite；bit32768GREATER。sample3原rDE6 strictGREATER，其他7GEQUAL，实际OMGetDS检查，没一律GEQUAL。共3647draw/444555 GPU点/89atlas。Source三角/FX旧438105GPU VS输出byte同。

先115capture run2e663ad5aa23446e9dbdbf6726a4add3/PID73200成功；13synthetic_contract_v2补4方向、second-color/Z、fogsplit、halfstep、zero尺寸、Z/GE-screenrange拒绝、viewportcrop和equalDepthGEQUALpass/GREATERreject。test_ge_sprite_contract.py真实调用相同上游reference，合成cases明确synthetic；原数据没有fogsplit。v1是12case，其中case9名字误叫screenrange但实际viewportcrop，原numericpassed和labelnote留档；v2把screenrange和viewportcrop区分为13cases。syntheticreference endpts26,parts18,candidatePixels326400完全同kernel，不是新原版姿态。

最终GPU rund73d3f8edb0b4c629d0c991f9b46768b/PID89456自然exit0，128采集=12*9source+7旧analytic+13sprite synthetic，independent_verification.json passed。实际89atlas对upload/staging同且spriteCLUT再核raw；6450sprite实际VS clip/UV/color/fog bit同quad；no_sprites RGB/owner/depth同eb127基线逐byte，新sprite不改mainDepth，GPUowner在upstream candidate coverage内，RGBdelta只在spriteowner内。每帧owner321..945/RGBdelta312..911。13synthetic精确GPU coverage且连续D3D RGB实测0LSB差，上限1；equalZ GEQUAL过/GREATER拒真发生。旧115采集345buffers全同2e663。root实际view37fac...全部CONTACT和rotated-fog诊断图；d73原115buffers已证同2e/37fac图源。37fac127case旧numericpassed但metadata第9标签旧，上述v2为最新。当前d73/PREVIEW手动source/no_sprites/sprites_only等9模式，128PNGs+contact，audit_currenttools冻结，source_protection185包+ISO/slot0/INI同。

旧UE40fed...原异形回放仍旧普通透明，透体未修；本轮无UE/PPSSPP/安装/桌面UI。GEF3未接UE C++pass，默认M1未换，HD/clock/AI/原碰撞/伤害受击倒地/命名手骨枪口均未完成。MSVC/SDK RunAs取消终态，授权有效，既有UAC诊断待答，不重复提权。原完整goal active不complete/blocked。

文档GE_RECT_SPRITES_20261021.md。下一步优先原line segments(0x19c PRIM2，当前样本3/4等)、结合原FXweaponlocal候选追真实attachment writer/枪口方向；或HUD/FBOpostprocess。读取raw/Record.cpp观察FRAMEBUF有16byte addr/bufw/flags/pad，drawnVRAM内容可能是RAM旧值、回放依赖先前render target；未核flags不要当本帧GPU groundtruth，也不能PNG代替场景。不要再在当前sprites/natives已通过子集原地反复验证。

## 最新：407次原FX三角条带恢复＋枪口emitter候选，native GPU通过

有实质progress。新recover_ge_strip_fx_scene.py从原12同Aya/gun/creature capture恢复所有mainFB/depth-tested/perspective/unweighted triangle-strip draw：407draw、3081展开点、10新有效CLUT_RGBA，合并3635draw/438105点/88atlas。VTYPE81/102/19f/11e，posS8/S16/F32/UVU8/U16/F32，原RGB或ambient、UV affine（含2、1.84375、13.953125等scale/offset），strip奇偶winding/退化顺序保留。源lighting0、smooth1、GEQUAL、noDepthWrite、stenciloff；blend32/76/a6，sampler repeat/clamp，min7但mipmax0。T3BGEF2自定义导出flags，不是PSP格式。

重要源精度修复：inputs_v1失败cullmode1、v2失败非unitUV，producer+failure留档。inputs_v3统一Ayaorigin导致FX VIEW内placement相消，sample0投影误差.055496PSPpx>既定.01，failedproducer/auditor留b52e...。最终inputs_v4每FX原WORLD bboxcenter局部origin+等价matrix，最大可见误差.0000376102PSPpx，未放宽阈值，不是screenPNG，也不是全FX共world坐标语义；每draw原VIEW仍保留。

Tools新增ge_strip_fx_reference.cpp/.hlsl/run_ge_strip_fx.py/verify_ge_strip_fx.py。shader在fog后按未截断2*a预乘RGB，BlendSrcONE+DestInvClamped2Alpha或ONE，支持原alphaTest开关/UVsampler/winding；不同camera的FX不当background。成功runeb127720dab34700b91773818e73350e/PID79512 exit0，91真实GPUcaptures，independent_verification passed。原435024条GPU VS输出byte同f99 baseline，no_effects RGB/canonicalowner/depthStencil byte同；FX不改mainDepth。新增3081SO输入/UVcolor/clip/fog与原source重算通过；88GPUatlas byte同。3doublealpha controls RGB [48,96,144]/[96,191,255]/[128,255,255]，旧fog/stencil控制byte同。失败efd737(合成漏blend-enable)、57a850/cd9e(错误约束disabled-blend未使用factors)全留报告；GetDesc实测disabled runtime规范化ONE/ZERO，现仅对active检查factors，所有active/数值检查仍严格。root实际view全部CONTACT_SHEET，见烟雾/闪光/红色碎片/地面暗影。连续D3D算术≠完整PSP integer pixel/D16/alpha-stencil。

新analyze_ge_fx_weapon_anchors.py：FX local0经原WORLD/VIEW/invMainVIEW→commonPSPworld→invGunRigid(BONEweight×WORLD)到原gunlocal，gunrigid对生产输出F32bound通过，candidateXYW projection同主相机。14/15-point strips在samples1/2/11共享origin，每帧二draw实际一个独立观察，共3次；mean[-1.0844841053,.0004692606,.1264725467]，maxrawlocalresidual .0020478362，位于gun负X端外侧，支持muzzle-emitter假设。out/GE_STRIP_FX_20261021/weapon_anchor_candidates_v1/candidates.json。**尚未定位原attachment writer/named muzzle；非确认socket/方向，未替M1binding，邻1/2相似不能说6独立姿态**。

run含PREVIEW手动选source/no_effects/effects_only等7模式、91PNG+contact、audit源码身份、候选JSON、官方DrawPixel留URL/SHA。source_protection从上轮184旧+新候选=185UE包和3原文件hash全同。本轮无UE/PPSSPP/安装/桌面操作。旧UE40fedc9...异形回放数据验收仍有效，但原透明透体/独立背景fogstencil未修、formalCpp未编译、M1默认未换、HD未完成。授权有效，RunAs取消终态/UAC诊断待答，不重问授权不重试。

文档GE_STRIP_FX_20261021.md。下一步有意义前沿：恢复source VTYPE119矩形sprites（每帧千余点，需查官方Rasterizer/TransformUnit rectangle颜色/第二点depth/屏幕轴对齐规则；不能任意worldquad），line/HUD/FBOpostprocess或追这份武器FXanchor真实writer。不要在已通过triangle-strip/native数据上原地反复验证。完整goal active，AI/原碰撞/伤害/受击倒地/精确clock/命名手骨枪口/正式UE/HD全未完成。

## 最新：原11-bone异形已实际UE同帧回放，数据验收通过，透明视觉仍未修复

UE5.8.4 CL58902052/D3D11 content-only run40fedc9fa49f4ad3ab9660645c77717e，PID87112自然exit0。新ge_other_actor_capture.py读取OTHER_ACTOR_GE_PAIRED_20261021/runtime_v1证明，与Aya/gun同12份capture严格匹配，28临时DynamicMesh逐packet回放1800点/帧。不是UE SkeletalMesh/AnimationSequence，原clock未恢复。新--other-actor-runtime选项要求street-series/cameras/reuse weapon mat，默认旧路径保持。producer/headless冻结helper/commands/进程身份；原drawgroup都早于Aya/gun，sort -100..-73，street更早。实际组件identity worldtransform，原WORLD含于kernel worldpos，不人为居中。

发现旧M_Twisted_000源bundle cull0/双面，而当批336draw原r1d=1，需要单面。只新增/Game/T3B/NativeCandidates/OtherActorGEPaired/Run_40fedc9fa49f4ad3ab9660645c77717e/M_Creature_SourceCull，duplicate原材质，two_sided=false，保持透明unlit原texture/graph，metadata标新来源。184旧UE包全不改，新增1包；今后保护应含该新包，旧baseline184仍保留。原Texture2D Source RGBA f2bb1be7...3d306匹配256²原CLUT。

新verify_ue_other_actor.py passed：336draw/21600组件positionF64、normal/colorF32bits、UV/tri顺序全同生产proof，readback完整无gap/overlap；actualtexture SourceRGBA逐byte同原。独立camera72GPU markers/max.548436PSPpx通过；streetseries1568draw/358488点/73SourceTextures通过。60张actor-hiddenbaseline controls逐像素同f13b293...；异形alone3382..8929visiblepx，每组加入后RGBdelta3032..8804。root实际看sample0与全部OTHER_ACTOR_CONTACT_SHEET。97framePNG＋75textureSourcePNG＋3contact=175PNG。PREVIEW.html可选allactors/原无异形baseline/onlycreature。audit_identity源码冻结；source_protection末尾核ISO/slot0/INI＋184旧包全同，newcandidatehash单列。

**视觉未验收**：UE普通透明mainDepth不写，Aya背面露出正面/透体仍在截图可见；新UEstreet仍旧matchedbank，不含native新backgroundcamera/fog/stencil。正式GE C++pass未编译加载，默认M1未换、HD材质/AI/原碰撞/伤害受击倒地/手骨枪口/精确时钟未完成。原MSVC/SDK RunAs提权取消终态未变，本轮无安装/PPSSPP/桌面UI，现有UAC诊断待回，不重复启动/不重问授权。完整goal active，不标complete/blocked。

文档OTHER_ACTOR_SAME_GE_UE_20261021.md。下一步推进真正UErenderer/原战斗/FX或原clock证据；不要把已通过geometry回放再当新进展反复验证。新原异形形态和11源indices已明确，具体怪名/解剖骨名仍未知；旧60sample sourceclip不同capture不混。正式Cpp工具链未解决前优先可独立做的原数据行为恢复，勿用Masked/depth预通道假冒原source-alpha+逐drawdepth。

## 最新：原版11-bone异形按同Aya/gun捕获恢复，12组完整native场景通过

本轮有实质progress，不是blocked。新recover_other_actor_ge_series.py读取同12份GE，按ORIGINAL_ACTOR_SOURCE_METADATA已验证ordered28packet vertexSHA精确匹配；每帧1800点，336draw／21600点。原pos/normal/weights/UV逐分量对metadata，实际BONE继承按palette→source indices恢复完整11矩阵，所有重复source同帧payload严格一致，11骨在全部11相邻步均变化；同组WORLD一致，VIEW/PROJ同Aya。具体敌人名和解剖骨名未证，不混旧60CPUclip/原clock。out/OTHER_ACTOR_GE_PAIRED_20261021/inputs_v1；comparison_v1实际pinnedPPSSPP Math3D/Lighting transform/color mismatch0；runtime_v1实际compile生产T3BGESeries/Lighting+新ge_other_actor_series_probe.cpp，21600输出byte同reference，UVbits同源。

export_observed_ge_scene.py新增可选--other-actor-proof，默认原subset保留。out/OBSERVED_GE_SCENE_20261021/inputs_with_actor_v1共有3228draw／435024verts／78原CLUT_RGBA atlas。当前12捕获所有weighted draws已包含，剩余FX/HUD等无权重draw仍excluded，不是全游戏覆盖。真实native runf99ea978f2644fe3aa63b5af15c39251/PID77984自然exit0，64GPUcaptures。verify_ge_observed_scene.py支持3rdactor，新增独立rawBONE/lightingheader/decodedpos-normal-weights-UV审计与所有flags从原regs重算，independent_verification.json passed，projection max0.0000619505PSPpx。新verify_ge_actor_addition.py passed：对d167baseline保留draw输入/矩阵/flags/textureidentity顺序完全同，VS/PS DXBC同，每组只加28draw/1800点，异形finalowner2672..8755px，RGBdelta2731..8763。root实际view全部CONTACT_SHEET，原异形在12组画面均可见。

run保留audit源码identities、PREVIEW.html手动样本＋no_creature基线对照、source_protection核3原文件＋184旧UE包全同。未启动UE/PPSSPP、未改旧包／存档、未做系统安装；Windows提权先前取消终态仍未解决，已有UAC诊断待答，不重问授权/不重复启动。新成果尚未进入UE C++pass/正式M1；原素材不是HD。D3D11完整PSP栅格/D16/alpha-stencil耦合仍不等价；原clock、AI、原碰撞、伤害/受击/倒地及HD材质未完成。doc OTHER_ACTOR_SAME_GE_SCENE_20261021.md。

下一步优先把这份同帧11-bone原异形输入接入UE（现有M_Twisted_000/原256²texture已在Content，需核schema/colorDouble/原cull；不能把普通translucency称原mainDepth等价），并继续剩余无权重FX／原战斗行为。正式UE C++pass还只旧twoatlas且未编译，MSVC/SDK需要真实UAC问题解决后UBT。不要回到已通过native子集原地反复跑验证。

## 最新：原逐 draw 独立相机背景／未匹配街景＋fog/stencil 子集，native GPU 通过

run d16757dbab6645ababbe99e4d838841d／PID80080 exit0，RTX2080Ti native D3D11；12 samples所有observed无权重VTYPE11f＋Aya106/gun1，共2892draw／413424vertices／77原RGBA atlas。此前40 unmatched观察／10548点现已native渲染，逐draw自身VIEW/PROJ保留，不套主相机。不是新增UE成果。64真实GPU采集（12*5＋4synthetic），独立原PPDMP重算／GPU SO通过，可见投影max0.0000619505PSPpx；77GPU staging atlas逐byte同原CLUT；fog控制3色和depthfail stencil73通过。所有background关闭主depth/stencil不变、fog关闭owner/depth不变、nodepth unioncoverage不变。

首次auditor错误要求每组background改变RGB，在4..7被后续scene完全覆盖时失败。failed_auditor_v1.py／failed_audit_v1.json已保留。修正为核单独background覆盖、off-background owner、最终background owner一致；4..7无未覆盖背景且RGB无差，其余8有差。已有PNG只读像素核对不覆盖，精度阈值未改。最终independent_verification.json passed，audit_identity保留源码。root实际看sample0和全部CONTACT_SHEET；PREVIEW.html仅手动选样本，无原clock／插值声明。官方DrawPixel.cpp v1.20.4已留URL/SHA。

Tools新增ge_observed_scene_reference.cpp／ge_observed_scene.hlsl／run_ge_observed_scene.py／verify_ge_observed_scene.py；psp_parse/tools/export_observed_ge_scene.py，导出out/OBSERVED_GE_SCENE_20261021/inputs_v1。T3BGEF1是导出桥接格式。深度D24S8、RGB-only，未复现PSP framebuffer alpha/stencil耦合／完整固定点栅格／D16depth；其余weighted actors/FX/HUD仍excluded。当前UE C++pass还只支持旧2atlas子集且未编译；未写UE新asset／未替M1默认world／原素材未HD化。

新source_protection.json核3原文件＋184旧UE包全同。用户授权有效，但真实Windows提权上次取消、安装未启动；本轮fresh目录仍缺MSVC／SDK22621，无installer在运行。现有UAC诊断待答复，不重问授权／不重复提权。完整HD/M1 goal active。下一步解决真实UAC后正式UBT并将逐draw源状态接入UE；也可继续未覆盖源角色/FX解析。文档OBSERVED_GE_SCENE_GPU_20261021.md。

## 最新：12组逐采样街景实例＋Aya/gun实际UE回放，1568draw／358488点通过

恢复recovery_v1：psp_parse/out/PAIRED_STREET_SERIES_20261021，12个child snapshot，前4组140draw，后8组126draw，共1568/358488points。recover_paired_street_snapshot.py增加recover(out,sample)，按rawGeomID＋material/实际CLUT匹配而不是只固定WORLD；同WORLD优先，变体保留实际WORLD和candidate IDs，objectidentity=false不插值。新recover_paired_street_series.py导出series.json，执行producer和snapshot依赖冻结留SHA，所有child producerSHA一致；sample0 binary同旧snapshot逐byte。原140instances实际128vertex-signatures；9种signature整组多WORLD，其中6种已在旧参考多实例，另3种参考外WORLD（旧draw67/68/69同组平移），不能说3物体动画或9动画通道。

实际UE5.8.4/D3D11 runf13b293ea4de4f258b16b4d7250f9339/PID85364自然exit0，source-camera content-only。新ge_paired_street_series_capture.py复用140render slots，rawGeom一样只改position，不同就reset原UV/colors/triangles；sample4重建89槽，隐藏14多余槽，后续复用。数值structured componenttransform identity，不拿内存地址/slot当对象ID。headless CLI显式--street-series与--street-snapshot互斥，默认模式不变；capture主体按series采12而非旧单snapshot1。实际73framePNGs（36actor+1hidden+12marker+24street）及73streetTexture2DSourcePNG/1gunTextureSource；root实际看过STREET_CONTACT_SHEET。

独立verify_ue_paired_street_series.py passed：全量原PPDMP观测bank draw key集合无增删，1568原PRIMregs/矩阵与358488component位置F64重算bits、colors/UV/triangle顺序一致；offset全流无gap/overlap；73真实Texture2D Source RGBA同当份CLUT。12组actor-alone图同已接受camera baseline逐像素同，sample0 street两图同旧snapshot逐像素同。旧verify_ue_original_camera.py复跑当前新run通过72GPU marker/max0.548436PSPpx。CPU componentpos plumbing≠原PSP GPU arithmetic读回，formalCppGEpass没加载，当前透体/fog/stencil/透明主depth仍未通过。原钟unknown，手动preview不循环/插值。

**下一步源数据更完整范围**：auditor列40次未匹配VTYPE11f观察（不在旧street bank），8 vertex payload signatures/7CLUT解码RGBA variants，不能把它们等同authored asset个数。unmatched_v1/observations.json保存所有matrix/regs/source与7原PNG，semantic_name=null，当前UE未渲染。每组有594vertex draw（record10；frame8另378vertex record15等），594的VIEW平移0、VIEW和PROJ都不同main camera、fog0/depthwrite0；root实际view其128x128原贴图是云层，**背景天空用途仅推断**，不要套maincamera，也不要把黑背景当原sky不存在。其余54/18/72等新worlddraw也需接入，不止旧稳定bank。下一步恢复这类独立drawcamera/未知资源，推进真实全场景，不在已通过子集原地验证。

184旧包和ISO/slot0/INI hash重查全同，无new/deleted package、PPSSPP、系统安装/桌面操作。本轮仅只读查看UBT寻找路径，未下载portable toolchain或绕过UAC；原官方installer先前RunAs取消终态不变（非live），既有UAC诊断问题待答复，不重问授权/不重试安装。完整HD/M1goal active，Twisted/原碰撞/HD材质/真正UBT等仍未完成。

文档 docs/PAIRED_STREET_SERIES_UE_20261021.md；预览 work/t3b_unreal/Validation/paired_street_series_ue_runs/f13b293ea4de4f258b16b4d7250f9339/PREVIEW.html；当前验收 independent_street_series_verification.json，source_protection/audit_identity留档。

## 最新：同原GE sample0的140街景draw＋Aya／原枪械实际UE同帧接入

实际UE5.8.4/D3D11 content-only runf42f69bcedf741fd9515fcfc9d7a72c9/PID87020自然exit0；root实际看过00_original_street_with_aya_weapon.png，原路面/建筑/警用路障/托盘/树/路桩围绕Aya＋gun，同一原版机位。不是背景PNG。新recover_paired_street_snapshot.py从同dump source0匹配140旧street vertex+WORLD，原UV/RGBA/POS16，无normals/weights；当前units/origin/XZY坐标，T3BSTG1桥接。全部材质参数和原CLUT解码必须与既有M_Street候选对应；73原PNG保留。旧relativeAyaScene anchor没有混用。

新UE helper ge_paired_street_capture.py建立140临时DynamicMesh、复用81M_Street材质，读回31656位置F64/colorF32、triangle index／UV，73真实Texture2DSourcePNG导出。tools/capture_weapon_ge_paired.py/_headless新增显式--street-snapshot，必须--cameras且reuse旧材质；只采source0，默认旧12模式不变。独立verify_ue_paired_street.py验收通过：140draw/31656点位置double和color/UV bits、原triorder/multiplicity一致；73实际Texture2D Source逐RGBA同原dump CLUT。原Aya/gun3699component点同旧accepted baseline；camera property同旧run，scene隐藏时hidden/body/gun/combined四控制图逐像素同5a76f509..。街景96575非噪声px，加入Aya/gun改变3910px。

source scene records17..752全早于Aya884..1199／gun1204，priority=-1000+i仅保持组序；112不blend、23blend+depthwrite、5blend不depthwrite，140均fog1/stencil1。当前UE普通材质没有实现完整fog/stencil/透明主depth，C++GEpass没加载，M1默认world没换，不称HD材质／完整关卡／原碰撞／Twisted完成。normal缺失但四lights均off、materialupdate7/globalambient全白/emissive0，条件性ambient整数映射256channels为identity，原RGBA保留。componentTransform仅6decimal repr，positionbit是component local数据；默认actor identity，无GPUscenevertexreadback声明。

额外12dump只读series_world_coverage.json发现samples0..3=140旧geometry+WORLD，samples4..11=123相同＋3同geometry但WORLD改变，其它旧draw未观察；**不要把source0快照重用成所有时刻固定街景**。3变化语义unknown，不直接叫billboard/tree。snapshot_v1/执行源码、数据身份、73原PNG在psp_parse/out/ORIGINAL_SCENE_GE_REPLAY_20261021；官方Rasterizer.cpp及SHA保留供fog调查，PixelFunc.cpp404已记录未获取。184旧包和ISO/slot0/INI hash全同，没有新package、PPSSPP、系统安装/桌面操作。官方installer本轮未重试；现有UAC诊断仍待回复，已授权但实际Windows提权取消的状态不变（见下方终态，不是live job）。

文档 docs/PAIRED_STREET_UE_20261021.md；实际预览 work/t3b_unreal/Validation/paired_street_ue_runs/f42f69bcedf741fd9515fcfc9d7a72c9/PREVIEW.html。下一步可恢复3个变化WORLD／逐帧scene subset，推进原fog/stencil/源blend-depth统一GEpass；正式UBT要先解决真实UAC。完整HD/M1goal仍active。

## 工具链状态更新：Windows提权返回“操作已被用户取消”，安装未启动

用户安装授权仍有明确记录，但当前RunAs请求已terminal：exec session31121退出1，父PID89056已不在进程列表；Start-Process返回“操作已被用户取消”，没有installer PID、process_started.json或组件安装成功记录。Validation/toolchain_install_runs/f041d28d9c114afbb23324f1d76b4c5a/install_error.json及terminal_status.json留档，retained_logs.json为空。不能把下方早先pending提权段落当最新live状态；不要再poll缺失session或把它叫verified wait，也没有后台安装在运行。没有重复启动/UAC。已有诊断async问题“是否看到Microsoft安装器UAC提示”仍待用户回；不是重问安装许可。下一步根据该诊断回复解决实际Windows提权，再安装原参数并真验MSVC/SDK/UBT。不要仅因聊天已授权就声称安装完成。

本轮UE原相机验证成果完整保留：5a76f5096f5c46be84c5d8f1260a1f29/independent_camera_verification.json通过72GPU markers、44388component点，184包/原ISO存档INI不变。GE C++pass与M1仍未完成，goal active。

## 最新：原版相机实际UE验证通过；用户已授权工具链安装，当前Windows提权请求待完成

实际UE5.8.4/D3D11 content-only run5a76f5096f5c46be84c5d8f1260a1f29/PID85340自然exit0。12原同dump Aya+gun，原相机adapter采用真实UE component matrix求残差customProjection，保留源F24非正交VIEW而非仅拟合FOV。49framePNG（36角色图+1hidden+12marker）＋1原weaponTexturePNG。真实组件44388点position F64/color&normal F32 bit同原参考，sample0/11拓扑UV保持；72隔离opaque/unlit coloredquad实际GPU图中心距原机投影≤1PSPpx，max.5484361901722512。independent_camera_verification.json passed。GPU marker证明实际SceneCapture投影，CPU property不假冒FViewInfo/GPUvertex读取。

root实际看过CONTACT_SHEET、00marker、NATIVE_UE_COMPARISON。当前UE仍有背面显示前脸／手臂透体，native depthOFF呈同类缺陷；GE depthON改善。新C++GEpass没有加载、正式M1未换，不称HD材质/动作时钟/完整像素完成。184旧包及原ISO/slot0/INI再次hash相同。tools/capture_weapon_ge_paired.py/_headless新增optin --cameras，默认旧校准不变；新helper ge_source_camera_capture.py、独立auditor verify_ue_original_camera.py。三次producer失败da3954(错误材质报告路径)、123b66(VertexColor输出名RGB错误)、189b05(Quat缺少API)留档，启动前输入check已补。strictblack auditor失败也保留：actual hidden只有0/1中性灰；查过UEtonemapper dither代码，最终限定1LSB灰，不宣称色彩等价，marker1px和componentbit阈值未松。

**重要新授权**：用户回复call_dd518683bf384277b96808c66a12bd89“允许后台安装（推荐）”。此前MSVC/SDK授权阻塞已解除，不要再问安装许可。按原plan下载aka.ms/vs/17/release/vs_BuildTools.exe，Microsoft Authenticode Valid，fileversion17.14.37806.7，SHA2a6aa7d94e38d457a4eb3930fc60056ecab06865b2eb925e5275b8473a017583；在Validation/toolchain_install_runs/f041d28d9c114afbb23324f1d76b4c5a保存authorization、download_verified与run_authorized_install.ps1。非admin父pwsh通过Start-Process -Verb RunAs -WindowStyle Hidden按既有quiet/wait/norestart/nocache+VCTools/MSVC14.44/SDK22621启动。当前**exec session31121仍live，stage requesting_windows_elevation，parent_pid89056；尚无process_started.json，未发现installer PID**。不要重复启动或擅自终止；先poll同一write_stdin session/父PID和文件真实状态。用户已收到诊断async问题“是否看到UAC提示”，不是重问授权，答案仍待回。不可把提权pending称为组件安装或UBT通过。启动后按handle等终态并验cl≥14.44.35211、SDK22621，再真实UBT。

完整说明 docs/AYA_ORIGINAL_CAMERA_UE_20261021.md；实际预览 work/t3b_unreal/Validation/original_camera_ue_runs/5a76f5096f5c46be84c5d8f1260a1f29/PREVIEW.html。完整HD/M1goal仍active。

## 最新：12份原版相机恢复，24图与44,388条实际GPU顶点通过投影检查

原GE逐PRIM恢复12个shooting-input样本的VIEW/PROJECTION/viewport，1284draws（Aya106+gun1每帧）同机位。FOV由projection推导约40→35.2→29.2→28度，不是新恢复authored camera/time。实测GE depth clamp=1；recovery_v1错误预设0被拒绝，failed_producer/failure留档；recovery_v2另存原payload与T3BCAM1导出矩阵。新 tools/recover_original_ge_cameras.py 没猜INIT矩阵，逐PRIM核对旧body/weapon记录。

真实native run82e331c301ed4ecaa7832b97a9a673dd/PID81488/RTX2080Ti自然exit0；原几何/贴图/colors/draworder＋当前UE WorldToClip shader主体（directFXC，非UEcompiler）恢复源机位。12samples*depthOFF/ON=24张480x272实际GPU图，另44,388条VS stream-output记录。独立原world点→原view/projection→原viewport与GPU最大屏幕误差3.986104880482344e-05个PSP像素；UV/color bits保留。auditor加强版从原PRIM二进制独立解码viewport而非依赖producer metadata，independent_source_register_verification.json通过，旧auditor/report没覆盖。

原depth clamp虽1，本批W>0且所有选定顶点及三角内部在Z clip内，normalizeddepth约.16638..25176；不能推广到全场景。depthON/OFF unioncoverage相同，总8398 RGB/7684owner改变。sample6/7 gun finalowner为0，但243原顶点/draw保留，不强制透体、不证明named muzzle可见。root实际看过CONTACT_SHEET，PREVIEW.html可选sample/depth；原分辨率、黑背景无场景、未做HD贴图或原机像素验收。

native ge_depth_reference.cpp仅新增optin worldShader80byte常量/原入口和ATTRIBUTE layout；旧默认校准实跑a6b4f9f1e3784ccd9d717ac96588cd2f/PID85156 exit0，52采集独立验收通过，156 GPU raw buffers同旧6bb逐byte。184包、原ISO/slot0/INI、11UEruntime/shader/module源码hash相同。没有UE/PPSSPP/桌面/系统安装；UE formal M1仍未接入。文档 docs/AYA_ORIGINAL_GE_CAMERA_20261021.md。下一步可用既有content-only UE/Python检查SceneCapture自定义projection与camera VIEW，再做实际UE原机位对照；正式C++工具链安装问题仍待既有回复，不能把自动goal延续当授权。

## 最新：当前 WorldToClip / pre-exposure shader 主体通过独立 GPU 检查

run60d238a224c944c5a7138a0134590949/PID17696/RTX2080Ti 自然 exit0。直接 FXC 编译当前 T3BGEOrdered.usf MainVS/MainPS（仅移除未使用的 Engine Platform include、内联原共享 ush），不是 UE shader compiler。3组独立矩阵／15条实际 VS stream-output 记录投影通过，UV/color bits不变，row-major reflection及80byte constants offsets确认；4档曝光＋alpha0 discard共1280像素在RGBA32F/R32UINT staging读回精确通过，HDR值最高8保留、alpha不随曝光改变。新增 Tools/ge_world_shader_probe.cpp、run_ge_world_shader_probe.py、verify_ge_world_shader_probe.py；源码/DXBC/命令/PID/独立auditor身份已留档。

UE module/相机参数绑定/RDG/场景blend/完整M1仍未实编验收；原游戏相机／原动作没有新增采集。UEruntime/shader源码未改。184旧包、原ISO/slot0/INI再次hash相同，未新增package／启动UE或PPSSPP／下载或安装组件。MSVC/SDK安装确认仍待此前问题答复，不把自动延续当授权。详见 docs/UE_GE_WORLD_SHADER_GPU_PROBE_20261021.md；实测报告为 work/t3b_unreal/Validation/ge_world_shader_probe_runs/60d238a224c944c5a7138a0134590949/independent_verification.json。

## 最新：UE原生3D按序GE pass已实现；生产loader/shared shader实际GPU回归零差，UE module仍待编译

本轮真实progress：不再只做native参考，已写入UE actor/ViewExtension/RDG真实3D几何pass，但正式UE C++/shader wrapper尚未编译或执行，不称UE透体已修复，M1/完整HDgoal仍active。无系统安装/SDK下载、无UE/PPSSPP启动/桌面UI；native进程已terminal。

新增Public/T3BGEGeometry.h、Private/T3BGEGeometry.cpp：engine-independent T3BGPU1 exported兼容geometry reader，2原RGBAatlas、frame source order和GPUVertex9F32/36bytes。有限数/UNORM范围/bounds/trianglecount/ordinal检查。不是原PSP格式，也不包含原clock/骨骼socket。新增Public/T3BGEReplayActor.h及Private cpp：LoadOriginalGEBundle读取真实3D样本、CreateTransient PF_R8G8B8A8/SRGBfalse/NeverStream，两图纹理；SetCapturedSample选样本，Actor平移/旋转统一作用body+gun，限定unit scale，非有限transform隐藏不回退。bSourceReady仅dataready。默认不播放，可选30fps preview clamped、不推断loop/原时序。WriteSubmittedFrame生成T3BSUB1 CPUsubmission（sample/draw/vertex header＋sections3u32＋vertices9F32），不是GPUreadback。

新增Private/T3BGEViewExtension.h/cpp：同world FWorldSceneViewExtension在PrePostProcess使用实际SceneColor/SceneDepth，Renderer5.8 FViewInfo ViewRect/PreExposure/WorldToClip，RDG tracking VB/twoAtlas/RT-depth依赖；不可变Frame和RHItextureRefs在RT持有。逐draw source-alphaADD、RGB-only、GREATER_EQUAL＋main depth写入；MRT1R32UINT写最后drawowner，单面cull按View.bReverseCulling。r.T3BGE.DepthWrite默认1，0仅诊断，RHIstate及RDG access同步。Shaders/Private/T3BGECommon.ush共享原pixel combine；T3BGEOrdered.usf实际world3D投影，row_major matrix，ScenePreExposure。不是生成PNG贴到UE。初版范围single-sample desktopSM5+/two-atlas/no-stencil；MSAA/mobile/VR/primitive show-only/其他UE透明相对顺序/velocity/TAA等未验。HDR/RGBA8量化差、原fog/相机/stencil仍未解决；颜色为捕获时bakedGEcolors，actor移动不等于原动态灯光恢复。

Module/build已改：T3BRemake.Build.cs增加RenderCore/RHI/Renderer及RendererPrivate/Internalinclude；T3BRemake.uproject加载期Default→PostConfigInit确保globalshader早注册；T3BRemake.cpp自定义startup映射/T3B到项目Shaders，cooked data不要求physical shader目录。旧SourceData/native候选/默认T3BReplayWorld未换；新actoroptin，不能在legacybody上叠加然后宣称默认M1已完成。源级API依据本机5.8 headers看过，不等于ABI/UBT通过。

**实际native回归覆盖生产部分**：Tools/ge_depth_reference.cpp已删除自身读取循环，使用同production LoadGPUGeometry；Tools/ge_depth_reference.hlsl调用与UE同一T3BGECommon.ush，builder在编译前冻结并内联common shader、复制production h/cpp。正式run6bb0e3db0bcd40cb98ba9f66aceae654/PID82312自然exit0，真实g++/D3DCompile/D3D11/2080Ti。48原model＋4synthetic=52实际硬件采集；root独立verify_ge_depth_reference仍通过。对原ac1f31基线52*3=156raw颜色/owner/depth buffers全部逐byte相同。9损坏输入实际拒绝magic/atlascount/textureid/ordinal/非triangle count/nonfinite pos/color>1/truncate/trailing。production_core_gpu_parity.json在6bb目录，当前production loader h/cpp/common shader与实际compiled copies SHA相同。它不覆盖UE WorldToClip wrapper/actor lifecycle/transienttexture/RDG。先前ac1f31证据未改。

**准备的UE实际验收仍未执行**：Tools/capture_ge_ordered_pass.py＋_headless.py＋verify_ue_ordered_ge_pass.py，普通Python py_compile语法通过，不能称UE执行。wrapper发现无Binaries/Win64/UnrealEditor-T3BRemake.dll就拒绝启动（本轮没浪费启动）；未来真正T3BRemake.uproject/D3D11载C++actor捕12samples*2views*2depth=48PNG+hidden，导出CPU submitted data，root verifier对原bundle比较vertex/UV/color bits与drawatlas顺序、相机identity、PNG前景和depth干预变化，UBT provenance/GPUvertex/depth readback仍独立需要。新脚本没运行、没任何新UE验收green记录，至此没有UEclass真实截图。

完整说明docs/UE_GE_ORDERED_PASS_IMPLEMENTATION_20261021.md；Validation/ue_ge_pass_implementation_20261021/implementation_status.json含所有新source SHA和scopeflags（UE_module_built=false, UE_pass_executed=false, UE_shader_wrapper_compiled=false），asset_protection.json核184旧包不变，source_protection.json新全hash确认原ISO448a90...a15bc、slot0 32f7fe...dc39、INId75494...ca34未变，active_capture_processes=[]。

**安装确认继续pending**：先前functions.request_user_input_async询问的MSVC14.44＋WindowsSDK22621官方后台安装尚无用户答复。此turn只收到日期/环境更新（用户本地2026-10-21），不是安装授权。不要重复提问或用自动goal续行当许可。当前常见vswhere/MSVC/WindowsSDK及C:\BuildTools\VS2022仍未发现完整工具链，未下载/执行任何installer。review方案Validation/toolchain_install_plan_20261020.json保持awaiting_explicit_user_decision。用户明确允许后再官方bootstrapper验签/版本、后台安装持有进程handle+logs/延后重启，fresh核UEban范围及SDKheaders/libs/rc后真正UBT。若用户自装则先fresh核；若不装继续可支持解析/参考，不虚报UEbuild。三旧worker usage-limit已结束，不再重启。

下一步优先实际UBT→修真实编译诊断→新UEactor/orderedpass的真实48图与提交数据／RHI读回验收，再接M1；不得用prepass/masked或2D图替代原source-alpha＋逐draw depth写入，不把共享nativeGPU回归冒充新UErenderer测试。原clock/命名手骨socket/muzzle/完整场景与战斗仍未完成。

## 最新：原Aya／枪械的实际D3D11主深度干预已通过；UE工具链安装正在等待用户决定

本轮真实progress，完整高清重制/M1仍active未完成。上一turn同GE12帧UE回放/原顺序已真实通过；这轮新增独立硬件GPU对照，仍没有修复正式UE renderer。不得将native GPU参考叫UE修复。无系统安装、UE/PPSSPP启动或桌面自动化；所有本轮native进程terminal，无待采集任务。

**GPU实现与输入**：Tools/ge_depth_reference.cpp＋.hlsl、run_ge_depth_reference.py、verify_ge_depth_reference.py。使用同12份原PPDMP的106Aya＋1gundraw，共3699vertices/1233tris/frame；输入为旧production reader/kernel对独立PPSSPP software reference已逐byte核验的WORLD positions/primaryColors＋原F32UV，减共同origin/units转UEcm后F32。每帧按原GE record/word排107draw，首帧body→weapon、其余weapon→body。两张原atlas实际D3D11Upload/Mapreadback字节全同；native owned device无窗口，不借UEdevice。HLSL固定相同±Y正交512x768，MODULATE/rgb*2/SRCALPHA+INVSRCALPHA ADD，alpha仍混合，singleBACK/FrontCCWtrue（源GE和UE D3D映射一致），GREATER_EQUAL+clear0。两模式唯一干预DepthWriteALL/ZERO；实际OMGetDepthStencilState/Blend/RS读回检查。MRT0RGBA8仅RGB写/alpha保持255、MRT1R32uint最后通过draw owner、D32float depth，都实际staging Map。

首次run0e254e1e54f948a89c1a23e8139b2e28因Windows near宏导致g++Werror编译失败，源码/log保留。变量改isNearLayer后正式runac1f31b9c5e142d1a07a2cbc5f1cf481，g++13.2 C++17/O2/WallWextraWerror，链接已有d3d11/d3dcompiler/dxgi/dxguid。shader/cpp编译前冻结，D3DCompile实际vs_5_0/ps_5_0留DXBC。实际DXGI设备NVIDIA2080Ti/FL11_0，PID82388自然exit0。48原几何采集（12*2view*2depth）＋4明确synthetic；rawrgba/owner_u32/depth_f32均在run目录。

**独立核对**：root verifier不importbuilder，读冻结bundle/每draw输入hash/texture/进程和GPUMap文件，52采集通过；禁写depth全0，写组depth>0范围与owner>0全同，24对照union raster/alpha coverage全同。累计RGB改109953pixel/owner改100540；sample11−Y枪最终owner1028→3395，RGB5364改。owner不是全部混合贡献。root实际view sample11−Y OFF/ON，枪身从身体覆盖中恢复、手臂错误覆盖改善。PNG只是GPUrawRGBA无修改编码。

**合成控制不是原观测**：红near0.8/蓝far0.2，alpha128/255，中心实际RGBA严格match独立期望：near→far写[128,0,0,255],owner1,z≈.8；禁写[64,0,128,255],owner2,z0；far→near两模式[128,0,64,255],owner2，写z≈.8/禁写0。证明顺序blend+depthwrite仍保留far的贡献；只nearest depth预通道会丢蓝贡献，不能Masked/简单prepass替代原行为。这不是说UE所有auxpass测试过。当前自选calibrationcamera+D32、D3D11插值/UNORM、无原fog/stencil/PSP16bitdepth/outputcolor，不叫原PSP像素保真或正式M1。

实际图/interactive PREVIEW.html与CAPTURE_REVIEW.md在runac1f31...，全说明docs/AYA_GPU_DEPTH_INTERVENTION_20261020.md。最后source_protection.json于2026-10-20 15:40UTC完整核原ISO448a90...a15bc、slot0存档32f7fe...dc39、INI d75494...ca34不变，active_capture_processes=[]；UE_package_protection.json重新哈希原184包全部同96556baseline。UE代码/uproject/原包本轮未改，仅新增Tools/Validation/docs。

**重要：安装确认待用户回答，不能当作授权**。本轮fresh只读检测常见VS/MSVC/WindowsSDK位置仍无正式组合，vswhere仍缺；已有MinGW+d3d11 headers/libs只足standalone，不能代称UE编译链。真实UE5.8.4 Engine/Config/Windows/Windows_SDK.json偏好MSVC14.44（ban≤14.44.35210，需≥35211）和SDK22621；官方Microsoft文档已查。完整review方案在work/t3b_unreal/Validation/toolchain_install_plan_20261020.json：官方https://aka.ms/vs/17/release/vs_BuildTools.exe，目标C:\BuildTools\VS2022；VCTools workload＋VC.14.44.17.14.x86.x64＋Windows11SDK.22621，quiet/wait/norestart/nocache。没有下载bootstrapper/执行installer/改系统。

functions.request_user_input_async已问“正式UE C++构建仍缺MSVC和WindowsSDK…是否允许后台安装MSVC14.44与WindowsSDK10.0.22621”，选项[允许后台安装（推荐）／我自行安装／暂不安装继续解析]，尚无用户回复。不要重复提问，不把自动goal续行或等待时间当作许可。用户明确允许后才可按review方案下载，验Microsoft Authenticode和实际版本/SHA，隐藏启动并持有installer进程handle/日志，必要UAC由用户处理（不自动UI），任何restart延后，fresh核vswhere+compiler+SDK头库rc且不在UEban范围，再执行真实UBT；安装成功不等于build成功。若用户自装，先fresh核；若不装继续支持的解析/图形对照，保留这个编译缺口。

后续目标仍是真正UE原blend+mainDepthwrite+逐draw顺序的原生渲染适配（可根据当前本机SceneViewExtension/RDG头文件实现；本轮仅初读API，尚无新UEpass源码），精确时钟/骨骼武器挂点枪口/正式战斗。不要把nativeGPU生成2D图贴进UE冒称完成3D集成，也不要用只nearest的masked/prepass改变原半透明blend。任何SDK安装必须等上述明确答复。

## 最新：12个同GE帧的Aya／真实枪械已实际UE回放，原绘制顺序纠正；主深度契约确认

本轮实际progress：上一goal turn已恢复72个Aya GE样本；这轮恢复12个同dump真实枪械，实际UE渲染及root独立审计通过。完整HD remake/M1仍active且未完成。无PPSSPP启动/系统安装/桌面自动化；所有UE processes terminal，无运行中的采集。

新tools/recover_weapon_ge_paired_series.py从原slot0_fire_verified12份PPDMP每份精确找到1个真实枪PRIM：VTYPE0x522、243vert/81tri、geometrySHA168578ab...d42e65a。idle_long60份没有此枪draw，不能插猜测枪。逐dump原weapon VIEW/PROJECTION与全部106Aya draws完全一致，WORLD/BONE独立恢复到out/WEAPON_GE_PAIRED_20261020/inputs_v1。原GE CLUT解码RGBA同既有staged枪贴图。配对依据同dump，非named hand/socket/CPU时间对齐/枪口语义。

comparison_v1实际固定PPSSPPv1.20.4 software Lighting/Math3D对2916枪械点变换bits/颜色bytes零差。runtime_v1实际g++编译同production T3BGESeries/T3BGELighting，Tools/ge_weapon_series_probe.cpp一drawdriver输出逐byte同独立reference、UVbits全同、8坏输入拒绝。production reader/kernel没改、旧body/proof来源保持。新verify_weapon_ge_series_runtime.py为gun对应driver。正式UBT/旧60sample source-bone/weapon/defaultT3BReplayWorld均未替换。

实际UE最终run96556b7a90d140459ecbb45e4cb359b5/PID35964自然exit0，UE5.8.4/D3D11。Tools/capture_weapon_ge_paired.py及_headless.py启动前冻结producer。两个真实DynamicMeshComponent: body3456/1152、weapon243/81；同固定body首帧WORLDorigin、canonicalunits、XZY*100、identityactor/component。原UV/法线及GEcolors；±Y校准相机512x768，manualexposure0，body-only/weapon-only/combined各12*2=72实际PNG＋2hidden controls。武器材质为初run a8dd对M_Weapon_000独立copy，仅TwoSidedfalse恢复sourcecull；最后run显式只读reuse不再存包。旧body单面材质不变；actualTexture2D SourcePNG实际导出RGBA同原GE解码。

**原顺序修复／失败保留**：初run a8dd1edb915b4dd0816d496e9a7bd8bd/PID76728实际采集成功但root审计发现固定body0 weapon1错误；source sample0为body→weapon，其余1..11为weapon→body（没有内部interleave）。root_independent_verification_failed_v1.json保留，不改旧acquisition report。producer改为逐frame实际component priority切换。第二run5de4843273be41379733d75e8e246dfb/PID70176因target变量被GE command tuple覆盖RenderTarget而零样本失败，report/log/原包hash留存。修正weapon_ge_command命名后96556真正通过，未将失败回填为green。source-order调整令部分机位枪身被身体覆盖更明显，保留正确顺序并承认mainDepth未恢复，不调回漂亮的错误顺序。

root Tools/verify_weapon_ge_paired.py不导入extractor，直接核原dump/source摄像机/命令顺序、参考输出与实际UEcomponent数据/PNG：44388点positionF64/normalF32/colorF32bits全同、原拓扑/UV严格同；实际武器Texture2D SourceRGBA exact；12张+Y body-only逐pixel同上轮30e6de...原body对照；combined±Y各12种不同pixel图、均有枪visible对照。最终184旧包hash前后/exit后同，新包0（首a8dd新增孤立材质时原183包亦全同）。GPUvertex/原机位像素/命名握把枪口仍未通过。root实际view最终sample11±Y，武器随姿态但透体及枪身错误覆盖明显。最终run PREVIEW.html可切机位和body/gun/combined，显示每帧原order；CAPTURE_REVIEW.md实际图与边界，全说明docs/WEAPON_GE_PAIRED_20261020.md。

**Depth/blend契约**：out/AYA_DEPTH_BLEND_20261020/depth_blend.json直接读body7632＋gun12＝7644targetPRIM，同一state：ZTESTENABLE1、ZTEST7=GE_COMP_GEQUAL、ZWRITEDISABLE0=写depth开启，alpha GREATER0/mask255，ADD/SRCALPHA/INVSRCALPHA，stencil off，cull1/mode0。实际下载固定PPSSPPv1.20.4 ge_constants.h/GPUState.h、sourceSHA留存。UE本地TranslucentRendering.h::GetTranslucentPassDepthStencilState两branch depthWrite模板参数false，保存源函数excerpt/hash；仅normaltranslucentbasepass，不声称全UE任何auxpass都不可写depth。原Aya atlas24718partialAlpha/40818opaque/0zero；不能Masked替代冒称原blend等价。state mismatch与透体相符，逐像素因果尚未测，depth修复未实现。原draworder正确也不能修复这个差异。

最后out/WEAPON_GE_PAIRED_20261020/source_protection.json于2026-10-20 15:18UTC全hash核ISO448a90...a15bc、slot0存档32f7fe...dc39、INId75494...ca34不变，无PPSSPP/UEcapture进程。后续：真正blend+主depth写入+正确顺序的渲染适配，原camera pixel对照、精确CPU↔GE时序、named weapon/muzzle及正式战斗；不将新12帧配对剪到旧60帧CPU武器clock、不以Mask修饰通过。工具链未变化时不重复UBT失败构建。

## 最新：72个原GE样本动态光照已接入实际UE DynamicMesh回放

本轮有实际进展，完整高清重制goal仍active，正式M1／可玩版没有完成。上一轮仅回答引擎状态，未推进资产／玩法；本轮已从现有完整GE采集恢复并实测新动态路径。无系统安装、无PPSSPP启动、无桌面自动化、无后台任务等待。

原slot0_fire_reverse120_world60只有2份完整GE（实际source samples1/58），不把静态灯光扩写为60帧原数据。新tools/recover_aya_ge_sample_series.py实际解析idle_long60＋slot0_fire_verified12完整PPDMP：每帧106个原Aya packet的完整VTYPE+geometry SHA、顺序、PRIM/count、WORLD/VIEW/PROJECTION/BONE、CLUT/texture/material核对通过，7632draw/248832vertices。原CPU ticks在异步dump之前，精确GE时序未知；预览30fps明确是presentation，不替换旧60source-bone／weapon时间轴，不称完整原动画。每组1灯状态/1原材质，合计2灯状态。

out/AYA_GE_SAMPLE_SERIES_20261020/inputs_v2/inputs.json为新输入。v1 cache key缺纹理decode寄存器，已修为包含TEXFORMAT/TEXSIZE/TEXBUFW/TEXMODE/CLUTFORMAT/knownCLUT并实际重跑v2；v1/v2binary和draw/frame/light records全同。原运行保留v1来源，独立审计显式核v2。v2/recovery_code_retention.json留存producer/依赖是执行后copy，不叫启动前冻结。

新增UE源Public/T3BGESeries.h、Private/T3BGESeries.cpp与Tools/ge_series_probe.cpp。LoadSeries读取T3BLIT1、检查bounds/VTYPE/PRIM/weights/geometry，EvaluateSample逐样本调用T3BGELighting，不推断时钟/骨骼名/插值。tools/build_aya_lighting_reference.py新增--inputs（默认旧3pose不变）；comparison_v1对固定原PPSSPPv1.20.4 Lighting/Math3D software SSE4模型的248832顶点变换bits/颜色bytes零差异。tools/verify_aya_ge_series_runtime.py实际g++13.2/O2/msse4.1/ffp-contractoff/WallWextraWerror编译productionreader/kernel/probe，runtime_v1输出逐byte同独立reference、UVbits全同；8坏输入实际拒绝。正式UBT仍未通过；正式T3BReplayWorld默认face shading/source-bone/weapon绑定未换。

实际UE5.8.4/D3D11/2080Ti run30e6de5c441f4e55ba482b1c1f02d427/PID37704自然exit0，Tools/capture_aya_ge_series.py＋_headless.py，新producer启动前冻结。一个真正DynamicMeshComponent初次Append原3456点/1152面，之后72样本更新position/originalnormal/GEcolor，原UV/拓扑保持；使用已有单面translucent/unlit/rgb*2材质、NoTransformvertexcolor、固定每组首帧origin＋XZY*canonicalunits*100、identityactor/component；+Y正交512x768，manualexposure0。72张实际PNG＋2hidden controls、实际componentCPU读回actual_component_samples.bin，非GPUvertexreadback；未保存资产包。

root独立Tools/verify_aya_ge_series.py不导入exporter/recovery，直接读independentsoftwareoutputs与实际组件/PNG：72samples/248832点转后positionF64bits、colorF32bits、normalF32bits全同，maxpos0cm；抽取的indices/UV严格保留1152面顺序/重复面multiplicity与原F32UV。183既有包hash前后/exit后相同。idle实际58种pixel图，fire输入12种，逐张有前景。root实际view idle0/fire11，见原模型服装和姿态但手臂透体仍明显、此回放没有武器。不能称原机位像素/GPUidentity/深度或M1验收。此新动态网格保留1152面不改变旧native转换1151面的边界。

运行目录下PREVIEW.html提供按组播放/逐样本实际UE图，CAPTURE_REVIEW.md含实际图/复现/边界；全说明docs/AYA_GE_SAMPLE_SERIES_20261020.md。最后out/AYA_GE_SAMPLE_SERIES_20261020/source_protection.json于2026-10-20 14:57UTC完整核ISO448a90...a15bc、slot0存档32f7fe...dc39、INId75494...ca34不变，active_capture_processes=[]。

下一步优先解决原main-depth写入/透明混合与排序（手臂透身体）；精确CPU↔GE时钟及真正武器同步，生产native与正式UE战斗仍未完成。勿把新的独立GE groups接到旧60帧武器上，勿用Masked近似直接冒称原透明/深度等价。没有编译工具链变化时不重复UBT失败构建。

# 第三次生日高清重制持续工作检查点

持续目标：完成原版资源与行为恢复并接入独立 PC 高清重制；当前先完成可靠的 M1。用户授权持续解析、原版运行时采集与本地实现，不覆盖 ISO/存档，不再做“第四日”。

## 最新：GE 顶点光照核心、原软件实现独立对照、实际 UE 单姿态校准与 Nanite 修复

本轮实际progress，完整游戏/M1仍active。root独立完成，没有再调usage-limit worker，没有系统安装、桌面UI或重复SDK构建。新kernel落UE Source但未通过正式UBT/逐帧native调用，不能混称动态灯光接入完成。

**原始输入与CPU核心**：tools/recover_aya_ge_lit_inputs.py 从3个冻结PPDMP重放318targetPRIM，VTYPE/完整geometrySHA/registersnapshot核对后保留WORLD、逐drawBONE、原U16权重/32768、S8法线/128、S16位置/32768；out/AYA_GE_VERTEX_LIGHTING_20261020/inputs共10368vertices。新UE Source/T3BRemake/Public/T3BGELighting.h及Private/T3BGELighting.cpp实现原weighted skin/world/normalization和观察directional/point光、ambient/diffuse/specular整数舍入/secondary，拒绝COLOR0/through/spot等不支持路径。x64/SSE4精度策略明确。

**独立参考**：固定PPSSPPv1.20.4 Lighting.cpp/Math3D.cpp原体未改，test-onlyGPUState/框架headers适配retained raw，g++13.2 -msse4.1 -ffp-contract=off编译。comparison_v2/comparison.json记录全部源/适配器/driver/builder/compiler/exeSHA，318draw/10368vertices变换bit差0、颜色byte差0，完整outputbin相同。原始输入是观测，颜色是重建；不是原硬件/software renderer实际lit输出采样或GPU像素证明。13synthetic_edges_v2和8native_scope_tests通过，不算新增原始观测。doc docs/AYA_GE_VERTEX_LIGHTING_20261020.md。

**UE校准**：calibration_pair导出同一第一原姿态white/ge_lit静态glTF，只COLOR0 bytes不同，原WORLD姿态只平移居中/units换算不旋转；front/back文件名仅±Y轴。原单面透明材质、贴图、RGB*2和曝光相同。首次导入默认Nanite=True/fallback_relative_error1，实际RenderData→DynamicMesh1105tris，14palette外新颜色。直接读设置确认后，new namespace两副本仅官方StaticMeshEditorSubsystem.set_nanite_settings(False)重建，成功UE5.8.4/D3D11 run9516045f29bc4b40a2569ad97e0b6a79/PID67096自然exit0，4PNGs，181旧包hash相同只新增2mesh。实际彩色overlay3453convertedvertices/1151convertedtris，palette外值0，rawLODcount未声称。

独立NullRHI cornerprobe/PID77380自然exit0，文件该run/color_corner_probe/ue_corner_probe.json。root新Tools/verify_aya_ge_light_calibration.py严格F32position及F32/FP16 UV words+cyclic绕序匹配，再核colorbytes：SourceModel1152全匹配0差，RenderData1151全匹配0差，缺1仅duplicate class；rawindex删除阶段未知。Pillow独立4PNG/foreground/同A-B实际camera/asset hash通过，root_independent_verification.json；v2另核完整position/UV/color类multiplicity也通过，旧report保留。root实际看white/GE +Y图确实从泛白变为暗蓝绿（共同foregroundmeanRGB white136/135/138→GE28/40/42），不是originalpixel阈值或原版机位比较。CAPTURE_REVIEW.md保存全部范围。

**失败全部保留**：3cdc语法失败无包写入（之后wrapper增加py_compile）；eba2完成2mesh+图但white没有coloroverlay被错误当失败；beb81是GeometryScript_List脚本名；701d是不存在的get_triangle_count；836b acquisition完整但后发现Nanite简化不得称保真。后两个只读settingsprobe分别因StaticMeshEditorSubsystem未注册None失败、直接Nanite property成功；最终setter用独立实例的无状态API，实际raw readback核验。所有report/PNG/旧包未覆盖。旧带Naniteasset隔离保留，最终只用AyaLightingNoNanite/Run_9516045...下两个静态校准mesh。

本轮最后source_protection.json 2026-10-20 14:38UTC核ISO448a90...a15bc、slot0 32f7fe...dc39、INI d75494...ca34均原SHA，无PPSSPP或UnrealEditor-Cmd。仍需全动作灯光时间轴/动态shader、原mainDepth混合、fog/输出gamma、GE枪口语义和正式UE战斗；静态校准绝不可作为完整主角/高清版完成替代。

## 先前：六组原版 CPU GE 命令、矩阵独立回放与 Aya 原版剔除实际修复

本次goal turn为实际progress，完整M1/游戏goal仍active。没有系统安装、桌面UI或重复SDK失败构建。PPSSPP两次失败保留后第三次完整成功；UE A/B自然exit0，新的默认材质mesh候选独立进程重载通过。最终无PPSSPP/UnrealEditor-Cmd进程。三个worker部分完成后因usage limit终止，root已接手核对现有文件、完成报告/修复/重载；不要假定worker口头进度等于文件验收。

**真实武器关联CPU写入**：`out/AYA_BONE_GE_ACTIONS/slot0_weapon_ge_emit_fire6_command_alias_v3/marker_ge_emit.json` SHA c71bde19...917de，v3 producer46433780...a3bf74连接前已冻结到静态目录，174离线Mock。session42670自然exit0，102entry/96foreign/6target/6完整九阶段rows，failure/inFlight null、输入/自有BP/ownstop清理通过。6组各52B VIEW+16B首个PRIM；type152×4/mode1/source2b58/runtimeID15/VTYPE102/4vertices/stride10；type155×2/mode0/source2690或26a8/ID18或19/VTYPE11e/14或4vertices/stride16。root `tools/analyze_weapon_ge_emit.py`6rows/85codeblocks通过；真枪243vert identity、FEP192/registry/source geometry object、SP/RA/savedframe、type152emitstack10/14/18与155s4/s5实际对象链均核。16个validhash合成反例全拒绝，closure review已存。doc `docs/WEAPON_GE_EMIT_RUNTIME_20261020.md`。CPU writes不是GE execution，semanticName仍null，正式socket/timeline未替换。

前两capture保留：v1 `slot0_weapon_ge_emit_fire6_20261020` component08d5e27a是byte struct被4align gate拒；v2 `slot0_weapon_ge_emit_fire6_component_v2` 到真实matrix.return后因DLcursor48c5a9d0 uncachedalias拒绝。v3只对命令窗口允许普通/uncached两RAM段，保留CPU cursor和canonical readAddress；普通objects/matrix/vertices规则不放宽。不同冻结版本与raw没有覆盖。

**独立数学**：`tools/verify_weapon_ge_matrix_math.py`实际v3六matrix+六VIEW共192float32全部0bit差，六次matrix返回32GPR也完全一致；报告actual_v3，root重新运行root_replay_v3一致，13offline checks不是runtime。四mode1 f12=32，同次6589c/104原码双恢复；两mode0 f12=138.823532/35.730488，657f8/a4仅固定module静态码、缺同次runtime完整helperidentity。全部入口S/T/D prefix未由API导出，因此不是无条件全mode数学证明。VIEW用实际handlerMatrix而非预测matrix，不把mode0身份缺口隐藏。doc已更新mode0与边界。

**原版cull与真实UE修复**：`out/AYA_CULL_ORIENTATION_20261020/FINDINGS.md`/culling_states.json独立318原Aya PRIM全CULLFACEENABLE1/CULL0，1152face sourceRH与nativeXZY/LH normal同向。旧C强关cull→stager cull0→UEtwo_sided=true；gltf也硬True，是fallback而非原版。UE5.8.4 A/B run8198e8faa071458c834fa911389cc582/PID10808自然exit0，FullUV identityactor/同进程原材质vs仅改TwoSidedFalse，8图4hiddencontrols；root实际看图确认后片/后袋/靴后跟恢复，仍有手臂透背/亮肤色。176旧包hash保留、新增1材质。root新 Tools/verify_aya_cull_comparison.py 用Pillow独立核8图/相机component readback/同帧45骨/包hash通过。CAPTURE_REVIEW.md已由root补齐，不能叫完整GE深度/光照保真。

**持久化默认绑定**：新mesh `/Game/T3B/NativeCandidates/AyaSourceCull/Run_831698320b0d40c8becacb7e91609889/aya_source_cull` 引用原compact Skeleton和新单面材质，FullUV不变。root新Tools/prepare_aya_source_cull.py及_headless.py完成实际保存+独立UE5.8.4 reload run84e06f072fb04a658d6cc945ea8704c2/PID38556自然exit0，verified.json通过45bonehierarchy/15LOD属性/3449LODverts/defaultmaterial，179现有包hash全同。三失败run5c60(APIinstance)、6868(materialarray未copy)、831(设置str含内存地址误比)保留；最终831实际binding正确，root用显式existing-candidate只读恢复验证，没有将失败buildreport改绿或再写旧包。旧failed6868新包也保留隔离，不用于下一阶段。正式PMC/C++战斗未替换。

`export_aya_native_gltf.py`现在从原GE cull_enabled生成doubleSided，验证器分别记录新policy与历史fallback。新out/AYA_NATIVE_SOURCE_CULL_20261020 gltf139a8660...0cf22，bin同旧8ce1805d...d8454，root独立只材质delta/全PNG byte同/全部60帧数值验证通过。新gltf本身未再UEimport；上述持久化mesh复制旧已验证FullUV，二者来源不得混称。旧冻结export不变。

版本纠正以实际report为准：FullUV build f34679实5.8.3，RHI3a5b及offscreen01e实5.8.4，不能把“旧运行”全部称5.8.3。最终 `out/WEAPON_GE_EMIT_RUNTIME_20261020/source_protection_after_emit_cull.json` 2026-10-20 14:08UTC核ISO448a90...a15bc、slot0 32f7fe...dc39、INI d75494...ca34均未变，无capture进程。后续：原blend+mainDepth写入适配与光照；新姿态补657f8runtime原码/CPU→GE实际draw纹理和画面关联；生产native与正式UE玩法仍需完成。不将上述候选或CPU命令叫枪口FX最终确认。

## 先前：UE 安装复查、FullUV 实际读回、离屏画面缺陷与原版光照输入

当前用户回复的是此前“UE 尚未安装”的询问。2026-10-20 13:40 UTC fresh read 确认 `C:\Program Files\Epic Games\UE_5.8` 已有 UE 5.8.4 CL58902052，Build.version、UnrealEditor.exe file version 和 Launcher .item 一致、incomplete=false；`work/t3b_unreal/Validation/environment_engine_reply_20261020.json` 为新报告。不能继续告诉用户当前没有引擎，也不能将此前实际 UE 5.8.3 运行改称 5.8.4。MSVC/Windows SDK 仍未发现完整组合，vswhere 缺失所以编译器发现不完整。本轮无系统安装、无重复正式构建、无桌面自动化。

FullUV 新候选 `/Game/T3B/NativeCandidates/AyaFullUV/Run_f34679f35e3744e58f694342fba517d5/aya_native_full_uv` 已由 UE 实际重建；新 RHI run3a5b71bdf90d4ba9af564917577ff0a7 读回 frames0/30/59。原 F32 UV 最大残差为0，旧 FP16 误差0.000213623046875已消除；三帧10347位置与旧550c run逐 byte 相同，SHA07ca0934...55ee1。root新 Tools/verify_aya_full_uv_reference.py 直接解码冻结原 glTF/bin 做 oriented UV multiset 检查通过，`root_independent_full_uv_verification.json` 已落新run。仍是3449实际LOD vertices/1151转换tris；raw index-buffer面数未知，重复面少一次及16面身份歧义未消除，未称GPU/全量身份验收。

原生 Aya 真实 D3D11 离屏 run01e0bdc53e704bf1b8f63944bf63f62e/PID75272自然exit0，frame0/30、正反共4张PNG加2hidden controls。176旧包hash未变，未修改材质。root与worker实际看图都发现反面仍近似正面水平镜像，镜像RGB MAE约0.55/0.53；同帧45骨姿态相同、相机输入yaw±90，但未读取setter后的component/GPU projection，边界保留。当前TwoSided Translucent缺对应main depth-write是有本机源码支持的原因候选，非逐draw GPU证明；皮肤/头发偏亮，画面验收失败。专属 CAPTURE_REVIEW.md 与 image_readback_verification.json 保存全部边界，不能把foreground成功当保真成功。

root新 tools/inventory_aya_ge_lighting.py 重放3份原PPDMP的318次Aya draw，VTYPE/完整几何SHA/全部lighting寄存器与材质快照一致；2组状态均启用directional light0及point light1/2、light3关闭、Gouraud、无COLOR0。结果 `out/AYA_GE_LIGHTING_20261020/lighting_states.json`，说明 docs/AYA_GE_LIGHTING_STATE_20261020.md。只恢复所采光照输入，未实现原版shader、未覆盖60帧或所有关卡。UE当前unlit/rgb*2基线不能据纹理RGBA一致宣布最终肤色正确。

新的九阶段 weapon CPU GE emit producer/Mock 与 ABI 文档已交接：tools/trace_weapon_marker_ge_emit.js SHA ce1e08cf4e34a08906384518519835ff0d3a6ad3ba3358a9ee0d56106f75d2cb，150离线Mock通过，冻结副本与offline_verification.json位于out/WEAPON_GE_EMIT_STATIC_20261020。ABI为docs/WEAPON_MARKER_GE_CPU_EMIT_ABI_20261020.md。三worker均已交接。本轮尚无实际 PPSSPP 采集、尚无 root独立九阶段raw审计；不能把Mock当真实VIEW/PRIM写入。下一步沿已确认152/155 handler追 matrix→VIEW→geometry→emit，并区分CPU命令写入、GE执行与枪口视觉语义。旧alternate六组handler执行/返回证据仍有效。正式M1/完整高清重制未完成。

## 先前：精确武器 alternate renderer 六组真实回调；compact Aya 实际无损消除副本；离屏 RHI 数据边界已查明

上一goal turn有实际进展，本轮也完成新运行证据及可用资产。完整高清重制goal仍active，M1/完整游戏未完成。桌面自动化继续停止；只有隐藏PPSSPP/API与隐藏UE commandlet，没有系统软件安装。所有本轮exec session均terminal（queue79215、alt48424；UE失败20673、成功45132），三worker均完成交接，没有等待中的任务/采集。

**实际queue路径确认**：`slot0_weapon_queue_routes_fire6/queue_routes.json`，新producer SHA98f92c1c...8243241已在连接前冻结到`out/WEAPON_QUEUE_ROUTES_RUNTIME_20261020/trace_weapon_queue_routes_sampled.js`，42Mock通过。七phase顺序为enqueue6/range_draw0/range_alt6/callback0/callback_alt6/controller_dispatch6/enqueue_control6；两0阶段各有677776978 guest ticks推进，所有初末cpu.status完整ACK均running。30暂停点原global4→controller30均确认[08c3a680]=09c87e30，byte2e=0/2f=1。range_alt交替原args(2,9,256)和(4,266,8)，各3次，前者含200/203；controller_dispatch actual modes0/1/2/3/-2，RA593c8。callback_alt6最早buckets315/315/9/64/93/104，不是exactweapon选择，不把这些入口叫已验证武器。root tools/analyze_weapon_queue_routes.py独立30组audit passed，doc WEAPON_QUEUE_ROUTES_RUNTIME_20261020.md。

原module静态27完整函数/10真实callsite参数/3原表复核见`out/WEAPON_QUEUE_DISPATCH_STATIC_20261020/REPORT.md`与queue_dispatch.json；08b5ac60上层callbackMode3→下层rangeMode2、9..264，controller2e0走db20→d828→69b58。下层a0==3另转08bbd9e8，只处理特殊bucket265且走d7f0/A路径，不能误称cleanup或忽略这个例外。mode0..2单桶为314/315/316（原base表），不是9/10/11。旧空capture没有controller/ticks，不能追填旧现场；没有证据归因JIT故障。

**精确武器实际handler执行/返回**：`slot0_weapon_render_alt_fire6/marker_render_dispatch.json`，alt producer SHA99506c73...efc98a0，冻结`trace_weapon_marker_render_alt_sampled.js`，81独立Mock。ENTRY69b58/258→beforeJALR69d64→RETURN69d6c，entrycallerRA8bbd858，wrapperd828/3c。实际113entry、107foreignFEP prefix排除、6selected/6dispatch/6return/6rows，failure/inFlight null、finally输入/BP/ownstop清理成功。精确原枪243vert/VTYPE522与FEP192原record身份、D/list/definition严格relocation、实际registry/method20/target/thisAdjust/filter、原SP/savedframe/GPR、param来源全部root独立核对（20code blocks双恢复）。D10ba0×2/10be8×2实际type152→08b9809c，ticks2013/1777；D10c30×1/10c78×1实际type155→08b9a514，ticks1946/3230。六组state097d2540，对应N2340/21b0/1f60/1d10。parameter/mutable前后均未变，152为32/7bytes，155为76/32bytes；不可盲读a3为64byte矩阵。beforeJALR a2是vtable+20方法descriptor，实际param在t0，delay才copy到a2。N4c时间调整的FPR/VFPU未读，不能重建精确f12。

`out/WEAPON_QUEUE_ROUTES_RUNTIME_20261020/render_alt_fire6_independent_audit.json` passed6，actual_callback_invocation_return_verified=true；geDrawObserved=false、semanticName=null。doc WEAPON_RENDER_ALT_RUNTIME_20261020.md。正式M1枪口/timeline未替换。下一步沿已确认handler内部实际helper→VIEW/GE命令写入/提交，不再重复试旧入口；可关注152的62674/6270c、155的60374/6050c条件调用，但静态可达还不是已执行。仅handler返回不能证明GE draw/最终FX语义。

**独立审查修复**：runtime_action_clips只读review发现3项auditor缺口并复核全部关闭，报告`independent_auditor_review.md`。queue phase status/register raw按ticket绑定完整rpcLog ACK，resume核ticket/通知/wall；a0==3静态scope为special265不误含200/203。render阳性要求严格(ENTRY,DISPATCH,RETURN)×rows add/ACK/remove生命周期、target/entry counters、无externalpause。真实queue30/alt6回归通过；root新verify_weapon_queue_route_audit.py拒绝13坏证据并正确分类一个明确synthetic的mode3；verify_weapon_render_alt_audit.py拒绝13；旧empty9继续通过。不把synthetic记录当运行采集。

**compact Aya已实际导入并无损保留观察动作**：`out/AYA_NATIVE_COMPACT_20261020/README.md`、export_aya_native_compact.py/verify_aya_native_compact.py。新gltf SHA1da0939d...5f43a3、bin88976143...a43ec，994独立检查保全部原attributes/skin/动画/材质。真实UE import fbcb0ef145134ee58227c6c44f4835cb，新的`/Game/T3B/NativeCandidates/AyaCompact/Run_fbcb.../aya_native`三包；真实第二进程60帧raw probe d3bc5af548504f8d9145f593c5e9c2fa，SourceModel总点366336→3456、未引用362880→0、1152tris保留。新旧local/aligned各207360点、622080components逐byte相同（旧raw48c...参考），全部45骨实际world姿态/60times/UV/材质/反射与采样normal一致；误差无劣化，vsC最大仍0.0213324847cm。actual_compact_paired_verification.json与compact_frozen_C_gltf_comparison_v2.json为正式报告。原包/冻结产物/正式runtime未改；只清除了UE importer共享accessor引起的106倍SourceModel副本，没有做性能或GPU保真承诺。

**实际离屏RHI RenderData CPU采集，不能误称rawbuffer/GPU验收**：root新Tools/probe_aya_render_data.py和_headless.ps1，-AllowCommandletRendering -RenderOffScreen -d3d11，NVIDIA2080Ti实际RHI日志。首run6b84...因转换tris!=1152的假设失败保留；后run550c3d234d124e0382d260212efc1d35/PID67308/exit0，明确data acquisition only、topology_fidelity_verified=false。实际GeometryScript RenderData→GetCPUSkinnedVertices→DynamicMesh，frames0/30/59、default CVar0，输出3449点/1151面；不是rawLOD index/vertex count、不是GPU skinned vertex readback。成功producer事后copy与report SHA核对保留（未称prelaunch frozen）。旧161+原native3包hash不变。

独立tools/compare_aya_render_data.py与run550c.../independent_render_source_analysis_v2.json/.md：1134面oriented cyclic FP16UV唯一匹配+1面full5attribute等价duplicate，另16面identity明确INFERRED，global fidelity false。UV实际FP16量化，max原F32差0.000213623。少1 multiplicity为非退化同向重复858/1125（draw62/102），转换TToDynamicMesh会skip duplicate/处理nonmanifold，因此不知rawbuffer删除阶段。净7点差=少面3corners+4shared reuse，不是已证焊7点。严格1135面3帧corner对SourceModel最大0.0765085241cm，对C0.0388818807cm，均非zero未归因单一原因；不能称全部逐点、GPU像素/重复混合draw等价。完整边界run550c.../README.md。

最终`out/WEAPON_QUEUE_ROUTES_RUNTIME_20261020/source_protection_after_routes_render_alt.json`，2026-10-20 13:17UTC：ISO448a90...a15bc、slot0即时档32f7fe...dc39、INI d75494...ca34均保持原SHA，无PPSSPP或UnrealEditor-Cmd进程。UE5.8.3可执行但正式C++仍缺SDK，勿因不变缺口重复失败构建/安装/恢复桌面。后续仍需GE实际包/武器视觉语义、生产native采样/精确UV/draw保留、GPU同机位材质和正式UE战斗玩法；完整game goal active。

## 最新：真实 UE CPU 蒙皮、完整 config 唯一匹配和实际 enqueue；renderer 零命中单独保留

本轮有实际进展，完整游戏 goal 仍 active、M1 未完成。桌面自动化继续停止，只执行隐藏 UE commandlet 与 PPSSPP debugger/API；未安装系统组件。三个独立 worker 均已交接并结束，无其后台任务需要等待。

**UE 原生 SourceModel CPU 蒙皮取得真实 60 帧×3456 referenced vertices=207360 点。** 默认 run `c64431c073744987b3bcb7965caa3a92` 和受控 raw run `48c1c01b67ae420290c829a9da5317b3` 实际调用 GeometryScript→FSkeletalMeshOperations::GetPosedMesh，组件 SetPosition 到达全部源时间。临时 actor yaw90+scale(1,-1,1) 实现 native→PMC 的完整 X/Y reflection，world-copy 对独立交换矩阵最大分量差2.13e-14cm。默认对冻结 C 最大0.08123738cm/RMS0.01372427cm；raw 最大0.02133248cm/RMS0.01037980cm，root 独立重算全部点和序号吻合，见 raw run/independent_frozen_C_recheck.json。不是 Python 造 UE 点。真实首末姿态变化，非静态重复帧。

raw 实验实际 CVar readback 0→1→1，原包/输入/时间/参考未改；本机 AnimSequence.cpp 的 a.ForceEvalRawData 在 WITH_EDITOR 内，CanEvaluateRawAnimationData 在非editor返回false，因此仅为编辑器数值参考，不能直接用作 cooked 游戏生产方案。默认run未自身读回CVar，另只读settings run观测默认0/ACL配置，保留此限制。统一采样网格最大key偏差71.558us；剩余误差未全部归因ACL。NullRHI RenderData无MeshObject，render-buffer/GPU未验收。只测前12三角绕序/normal，不能称全部切线/剔除正确。SourceModel实际366336个顶点，其中3456被1152三角引用，362880为未引用属性副本；需后续compact导入。没有替换正式PMC或完成UE战斗。所有工具、完整报告和复现命令见两run/README.md及work/t3b_unreal/README.md。

**完整武器 config：34个片段候选缩到唯一原record18。** `slot0_weapon_config_full_fire6` 实际4组，opt-in `MARKER_CONFIG_PROBE=1` producer SHA ff8eaa7f...7723bc已冻结。每组保留config完整228bytes、manager global/fields与108个pointer table words。实际config09c9a368=continuousbase09c99360+18*e4；pointer table无该config别名，未读取其payload。完整record SHA2e4bce...83e7b，在原ISO section0757111c、108条e4记录中唯一逐byte匹配index18，全部4组一致。没有live section header，未证明实际getter分支执行。root独立audit通过；7坏证据拒绝，另一个合法raw变异正确只得无匹配。新tools/analyze_weapon_config_source.py，doc WEAPON_CONFIG_FULL_RUNTIME_20261020.md、out/WEAPON_CONFIG_SOURCE_MATCH_20261020/full_record_runtime_audit.json。

**实际入渲染队列：** strict producer85d65e...9b0e、86Mock，`slot0_weapon_enqueue_fire6` 91entry/6完整pair/85foreign排除。原枪完整geometry和FEP192身份、callerstack、entry/return ABI、320bucket heads/tails及实际链全通过root audit。node+40实际D=10ba0(2)/10be8(2)/10c30(1)/10c78(1)，当前post type14，返回bucket200/203；只说明入队，render list152/155还不是实际handler。9坏证据拒绝。tools/analyze_weapon_enqueue.py，doc WEAPON_ENQUEUE_RUNTIME_20261020.md，out/WEAPON_MARKER_STATE_CONSUMER_20261020/enqueue_fire6_independent_audit.json。

**renderer 采集正常结束但零命中：** `slot0_weapon_render_fire6` producer0f841ac9...a5、81Mock。入口08b692f4/24c、wrapper69540/24原码双恢复通过、断点add ACK和输入/清理通过，但entry/dispatch/return/target全0，无guest tick，guest progress不能验证。不可宣称callback或GE执行。新root auditor默认拒绝空结果；显式--allow-empty仅给bounded_no_render_stops、actual_callback_invocation_return_verified=false，报告render_fire6_bounded_negative_audit.json，9坏证据拒绝。正向auditor分支尚无真实成功capture覆盖。原module另有08bbdb20→08bbd828→08b69b58、JALR69d64/return69d6c静态路径，下一步先从实际队列分发确认路径和guest progress，不盲目重跑相同断点。doc WEAPON_RENDER_DISPATCH_RUNTIME_20261020.md。semanticName仍null、geDrawObserved=false，未替换正式枪口。

最终 source_protection_after_config_enqueue_render.json（2026-10-20 12:52UTC）确认ISO448a90...a15bc、slot0即时档32f7fe...dc39、INI d75494...ca34均保持原SHA，PPSSPP进程为空。所有本轮采集session均已terminal，没有运行中的采集。UE5.8.3安装已完成、资产可用，但正式C++工程仍缺Windows SDK，勿重复不变的失败构建或恢复桌面安装。

下一步：实际queue dispatcher确定renderer入口后才做callback/GE包观测；native压缩生产采样保真与glTF compact独立验证；SDK就绪后正式UE编译/replay/玩法；GPU材质和原版同机位对照仍需完成。不能把SourceModel数值成功当作高清贴图/完整游戏验收。

## 最新：武器 selector 原字段和完整 pointer chain 实测；UE 第二进程重载通过

上一goal turn为实际进展（161 UE包真实生成）；本轮同样有新证据。完整高清重制goal active，未完成M1，不因Windows SDK缺口暂停其它解析。桌面自动化继续停止，只有隐藏PPSSPP debugger/API和UE commandlet。

新slot0_weapon_selector_binding_fire6实际4组ENTRY→POST_WRITE，均old0→new1、只改byte14c、70guest ticks，1层group递归；失败null，输入/自有BP清理成功。raw stack恢复实际caller08976f1c→08971edc(08971fe0)→26c6c/wrappers→6513c。新producer SHA8383019e...a1f1bf8已冻结到out/WEAPON_MARKER_SELECTOR_20261020/trace_weapon_marker_selector_writer_binding_sampled.js；旧295300...旧producer另保留，不能用新版hash追填旧capture。

独立analyze_weapon_selector_writer.py核对全部原码双恢复/JAL/stack/raw窗口：config+90=1→upper stack378=1→game s2/writer a2=1，actor80数组第0个24byte record→upper37c→state primary09bd23c0。raw handle4→drawable字段40→metadata64/draw16→完整243vert/VTYPE522 geometry链已保存。9个binding窗口全部独立查地址/hash；config94与upper374=00280216请求ID，slot缓存stateKey实际55/87/b9/ee，是不同层级，勿混称资源ID。binding_fire_independent_audit.json passed，4rows，primary_to_actor_raw_dereference_retained=true；旧fire_probe audit仍false。原40Mock+新增45Mock通过，11个新raw/valid-hash破坏证据拒绝。doc WEAPON_MARKER_BINDING_RUNTIME_20261020.md与SELECTOR_SOURCE_20261020.md。consumer语义仍null、没有替换M1几何枪口；Aya agent继续追P60真实渲染queue/GE consumer。

新FEP6的默认shared code auditor回归和独立逐opcodeVFPU replay也实际通过6rows/flags0/0bit差异，报告WEAPON_MARKER_STATE_20261020/fep6_shared_code_regression_audit.json与fep6_v2_independent_vfpu.json。加此前54组共60组实测flags0，但20/40/60分支仍无运行覆盖。

UE独立第二进程真实reload通过run c1994df2f25e40d89f80b978a8f731cc，Validation/asset_reload_runs/该run/verified.json。76Texture2D尺寸/alpha/sampler/tag、84Material签名与1106graphnodes/1204edges/UV/alpha/masks、依赖与空World均核对；161包前后SHA相同，实际UE日志0errors0warnings。Tools/verify_saved_source_assets.py和verify_source_assets_headless.ps1是只读新入口；两个失败run保留。不是GPU/shader/replay/gameplay验收。

Aya native实际导入和第二进程只读重载已通过：UE run64e9826c75854a7ba8f7f36eabefb4cf，reload14d20d34c3eb4a70bd74dd99b0fa34a1。/Game/T3B/NativeCandidates/Aya/Run_64e...下aya_native、aya_native_Skeleton、aya_native_Anim三包。45bones=44source+synthetic，全部44parent匹配、source_i→UE_i+1；60keys/59intervals、45tracks、长1.968633294s对源1.968625903s，+7.39097595us。唯一LOD0section/slot0确认后绑定已验M_Aya_000；旧161+新3包重载SHA不变。真实get_ref_pose_transform读取全部45refpose，对转换glTF最大local平移分量差0.000513125292cm、scale1.50649e-7、q2.43076e-8。默认native向量(x,z,y)、PMC(z,x,y)，相对X/Y reflection而非yaw；未做轴修复、未替换PMC、未验UE skinning vertex/GPU/玩法。首d33...官方glTF材质MF_Unlit_Body AlphaMode报错exit1保留，成功路径禁自动材质后绑定已验原材质。完整路径/命令/轴源码/边界见work/t3b_unreal/Validation/native_import_runs/64e9826c75854a7ba8f7f36eabefb4cf/README.md及Tools/import_aya_native_headless.ps1、verify_aya_native_saved_headless.ps1、compare_aya_native_refpose.py。

root另从真实UE已保存Texture2D source art用TextureExporterPNG导出76图，再用外部Pillow独立解码对原staging比较3637248 RGBA bytes全部逐byte同（含透明像素RGB和alpha）。run70d48c64a961495bb7017679bb9c3a31/verified.json；Tools/export_saved_texture_sources.py与verify_texture_source_roundtrip.py。只证source art保留，不是GPU平台纹理/采样/shader/像素验收。

config8c raw16bytes全ISO exact search为34matches，均type34 pack07571000、section0起0757111c/24632bytes/SHA7411909bb4e848af75628d4c305bccc1d25361cdf91e79831984900f12e866f3；不唯一，不确认完整record/livebase。源section header6c00e40008000000符合8+108*228的候选算术。legacy raw/packs/pack_sections.csv为pkg内相对偏移，ISO9660实际3rd.pkg LBA59600；1663rows/435pack实际目录核对后换算，勿复用outCSV绝对假设。tools/match_weapon_config_fragment_iso.py、docs/WEAPON_CONFIG_SOURCE_MATCH_20261020.md、out/WEAPON_CONFIG_SOURCE_MATCH_20261020已保存34候选和原section。

下游consumer静态ABI已交回：tools/analyze_weapon_marker_state_consumer.py、test_...、docs/WEAPON_MARKER_STATE_CONSUMER_20261020.md；39完整函数/15anchors/6saved rows/4FEP D候选，9离线tests。P60→render queue→type152/155为静态条件路径，尚未runtime读node40确认；8bbb8d4经kind1写GE VIEW3c/3d，绝非WORLD。最小下一capture：enqueue entry8bbdce8(a0=E,a1=C,a2/a3 options)，RA935f0，C8c=P/C90=N，N3c=E，stackQ0:d0 savedRA Q74=68ff0/Qa0=69080/Qb8=69a40/Qc8=6a9e8；单BP切return935f0要求SP=Q、E8=1/Ec=C/E10=P/E14=N。随后才按已确认identity采render dispatcher692f4/694f4的实际t2目标，不能按时间邻近关联无关GE draw。semanticName仍null。

下一步优先：native与PMC坐标/真实UE蒙皮点及渲染比较；最小queue probe确认实际consumer；补完整config e4 record/manager字段消歧34候选。Windows工具链复查environment_after_asset_reload.json仍SDK/MSVC未发现，真实C++构建尚未越过SDK gate；不重试相同失败、不安装系统软件、不恢复桌面UI。

ISO/slot0/INI在本轮实际采集后重新hash均不变，WEAPON_MARKER_SELECTOR_20261020/source_protection_after_binding.json保存证据，无自有PPSSPP残留。

## 最新：UE 首次真实资产导入通过、C++ SDK 诊断与 FEP live binding

UE 5.8.3（CL58210709）本机必要文件完整、现代Epic .item bIsIncompleteInstall=false。首次真实 Build.bat/UBT 已执行但 SDK validation 失败，缺少 Windows SDK（要求10.0.19041.0）；未进入C++编译。日志与summary在work/t3b_unreal/Validation/first_unreal_build*。无系统软件安装、无桌面自动化恢复。旧LauncherInstalled.dat空不再作为未安装依据。

独立content-only T3BAssetImport.uproject共享正式Content，无Modules；实际隐藏UnrealEditor-Cmd -unattended -NullRHI导入成功，run0fac54502ca140d4accffa2e5a7bc618，76原版纹理+84基线材质+1空地图=161包。wrapper核对本次run_id/PID/脚本/manifest和全部文件大小/SHA，verified.json在Validation/asset_import_runs/该run。两个失败run保留，按本机UE源码修复Coordinates→UVs和VertexColor unnamed RGB输出。不代表UE角色replay、shader/pixel或战斗通过；11材质状态仍不等价，高清资产尚未制作。

FEP opt-in已真实重采slot0_weapon_marker_state_fep6_v2：6组三阶段返回、来自state190的base08d4d280与五窗口1308bytes独立复核。header+8、header tables、descriptor/list/table1相关指针实测relocation，record+48f0完整192bytes同ISO。header+0c另有0→01ff0000未知修改。首次fep6因错误header+8 gate失败0rows并保留；不能冒充成功。报告out/WEAPON_MARKER_STATE_20261020/fep6_v2_source_verification.json，新doc WEAPON_MARKER_LIVE_FEP_20261020.md。完整778816byte runtime section未采；source名称/FX语义仍未知。selected FEP离线图93+93表项、133unique record候选，2587nodes2770edges、17坏数据拒绝，见SELECTED_FEP_GRAPH_20261020。

Aya native glTF候选已生成，44source bones+synthetic root、106primitives/3456verts、60真实时间点、132TRS channels，源raw/weights/provenance保留。root独立解码glTF与冻结C probe比较207360点，最大0.000173949054PC（0.0173949cm）；报告out/AYA_NATIVE_GLTF_20261020/independent_frozen_C_comparison.json。中间帧TRS/SLERP与C affine插值最大差0.0311726PC，仅是两种重放插值比较，未实测原PSP subframes。未用该候选替换正式PMC runtime、未通过UE native importer。

selector writer已实际fire_probe：4次observed writes old0→new1、只变state+14c；递归深度1、原游戏caller08971edc/callsite08971fe0。raw在slot0_weapon_selector_fire_probe。采样器Mock40通过、完整原码sidecars保留，但root独立写入/栈链审计尚待完成；不能直接叫已确认枪口。后续先独立重核caller chain/实际source1参数，再扩动作与consumer。

下一步：补齐Windows SDK/MSVC后实际编译正式UE工程并执行source replay probes；与此同时可继续原版consumer和更多动作解析。不得因安装/包保存成功宣布完成M1。完整高清重制goal仍active。

## 最新：真正最终state矩阵、FEP来源候选与Aya native SRT数学可行性

上一goal turn为实际进展。本轮继续取得新的原版运行时证据：slot0_weapon_marker_state_{square6,aimfire24,strafefire24}三capture，54组helper→generic→state完整返回，flags均0、stateRA08b63550、outerRA08b69f00。helper64bytes、generic C64bytes与最终P+60全逐byte相同；独立analyze_weapon_marker_state_output.py核对完整六函数原码双恢复、stack H+3ac/SP/RA、exact243vert枪、四阶段state/resource等。独立verify_weapon_state_vfpu.py又直接逐opcode/F32/branch-delay回放全部54组，0bit差异，未调用预测公式；只证明实测flags0分支，20/40/60仅静态依据。raw捕获目录、audits与完整trace见out/WEAPON_MARKER_STATE_20261020/，docs/WEAPON_MARKER_FINAL_STATE_20261020.md。采样producer f93d4d...已冻结该out目录，后续cleanup patch不能冒充旧producer。

低flags公式已解：basis=(flag20?A:M).R*L.R，translation=(flag40?A:M).R*position+M.t+P50.xyz。注意flag20/40都clear时position直接P10，其它取L.t；不是普遍假定P10=L.t。w强制1；high-basis(flag200000)/外部Y修正(flag10)未由此通式替代。M=generic marker，A=C40，L=local state-before。

54组四阶段state198实际均08d51b70，64bytes SHA04afeecb38df20d41a7c24da1686e31cf70a8e631aa51e48321c776ab21d89b6。全ISO exact search唯一命中0x56bfc4b0；CSV pack_offset明确为ISO absolute（不能再加PKG_BASE）：type12 pack56bf7000，section1 FEP07起56bf7bc0/778816bytes，记录offset48f0。section已提取out/WEAPON_MARKER_STATE_20261020/original_source_match_section.bin，完整SHA97443c71...06ec802，match_weapon_state_data_iso.py可复现并核目录。runtime base08d4d280仍需liveheader确认，不能仅唯一64bytes命中称资产身份已恢复。

三字段额外交叉：entryState190=08d4d280、194=08d4e234=base+fb4、198=base+48f0；原FEP table0[4]→descriptorab8→list48e0→record48f0，descriptor.low16index4与table1[4]=fb4吻合。初始化8b63f34/38/3c写190/194/198。Aya_materials正加显式opt-in MARKER_FEP_PROBE=1到新state sampler，仅首选中entry保存来自真实state190的base下0/400、ab8/12、48e0/16、fb4/64、48f0/c0有界windows；header严格gate容许relative或实际base-relocated pointers，失败保留raw并停止。尚未live执行新FEP probe；待该agent交接Mock/schema后，安全runner加载slot0备份跑6rows，再由root独立比较FEPheader与pointer链relocation。不要恢复桌面自动化；无UI输入授权。

另一个真实突破：out/AYA_LOCAL_SRT_FEASIBILITY_20261020.json/.md 与tools/analyze_aya_local_srt.py，60*44=2640 raw local samples、parent pointers全核对。原q0/q20非单位化，G40=||q20||²R(normalizedq20)，不能normalize丢scale；actualLocal最大SRT残差1.03142e-7、col-dot2.20875e-7，无实际shear/反射阻碍。保norm² scale层级G最大误差2.56862e-5 sourceunits；normalize-only误差.02165036。B80逐帧bit恒定，GE C0是量化后的skinning payload而非local。保scale SRT相比GE weighted verts最大4.94379e-5 PCunits；native数学可行但两个roots、非单位总weights与F24差异仍要处理，未改UE导入/runtime/资产、未实际UE compile。README已更新这一边界，当前affine PMC仍保真参考。

原ISO SHA448a90...a15bc、slot0 SHA32f7fe...dc39、INI SHAd75494...ca34采集前后全部相同，source_protection.json保存完整hash；无自有PPSSPP残留。新state采样器cleanup收尾已有50 Mock，queued own/external暂停边界与producer加载时自hash已加；更晚FEP opt-in补丁尚待交接。正式枪口/timeline没因候选语义被替换。完整高清重制goal继续active，UE仍未真实编译/运行。

## 最新：原版武器helper实际返回值与同暂停点几何校准

本轮实际进展，覆盖下方“尚缺helper output”的历史状态：四次PPSSPP hidden/API captures从slot0备份取得78组原版source1 helper entry/return pair（square6_v2、aimfire24、strafefire24、strafefire_dense24）。完整module identity两官方恢复路径、exact243vert枪geometry、SP/RA/s0/s1/s2、原a0 output64bytes与postWORLD/source40均独立复核。WORLD×source40相符的F64参考误差约1.56e-4..2.38e-4原单位，反序大差；不是逐bit相同。每helper667guest ticks。新增脚本tools/analyze_weapon_marker_output.py，报告out/WEAPON_MARKER_OUTPUT_20261020/*_audit.json，详情docs/WEAPON_MARKER_OUTPUT_RUNTIME_20261020.md。

第四capture同暂停点读取全3×0x130 source。tools/measure_weapon_marker_geometry.py从真实m1_main.c SOURCE_WEAPON_TIP与clip units，使用source0+C0的12个GE BONE words（0x2B opcode/float24/col-major3x4）与WORLD解析计算，24样本相对原版source1实际输出最大位置差0.3437013cm、方向差0.000002259deg。root40 identity且C0 decoded payload逐字等source80对应F32高24位；runtime+124为parent pointer [0,sourceBase,sourceBase]。错误的初次C0-as-F32诊断已保留为passed=false *_invalid_f32_interpretation.json，不计入结论。这是原world空间公式校准，不是实际M1插值、Aya-relative baked矩阵/GPU/可玩验收；未替换正式几何枪口或timeline。semanticName仍null，具体FX/弹道consumer未确认。

采集器GPR category实测35项（最初严格32导致0rows停止，失败保留）；现仅验证并取前32GPR，17个Mock反例/正常用例通过，全3source切片也已验证。4个auditor坏证据拒绝检查通过。四成功capture finally全清理，当前无自有PPSSPP，slot0与INI hash恢复核对通过。用户Esc停止桌面自动化的约束仍生效；本轮只有hidden runner+debugger API，没有桌面输入。

下一步可直接做真正下游state输出观测：docs/WEAPON_MARKER_STATE_CONSUMER_ABI_20261020.md已按原MIPS+现有stack核对。H=helper entry SP，D=H+1b0，generic return08b630dc时SP=C=H+210，其64bytes为helper的原样复制；最终P+60经flags组合，不可直接等同helper。需entry保存H+338完整flags、H+360 state函数savedRA（08b63550/08b6379c，returnSP=H+370）、H+3a8更上层RA（08b639c8/08b69aec/08b69f00）。现stack仅0x240不覆盖这几个offset，不能追填；新probe须扩到至少0x3ac并继续单activeBP逐级切换、每级SP/RA校验、原码双恢复identity。state+198资源指针只是入口，仍不能直接命名FX。

UE后台最新状态：必要Build.version/Build.bat/Editor文件仍缺，LauncherInstalled.dat空，最近检查连EpicGamesLauncher进程也未见；不能把此前“安装10%/PID63280”当作仍在下载的证据。不要自行重启安装或恢复UI。Tools/check_environment.ps1已实际运行，Validation/environment_inventory.json显示MSVC/SDK未发现且vswhere缺失（搜索不完整），UE从未编译。README含官方UE5.8要求与检查命令。完整高清重制goal保持active。

## UE5 工程初版（覆盖下方“尚未创建工程”的历史状态）

- `work/t3b_unreal/T3BRemake.uproject` 已建立UE5.8 C++ Runtime/Editor工程，T3BReplayWorld用ProceduralMesh完整affine replay，T3BReplayGameMode用Spectator观察。不是UE战斗移植完成，native Skeletal Mesh、碰撞/射击/Overdive等仍需后续接入。
- `Content/SourceData/manifest.json`已实际stage：4个binary逐字节相同、76个无损RGBA PNG、84个material绑定；Aya/Weapon同60帧times字节/scale/floor/spawn/group相同，Twisted独立capture group。`Validation/source_bundle_{staging,independent_verification}.json`通过，保留11个UE标准材质不能等价表达的render states（23街景draw main-depth-write+blend及3角色material）。不使用CustomDepth假装主深度，不称完成UE画面。
- standalone C++ core已真实G++13.2/C++17/-ffp-contract=off编译，57checks通过；scene31656的position/UV/RGBA逐bit同，Aya207360+Weapon14580+enemy108000=329940个全60帧点与冻结C probes零bit差异。报告`work/t3b_unreal/Tools/source_core_verification.json`。这是引擎无关core验证，不是UE module编译。
- `Tools/build_unreal.ps1`显式EngineRoot与Build.version5.8检查；`run_editor.ps1`配套UE-Cmd创建材质/地图，用独立run_id拒绝stale report。`editor_build_source_assets.py`保losslessalpha/UV/repeat/vertexRGBA，alpha>ref用If+mask，不掩盖透明depth/order限制。Python/PowerShell仅语法及guard核对，尚未在UE执行。
- `T3B.Replay.Probe`源码设计为读取实际procedural CPU vertex buffer/component world positions，四CSV加probe_metadata/run_id/engine_version完整标记，开始时先失效旧成功标记；`Tools/verify_unreal_replay.py`只接受这种实际UE输出，不接受standalone CSV替代；尚未产生真实UE probes。
- UE安装：用户明确答“尚未安装”，随后启动器实际窗口显示UE5.8.3已在安装中，最后观察约10%。用户物理Esc停止Computer Use，所有后续桌面自动化保持停止，不能自行重新接管。当前后台只读确认EpicGamesLauncher PID63280存在、LauncherInstalled.dat InstallationList空、UE_5.8/Engine目标文件尚未到位；不可据process或目录存在宣称安装完成，也不可重启安装。
- C++工程与运行步骤见`work/t3b_unreal/README.md`。启动器已存在`C:/Program Files/Epic Games/Launcher/Portal/Binaries/Win64/EpicGamesLauncher.exe`，引擎目标文件夹`C:/Program Files/Epic Games/UE_5.8`。安装完成后先实际Build.bat编译，再创建uasset、运行PIE和读回probe；尚未确认Windows MSVC工具链可用。不要安装/重配REA，既有缺工具问题与此不同。
## 最新优先检查点：原版异形与 fire60 已接入（本节覆盖下方旧阶段状态）

**引擎决定（用户最新明确要求）**：正式高清重制选定 Unreal Engine 5，以官方 UE 5.8 稳定系列为迁移基线，C++ + Blueprint。`../t3b_hd/docs/ENGINE_DECISION.md` 已保存官方依据、工具/原型/正式UE工程边界与U0–U3验收；README/REMASTER_PLAN同步。尚未安装/创建/编译UE工程，不能称已迁移。现C/SDL2/OpenGL2.1原型继续作为golden reference；下一步按UE迁移路线推进，保留全部解析与独立数值证据。机器实测RTX2080Ti、i7-11700、31.8GiB RAM，未承诺实际UE性能。

**原街景碰撞联调已解决旧boundary挡原spawn的问题**：新增`src/original_scene_collision.h`、`combat_capsule_triangle.h`，主exe实际编译。默认scene collision为8551个alpha全正的可见static triangles(63materials)，ground1072tri；排除722cutouttri和blend/depthwrite-off状态。ray/LOS用最近static表面，walk用near-ground union9点覆盖+1.84高capsule-triangle距离，保留collision_recovered=0。`--legacy-collision`才用旧4柱；不能简单扩大旧boundary代替此适配。

`--test-source-spawn`主exe实测5shots=4hit/1miss/0blocked、HP0，原spawn均有地面，13项实际几何checks通过，故意毒化旧boundary/加巨柱仍不影响新系统。`out/AYA_M1_SOURCE_SPAWN_PRIMARY_RAY_VERIFICATION.json`独立plane+Gram最大差异8.85e-8 PC；`ORIGINAL_SCENE_COLLISION_C_RUNTIME_VERIFICATION.json`独立选择8551indices全同SHA81b39d61...15d15，ground1072全同，并用约束最小二乘/active-constraint枚举复算capsule：两spawn可走、真实侧墙probe(-3.38577,-8.11244)被墙挡且9点地面覆盖，不是无地面伪阻挡。exe/CSV/checks冻结ORIGINAL_SCENE_COLLISION_C_RUNTIME_PROBES。场景+actor现行报告为ORIGINAL_SCENE_SOURCE_COLLISION_C_RUNTIME_VERIFICATION.json、ORIGINAL_ACTOR_SOURCE_SPAWN_C_RUNTIME_VERIFICATION.json；旧report均是此前fixture，勿混淆。

**武器source1 consumer已取得运行证据，但语义仍候选**：helper8b44580 ABI a0=outptr/a1=drawable/a2=index，经8b3e610 handle wrapper；原始runtime有JIT 0x68替换，已用memory.read(replacements:false)+memory.disasm逐word双重恢复并核对module，不能按前缀放行。`slot0_weapon_marker_{fire_verified,idle_verified,aim_control,square_control}`四组capture：R+square642stops/24source1，idle1108/0，R-only1104/0(1.8353sec)，square-only682/24(1.0691sec)。阳性共48行同返回链8b3e62c→8bbccd0→8b630dc，state+144 primary handle、+148 optional secondary；semanticName仍null，尚缺函数output与实际FX消费证据。`out/WEAPON_MARKER_CONSUMERS_20261020/runtime_audit.json`与`docs/WEAPON_MARKER_CONSUMERS_20261020.md`已保存静态/运行/四控制独立审计。所有capture finally释放输入/只移自有BP/runner恢复INI，未写存档；目前无PPSSPP运行。6离线采集器contract测试通过。

- 详情见 `../t3b_hd/docs/M1_ORIGINAL_ACTOR_FIRE60_20261020.md`。原版异形11 source bones / 28packet / 1800verts / 600tris / 60samples已取代guard外观与射击命中表面；原版256²RGBA atlas完整。C绘制/射线同帧mesh一致误差0；all60 C/source最大6.12383e-5原始单位，`out/ORIGINAL_ACTOR_C_RUNTIME_VERIFICATION.json`。
- `slot0_fire_reverse120_world60`：先120原版帧后退(y=-1)，再R+square采60帧，无近身弯腰段；同帧GE距离5.68..6.70 PC单位。`slot0_fire_retreat90_world60`的y=+1实际接近敌人，保留比较，不作纯射击基准。正式manifest已改fire60（`aya_fire_reverse_capture.bin`/`weapon_fire_reverse_capture.bin`），aim仍3帧，末尾clamp，未恢复完整recoil循环。
- 三骨骼真枪[-1,0,0]，每帧912byte源记录与304byte选中source0实际保存验证；source1+40在枪管端点附近且朝向吻合，但consumer未知，仅muzzle候选；禁止叫已确认socket。source0 GE59.2998I已逐帧读取，不再是假设常量。
- `out/AYA_REVERSE_CLIP_C_RUNTIME_VERIFICATION.json`：Aya全60帧误差3.03906e-5、gun1.57373e-5原始单位；raw/probe/exe冻结在AYA_REVERSE_C_RUNTIME_PROBES。
- `--test-ranged`5shot4真实mesh hit+1墙，kill通过。主exe+新street复测同样4hit kill，独立plane/Gram算法最大差异6.15e-7 PC，`out/AYA_M1_ORIGINAL_STREET_RANGED_RAY_VERIFICATION.json`，actor/exe/CSV冻结于ORIGINAL_ACTOR_STREET_C_RUNTIME_PROBES。旧normal fixture是每36帧离散点击，每枪fire时间归零，按wall-clock姿态有2..3hit、HP50/25，不能泛化为持键失败；新增同spawn/AI/几何的`--test-held-close`6shot4hit2墙kill通过，报告AYA_M1_ORIGINAL_MESH_HELD_CLOSE_RAY_VERIFICATION.json。没有放宽射线或targets；原版近身碰撞/瞄准仍未恢复。
- tools新增`trace_original_actor_source.js`、`recover_original_actor_metadata.py`、`export_original_actor_skin.py`、`verify_original_actor_export.py`、`verify_original_actor_runtime.py`；C新增`original_actor_runtime.h`、`combat_triangle.h`，主exe已实际build。完整actor报告和raw在ORIGINAL_ACTOR_SOURCE_*与AYA_BONE_GE_ACTIONS/original_actor_source_60。
- 原街景已接入主exe：`assets/scenes/original_street/original_street.bin`（T3BSCN1）/`original_street_materials.txt`，140draw/31656verts/10552tris/6WORLD、73纹理/81状态。主程序默认优先此scene，普通手动游戏自动原spawn；各test fixture保留旧位置，`--original-spawn`显式选原位置。`--legacy-scene`才用旧OBJ。新`src/original_scene_runtime.h`保原draw顺序、RGBA、floatUV/repeat、blend/depth-write/cull；不中心化/重缩放。道路CCW有同源几何证据，原fog/stencil尚不支持，旧四柱碰撞仍未对应原街景。
- `out/ORIGINAL_STREET_VERIFICATION.json`独立重算两份GE全部geometry/WORLD/material multiset一致；最大PC位置rounding7.6131e-6，全部UV/RGBA位相同，81states/73 PNG+BMP RGBA/alpha逐字节相同。`out/ORIGINAL_SCENE_C_RUNTIME_VERIFICATION.json`核对C全部31656顶点/5floatbits/RGBA与draw-material顺序零差异，120帧16800draw、GLerror0；exe/probes/结果冻结ORIGINAL_SCENE_C_RUNTIME_PROBES。
- 场景截图`../t3b_hd/build/m1_original_street_spawn_a.png`/b；详见`docs/ORIGINAL_STREET_EXPORT_20261020.md`。原spawn Aya0,0,0，敌人x2.66699/z.02245/yaw-1.579219。Aya同源pose最低点略低road约.01343PC（canonicalframe0约.00171），保留原pose不臆造脚接地点。所有权已从C/export agents交回父代理，主exe已编译，Makefile含新sceneheader依赖。
- 原版AI、hit/death状态、实体碰撞、完整动作、其它章节与高清贴图尚未完成。当前goal保持active。
## 2026-10-20 当前状态

- 确认的 44-bone hierarchy / 106packet 原版模型：`out/AYA_SLOT0_SKELETON_METADATA.json`。
- 正确 GE PRIM replay：`tools/replay_ge_draws.py`；36帧9252有效引用一致，旧整块REGISTERS快照法错误。
- Aya逐draw材质：`out/AYA_EXACT_MATERIALS/`，106packet/3帧318draw一致、原版256²atlas、alpha保留。
- 真枪：`out/AYA_EXACT_WEAPON/weapon.json`。旧weapon OBJ精确命中Aya packet86，已经停用。真实weapon243vertices/81tris/64²材质，12帧独立WORLD相对重放。
- source15 是稳定attachment候选；不是旧source36。原版解剖名称和muzzle socket还未确认。
- `manual_slot0_completed_matrices/metadata_snapshot.json`在bone43完成点暂停采集，证明matrix40*matrix80→GE col-major3x4，525/528bit精确，其余1量化步。
- `out/AYA_SLOT0_CORE_TIMING.json`、`AYA_REFERENCE_CORE_TIMING.json`：存档实际333MHz；不能把旧稀疏采样标成30FPS连续射击。
- M1现已真实加载source骨骼/权重、完整Aya、真枪和两套原版材质；构建无警告，CPU数值和战斗smoke通过。
- 本轮验证和限制：`../t3b_hd/docs/M1_ORIGINAL_SOURCE_SKIN_20261020.md`。

## 本轮已完成

- `trace_aya_action_verified.js` 修复采集：单listener/pending tickets/stop queue，bone43完成点；明确release所有按键，不能用空buttons释放。官方按键R=lock、square=shot已核对。`slot0_aim_verified`/`slot0_fire_verified`各12 source/GE配对，每段1272 Aya draw、3084有效引用全匹配。
- 原生PPSSPP窗口图像已存档：aim图弹药24、fire图弹药15且敌人掉血。详见 `../t3b_hd/docs/M1_VERIFIED_ACTIONS_AND_RAYS_20261020.md`。
- 原始12采样中间有动作过渡，仅选末尾稳定aim3样本、fire2样本，各自`manifest_steady.json`保留原始帧号/ticks/SHA。新clip导出支持独立文件、共同canonical floor/units，13项参数/身份验证测试通过。
- Runtime `assets/models/aya_source_clips.txt` 实际加载aim/fire身体与真枪配对；严格geometry/material/parent/times验证，共用clock、末尾clamp；SPACE可持续开火。没有move asset，不能把reference称为恢复idle/move。
- 实际子弹已移除角度OR/玩家位置LOS OR回退，改用真实枪口方向ray与capsule、碰撞柱最早交点。41项纯几何+12项场景检查通过。`--test-ranged`固定敌人2.55单位外，持续开火4次全命中，枪口后距离1.13..1.15单位，独立端点残差<4.85e-8。默认近距离smoke的枪口处于目标体积内，不单独用它证明远距离瞄准。
- C source数值/同步/战斗验证：`out/AYA_ACTION_CLIP_RUNTIME_VERIFICATION.json`，射线验证 `out/AYA_M1_RANGED_RAY_VERIFICATION.json`。源材质保持原分辨率，Twisted仍guard代理、场景collision仍竖直柱。
- 新增 `capture_bone_pose_action.ps1 -DenseSource`：一次memory.read原子读取44×0x130源记录并scalar校验；`slot0_fire_dense`、`slot0_aim_dense`各60样本，中位间隔33.34/33.36ms。首个GE导出后有200ms空洞，保留真实ticks；其余58段约33ms。
- `verify_dense_aya_source.py`检查每段2640 parent pointers、首尾514有效Aya引用全匹配；F32矩阵乘积/GE有float24截断与近零抵消，报告保留原始位距/绝对误差/roundoff bound，不把近零大位距误判为解剖映射。原始source binary全保留。

## 直接继续的下一项

**本轮已解决逐帧weapon WORLD**：详情 `docs/AYA_WEAPON_WORLD_20261020.md` 与 `../t3b_hd/docs/M1_DENSE_WORLD_CAPTURE_20261020.md`。原版caller8b526b4、drawable+220 F32矩阵，经8c01088上传WORLD；probe3精确geometry/GE payload匹配确认。s0只是排序游标、guest对象地址会变，正式采集逐帧用metadata singlepacket243/vtype522/完整SHA识别真枪。

`slot0_{fire,aim}_world_dense_verified` 各60对body/gun、1.9686秒、33.3667ms中位间隔，无200ms间隙。异步GE请求0/57与真实source sample1/58按257有效influence及body/weapon WORLD全部匹配。`manifest_aligned.json`保存对齐证据，不修改raw manifest。

导出四个 `*_dense_capture.bin`，用独立build/aya_dense_capture_clips.txt加载。`--inspect-capture`逐原始sample time查看，不激活正式manifest。C全60帧验证：Aya误差<3.10e-5、weapon<1.58e-5原始单位，report `out/AYA_DENSE_CLIPS_C_RUNTIME_VERIFICATION.json`，完整probe CSV和SHA冻结在out/AYA_DENSE_C_RUNTIME_PROBES。9项dense exporter测试+4项GE alignment反例通过；默认M1/ranged/ray/asset tests再次通过。

**关键视觉发现**：`../t3b_hd/build/m1_dense_capture_contact_sheet.png`显示fire0..10举枪，20..50明显放低枪/弯腰，59恢复瞄准，不能当纯射击循环。当前runtime正式fire仍只有2采样，持续开火后clamp末帧；没有宣称完整后坐动画。

下一步：给采集器加入以原始帧为单位的pre-roll移动阶段（现有WarmupSeconds没有输入，不能让人物退后），先拉开与敌人的距离，再以R+square采干净60..120帧；按实测状态/原生画面确认边界。另读取weaponObject+3c4的source bone+palette元数据，把中间帧的59.2998I常量假设替换为实际源bone（目前仅canonical和GE sample1/58验证常量）。

**原版敌人新证据**：`out/ORIGINAL_ACTOR_CANDIDATES_20261020/inventory.json` / `inventory.md`，工具 `tools/inventory_recorded_actors.py`。排除Aya106packet与真枪后，只剩同一weighted actor候选，28draw/1800vertices/600tris，geometry group SHA `eed4c94e2a8885a866ebfb0ba29f47701d6795b00275cab52896ae4135a5205c`，11个distinct活跃GE payload（不是已证source bone数）。原版256²CLUT8材质完整RGBA已解码，texture SHA70ee2537a15f93923fa3e732db6ac5d5e0f5f91e6484d57779ba40bf15d406b7。两份pose OBJ及投影视图已提取，视觉显示长臂钩爪异形，不是guard人体。probe3 WORLD记录9/84/159与之精确一致，caller8b526b4、object9b82a90+220（仍不能跨run固定）。下一步可按28packet geometry group重识别，采该对象metadata/完整source骨骼和连续动作，再替换M1guard；不能把目前visible pose提取称为完整FEP或species身份确认。

先检查持键战斗序列中的抬枪/开火/回正/敌人接触段，必要时从备份移动离开近身敌人后重采；可用旧安全slot1但它是手枪、不能复用步枪geometry和材质。不要手工yaw/grip拟合，也不要把source15候选叫成已确认解剖socket；旧source36与weapon OBJ已证伪。

继续恢复移动/受击/倒地与静态动画格式、高清贴图、真正Twisted/场景与章节。完整高清重制goal保持active，本轮只是可验证的M1阶段推进。

## 环境与验证

- cwd `C:\Users\25105\Documents\寄生前夜第四日`；PowerShell UTF8。
- 编译：在 `work/t3b_hd` 执行 `C:\Strawberry\c\bin\mingw32-make.exe -f Makefile.win`。
- 正常战斗：`t3b_hd.exe assets\scene\nyc_block_uv.obj --test`；角色检查：`t3b_hd.exe build\empty_scene.obj --inspect-aya`。
- 远距离持续开火fixture：`t3b_hd.exe assets\scene\nyc_block_uv.obj --test-ranged`；无窗口几何检查：`t3b_hd.exe --test-combat-rays`；资产检查：`t3b_hd.exe --test-source-clips`。
- 全采样检查：`t3b_hd.exe build\empty_scene.obj --inspect-capture build\aya_dense_capture_clips.txt`，随后 `verify_dense_runtime_capture.py`；该模式会输出完整CSV，默认battle测试只输出首尾CSV，冻结证据在out目录。
- CPU验证：`tools/verify_source_skin_runtime.py`，读取M1生成的body/weapon probe CSV与真实原始样本。
- 原存档备份：`raw/state_backups/manual_slot0_20261020_154643/ULJM05798_1.01_0.ppst`，SHA256 `32f7fe3d3d830079d7b4499066eb488562e33ce945765eea8461fc1fca18dc39`。
- PPSSPP采集应加载备份，启动已有其他PPSSPP时拒绝；仅停止本runner启动的进程，finally恢复ini原始bytes。不要广泛kill node/PPSSPP。
- REA工具本session不可用，既有doctor已查注册/runtime问题，不重复安装或改配置；当前证据来自本地MIPS、RAM、PPSSPP与Python/Node工具。

### 2026-10-21 M1 delivery index

当前 M1 可交付范围、验证入口、资产身份和未完成边界统一记录在：
`work/t3b_hd/build/M1_DELIVERY_INDEX_20261021.json`。

该索引对应 C/SDL2/OpenGL verification runtime、SourceData probe/manifest/runtime-identity 三重校验和可选 `--hd-sampling` 包。它没有把可选 4x sampling 解释成纹理细节重建，也没有把 `aya_true_right_hand_timeline` 的 loaded 状态解释成 active binding；当前 `bound=0` 保持不变。


### 2026-10-21 right-hand timeline provenance comparison

新增只读 validator 	ools/compare_hand_timeline_to_clips.py，报告 work/t3b_hd/build/true_hand_timeline_clip_comparison_v1.json。它比较 24 帧 GE hand/mount/muzzle 矩阵与所有 Aya T3BSKN2 clip 的 source bone 36；所有候选的 direct matrix error 均远大于 1e-3，因此不能把这条独立 timeline 绑定到 source-pair runtime。该结果支持继续保持 	imeline_bound=0，并明确记录 coordinate-space/frame identity 仍未知。



最新 smoke：un_m1_hd_sampling.ps1 -TestSourceSpawn exit 0，4 shots hit、enemy_dead=1、Overdive seen/return、muzzle_dir_norm=1.0；当前 	imeline_loaded=1 但 	imeline_bound=0。结果保留在 work/t3b_hd/build/m1_test_result.txt。



### 2026-10-21 approach_fire clip

将已验证的 ya_fire_retreat_capture.bin / weapon_fire_retreat_capture.bin 作为明确的 pproach_fire source pair 接入：只有移动+开火同时成立时选择。--test-source-clips 的5项 selector、8项 transition、8项 clamp 全通过；--test-approach-fire 实际选择237帧，pair sync failures=0。冻结证据在 work/t3b_hd/build/approach_fire_validation_20261021/。该 capture 不被称为通用 strafe、idle 或完整 locomotion。



### 2026-10-21 全量 CLUT/TEXTURE0 匹配

将 17 个已保存 PPSSPP frame capture 目录纳入 match_runtime_clut_pack.py，生成 out/RUNTIME_CLUT_PACK_MATCH_20261021.json。runtime payload signatures=206，exact/subsequence pack 命中=84，较旧报告新增3个1024-byte CLUT子序列命中，均来自 slot0_fire_world_paired3。仍有122个未命中；重复pack记录和FEP语义未锁定，未替换默认M1材质。增量审计为 out/RUNTIME_CLUT_PACK_MATCH_DELTA_20261021.json。



### 2026-10-21 dense Aya source coverage audit

修正 map_aya_source_bones.py：优先使用 manifest 中的绝对 dump 路径，并显式记录无 dump 的帧。对 slot0_aim_world_dense_verified 与 slot0_fire_world_dense_verified 运行后，两个 60 帧 manifest 各只有2帧完整 GE dump；均覆盖同一35/44 source indices，未新增映射。审计 out/AYA_SOURCE_BONE_COVERAGE_20261021.json，缺失 [0,8,10,18,20,24,35,42,43] 保持未解析。



### 2026-10-21 SEDB structural inventory

新增 	ools/inventory_sedb_structure.py，只读扫描 245 个 SEDBSSCF：53,002,424 bytes、统一 version=3/format=0x300400、7,221 个候选 offset regions。报告 out/SEDB_STRUCTURE_INVENTORY_20261021.json；未给任何 region 命名为 collision/nav/trigger，后续仍需 runtime entity/scene correlation。



### 2026-10-21 3rd.fsd structural record discovery

新增 inventory_fsd_structure.py。raw/3rd.fsd 为 7,932 bytes，header count=761；从 0x730 起有 761 个完整 8-byte 条目，所有首字段为1，0x1ef8 处还有 u32=1 哨兵。第二字段高熵且非单调，未命名为 pack offset、room 或 entity ID。报告 out/3RD_FSD_STRUCTURE_INVENTORY_20261021.json。



### 2026-10-21 FSD SourceData reader

新增 T3BFSDIndex engine-independent reader 与 Tools/fsd_index_probe.cpp。probe 对 raw/3rd.fsd 实际读取并通过：version=1、headerBytes=64、recordCount=761、stride field=44、recordStart=0x730、records=761、sentinel=1、packageSize=1344292864。报告 work/t3b_unreal/Validation/fsd_index_probe_v1.json；第二字段保持 opaque。



### 2026-10-21 FSD SourceData staging gate

将 raw/3rd.fsd 以 Content/SourceData/raw/3rd.fsd 纳入 SourceData manifest；manifest gate 重新通过，provenance inputs=85、staged outputs=81。sd_source_bundle_identity_v1.json 进一步确认 source/staged/probe SHA256 完全一致、bytes=7932、records=761。



### 2026-10-21 FSD reader negative verification

erify_fsd_index_probe.py 对有效文件和4个坏输入运行：bad version、bad record tag、bad sentinel、truncated file 均以 exit=1 拒绝；valid case exit=0。报告 work/t3b_unreal/Validation/fsd_index_probe_verification_v1.json。



### 2026-10-21 approach_fire UE SourceData bundle

将已验证的 approach_fire Aya/weapon pair staged 到 Content/SourceData/models/{aya,weapon}_approach_fire.bin，并纳入 manifest；SourceData manifest gate 继续通过，provenance inputs=87、staged outputs=83。两文件与 C/SDL2 runtime 输入逐字节一致，44/1 bones、60 samples。报告 work/t3b_unreal/Validation/action_clip_source_bundle_v1.json。



### 2026-10-21 C++ synchronized action clip reader

新增 T3BActionClip reader/validator 与 standalone ction_clip_probe.cpp，实际读取 SourceData approach_fire pair：Aya 44 bones/3456 vertices、weapon 1 bone/243 vertices、60 samples、duration 1.96863s，body/weapon sample times 逐项相等。报告 work/t3b_unreal/Validation/action_clip_probe_v1.json。



### 2026-10-21 UE toolchain and Game target

官方 VS Build Tools 安装在用户确认 UAC 后完成，`vswhere` 与文件系统检查确认 MSVC 14.44.35207、Windows SDK 10.0.22621.0。UE 5.8 `T3BRemake Win64 Development` 在 ASCII 临时路径执行并通过 35/35 actions（UHT、C++ compile/link），报告 `../t3b_unreal/Validation/ue_game_build_t3bremake_v1.json`。首次中文路径失败是 MSVC PCH 路径乱码；已通过 ASCII copy 隔离，不改原始 source bundle。为适配 UE 5.8，补入 UCLASS opaque state 的 custom deleter、qualified `EStereoscopicPass::eSSP_FULL`、移除 `FRenderResource` 派生的 `final`、删除过时 `Misc/LexFromString.h` include。Editor target 仍需 .NET Framework SDK 才能通过 SwarmInterface。

### 2026-10-21 action clip negative gate

`verify_action_clip_probe.py` 对 staged approach_fire pair 的 valid、truncated weapon、mismatched body 三个 case 均符合预期，报告 `../t3b_unreal/Validation/action_clip_probe_verification_v1.json`。这只验证 binary contract 与 sample-time 同步，不推断动作语义。


### 2026-10-21 UE action clip runtime switch

UE `AT3BReplayWorld` 已接入 manifest `action_clips`：加载时实际读取并验证 `approach_fire` Aya/weapon pair，运行时支持 `T3B.Replay.ActionClip approach_fire` 与 `reference` 切换，默认保持 reference。该切换只影响 visual SourceData replay，不替代原版 gameplay state machine。Build/hash 证据：`../t3b_unreal/Validation/ue_game_build_actionclip_v1.json`。

最新 M1 source-spawn 回归仍通过：`shots_hit=4`、`enemy_dead=1`、`muzzle_dir_norm=1.0`、`overdive_seen=1`、`overdive_return=1`；timeline 继续保持 `loaded=1, bound=0`。


### 2026-10-21 Aya source-bone role audit

基于 `AYA_SLOT0_SKELETON_METADATA.json` 与 `AYA_SOURCE_BONE_GE_DRAW_MERGED.json` 新增 role audit：44 个 source index 中 35 个直接参与 draw/palette，0/8/10/24 是 weighted bone 的非加权祖先，18/20/35/42/43 是当前 metadata 中的 other nonweighted。父子链和 mapping 集合独立 verifier 通过；9 个 index 仍不做 GE placeholder，也不赋予 anatomy 名称。证据 `../psp_parse/out/AYA_SOURCE_BONE_ROLE_AUDIT_20261021.json` 与 `AYA_SOURCE_BONE_ROLE_AUDIT_VERIFICATION_20261021.json`。


### 2026-10-21 CLUT 全量 capture 覆盖复核

重新把 out 下全部 17 个 frame-capture root（共 264 个 `frame_*.ppdmp`）输入 matcher。runtime payload signatures 仍为 206，命中仍为 84，未命中 122；与旧报告 signature set 相等，说明当前已保存 capture 没有提供新的 CLUT/TEXTURE0 byte identity。13 个 root 没有代表行只是 payload signature 去重结果，不是漏采。证据 `RUNTIME_CLUT_PACK_MATCH_ALL_CAPTURE_ROOTS_20261021.json` 与 `RUNTIME_CLUT_CAPTURE_COVERAGE_VERIFICATION_20261021.json`。


### 2026-10-21 original weapon marker SourceData

已把 `WEAPON_SOURCE_FX_LINKS_20261021/recovery_v1/source_markers.bin`（208 bytes、`T3BWMK1`、source index 1/2）逐字节 staged 到 UE SourceData。`AT3BReplayWorld` 现在通过 `T3BGE::LoadWeaponMarkers` 实际读取并验证 marker 定义，UE Game target 35/35 通过。保留边界：这是 source marker 矩阵输入，不等同已命名的 gameplay muzzle/socket；`hurt_warmup` 仍只有 Aya 24 帧，没有同步 weapon pair，未接入 hurt clip。


`weapon_marker_source_bundle_v1.json` 现在关联原版 marker runtime_v2 verification：12 samples、每帧 2 markers、F64 max error `1.11e-16`、5 个坏输入控制，且 source marker SHA 完全一致。该证据仍不命名 gameplay socket。


### 2026-10-21 runtime marker probe output

`T3B.Replay.Probe` 新增 `Saved/SourceReplay/weapon_markers.json` 输出，实际复用已加载的 `T3BWMK1` marker 定义，保留 source1/2、weight、root 和 local matrices，并明确不推断 socket/muzzle 名称。Build 证据 `../t3b_unreal/Validation/ue_game_build_markerprobe_v1.json`。


### 2026-10-21 UE runtime smoke boundary

实际启动 ASCII copy 的 UE Game target 与 `M1_SourceReplay`，Null RHI 初始化成功，但 loose/未 cooking map 在 IOThreadPool 触发 `FBufferReader ReaderPos+Num<=ReaderSize` assertion，exit=3；`T3B.Replay.Probe` 未产生 marker JSON。该结果只说明当前 map/runtime packaging 仍未验收，不影响已通过的 UBT compile。证据 `../t3b_unreal/Validation/ue_game_runtime_smoke_v1.json`。
