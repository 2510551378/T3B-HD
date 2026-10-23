# 原版逐采样街景实例集：12组实际UE回放

已恢复并在实际UE5.8.4／D3D11中回放12组原街景实例集，与各自同dump的Aya、枪械和原相机配对。前4组各140次街景draw，后8组各126次，共1,568draw／358,488场景顶点。独立原PPDMP重算、实际组件读回和73张Texture2D Source RGBA检查通过。

[逐采样预览](../../t3b_unreal/Validation/paired_street_series_ue_runs/f13b293ea4de4f258b16b4d7250f9339/PREVIEW.html) · [12组联系表](../../t3b_unreal/Validation/paired_street_series_ue_runs/f13b293ea4de4f258b16b4d7250f9339/STREET_CONTACT_SHEET.png) · [独立验收](../../t3b_unreal/Validation/paired_street_series_ue_runs/f13b293ea4de4f258b16b4d7250f9339/independent_street_series_verification.json)

这是原版采样回放进展；没有恢复原时钟、完整关卡、高清材质或完整M1。

## 实例变化与对象身份

原140draw引用128种vertex payload signature，不能把每种signature当唯一场景对象。源GE每次draw的WORLD必须单独保留。

之前发现的3个新WORLD值对应旧参考draw67／68／69的三种顶点payload。三者在sample4开始使用同组新的平移，原局部顶点仍相同。但没有原CPU对象指针／资源实例ID证据，**不能认定为同一物体移动，也不能生成插值轨迹**。

整个采样中有9种几何signature出现多个WORLD；其中6种在旧参考里就被多实例复用，另3种出现参考外的新WORLD值。`world_instance_summary.json`区分这两类，不把它们写成9条对象动画通道。后8组未观察到的其它旧实例不据此叫作删除，也没有确认原CPU的裁剪原因。

## 数据恢复与UE执行

`recover_paired_street_snapshot.py`增加按sample恢复：先按原vertex payload signature查找已验证街景bank，再严格匹配实际material parameters和有效CLUT RGBA，优先保留同WORLD参考；没有同WORLD参考时接受实际记录的WORLD，并保留候选索引及`temporal_object_identity_verified=false`。材质有歧义则拒绝，不凭draw序号推断。

`recover_paired_street_series.py`逐份生成12个T3BSTG1桥接文件及series manifest，原VIEW／PROJECTION必须对应当份Aya机位，选中街景draw全部早于Aya。新sample0 binary与上一轮snapshot binary逐byte相同。

新 `ge_paired_street_series_capture.py`在最多140个临时DynamicMesh component中复用渲染存储。相同raw geometry signature只更新位置；signature改变时重建原UV、颜色和三角数据。sample4有89个buffer slot重建，其余后续组无需重建；14个超出本组draw count的槽位隐藏。**slot只是buffer storage，不是原游戏对象ID。**

真实run `f13b293ea4de4f258b16b4d7250f9339`，PID85364，自然exit0。显式`--street-series`模式通过原content-only probe工程离屏运行，没有加载未编译的GE C++ module。36份角色分离图、1份hidden、12份marker及24份街景图共73个frame PNG，另有73张实际街景Texture2D Source PNG及1张weapon Source PNG。root实际看过整份街景联系表。

## 验收范围

`verify_ue_paired_street_series.py`重新解码原12份PPDMP，完整枚举对应该街景bank的实际draw key，要求与每份导出实例集完全相等，不能挑选少数通过的draw。逐draw检查：

- 原PRIM registers、WORLD／VIEW／PROJECTION和raw geometry identity。
- 原POS16与F24 WORLD在F64中重算的UE厘米位置，对bridge和实际component position逐bit一致。这里检验数据接入，不是原PSP浮点GPU寄存器读回。
- vertex color F32、原UV F32、triangle顺序／multiplicity，以及全流offset连续无遗漏。
- 数值化component world transform确认为identity，实际material binding、cull和组序priority一致。
- 同dump有效CLUT解码与73个实际UE Texture2D **Source** RGBA相同；不是GPU mip/filter或最终像素等价。

已接受的12组原机位adapter property保持相同，角色单独图与先前camera baseline逐像素相同；sample0两份街景图与上一轮snapshot逐像素相同。独立72个GPU相机标记检查再次通过，最大中心偏差约0.5484个PSP像素，阈值1像素。

普通UE透明材质透体仍在，原fog／stencil／blend＋主深度语义没有因上述数据检查变成通过。原时钟和对象身份未知，不自动循环或插值；预览只手动选样本。

## 新找到但尚未接入的draw

独立auditor同时列出不属于旧街景bank的VTYPE0x11f：合计40次观察，8种vertex payload signatures、7种有效CLUT解码RGBA variants。它们不等于8个已经命名的模型或7个原贴图文件，可能包含可变顶点／palette状态。

`out/PAIRED_STREET_SERIES_20261021/unmatched_v1/observations.json`保存其每次原WORLD／VIEW／PROJECTION、完整registers、texture／CLUT身份及解码PNG，语义名保持null，当前UE图没有渲染它们。

其中每组开头有一个594顶点draw，VIEW平移全零且VIEW／PROJECTION均不同于主机位，fog关闭、depth-write关闭。root直接查看过其128×128原贴图，内容为云层。**推测为背景天空用途**，没有确认原游戏资源语义名。不能把该draw直接套入主机位，也不能据当前黑背景说天空资源不存在。下一步应保留独立draw camera来恢复这一组，并处理其余未知实例。

## 保护与后续

184旧UE package和原ISO／slot0存档／PPSSPP INI重查hash相同，无新增／删除package。执行producer、helper、auditor及依赖源码均留SHA和冻结副本；之前snapshot及验收报告未改。没有启动PPSSPP、系统安装或桌面自动操作。

工具链授权依旧有效，但先前Windows RunAs已取消、安装未启动，已有UAC诊断问题仍待回复，本轮没有重试。正式UBT、GE C++ pass、场景fog/stencil/透明深度、Twisted、原碰撞、高清素材及完整M1仍须继续完成。
