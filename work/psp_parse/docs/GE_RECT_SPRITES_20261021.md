# 原版矩形 sprite 恢复与 GPU 验证

从同 12 份 Aya／枪械／异形 GE 捕获中恢复 VTYPE0x119 的矩形批次，共 13,950 个原端点、6,975 个矩形观察。保留原 position／UV／RGBA4444、WORLD／VIEW／PROJECTION 和原 CLUT。1,075 个具有可见候选覆盖的 quad 生成 6,450 个 GPU 顶点，白色环境粒子现已和原角色／FX／街景同帧显示。具体原 FX 名称尚未定位。

## 固定源码与规则

矩形是投影后屏幕对齐的原语，不能把两个任意 3D 端点补成普通 world quad。固定 PPSSPP v1.20.4 的 `DrawRectangle` 使用第二个端点的颜色、Z16 和每个矩形分片的 fog。`ProcessRect` 在 fog 差异超过半步时沿 X 分半，并反向选取 fog；反向端点的 UV 方向也随之变化。本批真实数据没有触发 fog 分半，补充诊断样例另行验证该路径。[固定版本 Clipper.cpp](https://raw.githubusercontent.com/hrydgard/ppsspp/v1.20.4/GPU/Software/Clipper.cpp)

`build_ge_sprite_reference.py` 保存完整原源码与 SHA，按原样提取／编译 `ComputeTransformState`、`ClipToScreenInternal`、Dot43、`ClampFogDepth`、`ProcessRect` 和 `DrawRectangle` 函数，Math3D／fast_matrix 头保持原字节。显式测试适配器仅提供保存的寄存器、framework／bin／输出记录接口；纹理采样、alpha、depth test、blend 不在该 reference 中执行。使用完整 drawing scissor 范围作为 bin；reference 的候选像素不是原游戏最终像素，不能由此宣称完整 PSP／PPSSPP hardware backend 色彩等价。

## 原始输入与独立几何检查

新 `recover_ge_sprite_inputs.py` 导出 `GE_RECT_SPRITES_20261021/source_inputs_v1`，桥接 `T3BSPR1`，12 个原 draw、6,975 个源矩形及一张 32×32 有效原 RGBA atlas。它不凭空增加原采样时刻或 authored emitter。

`ge_sprite_geometry.py` 使用明确 F32 运算顺序重建原端点、1/16-screen rounding、Z16、clip rejection、rectangle UV／fog／coverage，并生成矩形 quad。`export_ge_sprite_geometry.py` 再读原 PPDMP 独立核对输入，逐项对照实际编译的固定上游 reference：

- 全部 13,950 个端点的 clip／fog bits、outside-range 标记一致；有效端点的 screen X／Y 与 Z16 一致。被原规则拒绝的端点不拿无关 screen Z 转换值作有效数据。
- 313 个矩形被源 clipping 规则拒绝，其余 6,662 个分片被完整记录；这批没有 fog 分半。
- 全部 26,867 条候选 pixel calls 的坐标、UV F32、fog、RGBA 和 Z16 逐 byte 一致。
- 1,075 个分片在 drawing viewport 内有候选覆盖，生成 6,450 点；其他分片没有可见覆盖，保留其源记录。真实样本可见部分都是反向 X／正向 Y 的 UV 方向，不能据此说四种方向都已由原样本验证。

quad 保留每个分片的第二端点颜色、Z16、flat fog 和原 UV 方向／采样相位。其展开结果与本次捕获相机相关；原端点与矩阵继续保存，换 PC 相机时要重新计算。原角色、枪械、街景和条带 FX 仍用原有真实 3D 几何，没有把整幅图片贴回场景。

## 新 GPU 格式与原 depth 差异

`merge_ge_sprite_scene.py` 生成自定义 `T3BGEF3`，顶点为 `position3, UV2, sourceFog1, primaryColor4`，40 bytes；原 36-byte 顶点只插入 sourceFog=0，并分别保留旧、新格式 checksum。Sprite 批次携带每顶点 flat fog，其余 3D draw 的 fog 计算保持。

新 `ge_sprite_reference.cpp`／`.hlsl`／`run_ge_sprite.py` 实际使用 40-byte layout。原 sample3 的矩形 depth function 为 **GREATER(6)**，其他为 GEQUAL(7)，通过新 flag 保留并实际 OMGetDepthStencilState 检查；没有把所有矩形强行设为 GEQUAL。Sampler clamp／single-level linear、alpha>0、source-alpha blend、no-depth-write 与原源状态对应。

正式 UE C++ pass 尚未支持此格式或运行。这个 native pass 仍使用 D24S8／连续 D3D texture/interpolation/blend，与原完整固定点栅格、D16 main depth、framebuffer alpha-stencil 不等价。

## 实际执行与 13 个诊断样例

初版 reference_v1 因测试适配器缺 SSE4 include／dither getter 编译失败，stderr 与原 driver 留档；修复适配器后 reference_v2 实际通过，未改上游算术函数。合并 scene_v1 的新顶点 checksum 未更新，被保留为未执行 GPU 的 metadata 问题；scene_v2 采用独立 40-byte checksum 后进入实际 GPU。

基础 run `2e663ad...`／PID73200 完成 115 个实际采集并通过。补充 synthetic contract v1 的 case9 标签把 drawing-viewport 裁剪误叫 GE screen-range 拒绝，数值对照仍正确；原记录与标签说明保留。最终 v2 区分这两条路径，共 13 个明确标记的 synthetic cases；没有把它们当成新原版姿态。

最终 run **`d73d3f8edb0b4c629d0c991f9b46768b`**，PID89456 自然退出0，RTX2080Ti：108 个源状态干预＋7 个既有数值控制＋13 个 sprite 诊断，共128采集。`verify_ge_sprite.py` 通过：

- 89 个实际 GPU atlas staging readback 同输入；sprite 贴图再次对原 PPDMP 的有效 CLUT 解码核对。
- 原有 438,105 条实际 GPU VS 输出 byte exact；新增 6,450 条 clip／UV／flat color／fog 同已验证 quad 数据。
- 关闭 sprites 后的实际颜色、draw owner、depth-stencil 与此前条带 FX 基线逐 byte 同；新增 sprites 不改 main depth-stencil。
- 实际 sprite owner 覆盖在固定上游候选覆盖以内，RGB 改变只发生在真正存活的 sprite fragments。每组 owner 321–945 px，RGB 改变312–911 px。
- 13 个 GPU 诊断核对四种端点方向、第二端点色／深度、fog 分半／小差值、退化矩形、Z／GE screen range rejection、drawing-viewport crop。候选覆盖 mask 完全相同；所选白纹理连续 blend 数值最大差实际为0 LSB（接受上限1）。相等深度下 GEQUAL 实际通过、GREATER 实际拒绝。
- 原115采集的345份颜色／owner／depth读回与基础sprite run全部 byte exact。root 实际查看了完整12组联系表与 rotated-fog诊断图。

## 仍未完成

新粒子仅接入独立 native reference，未接正式 UE／M1；原时钟、敌人 AI、伤害／受击倒地、原碰撞、命名手骨／枪口、高清材质和完整游戏仍未完成。上一轮武器 FX anchor 仍是候选，没有据此替换 M1 socket。MSVC／SDK 因先前 Windows 提权取消尚未解决，用户授权有效、已有 UAC 诊断待回复，本轮没有重试安装。

原 ISO、用户slot0、INI 与现有185个 UE packages 末尾 hash 全同。本轮没有启动 UE／PPSSPP，也未改旧资源包。完整目标保持 active。

下一步可恢复 source line segments，并用它们和原 FX origin 候选追实际枪口／attachment writer；HUD 和 framebuffer postprocess 仍缺。涉及 FRAMEBUF record 时要核 header／flags 与 replay dependency，不能把其 RAM tail 一律当作本帧原 GPU 像素或背景 PNG。

[实际矩形粒子预览与关闭对照](../../t3b_unreal/Validation/ge_sprite_runs/d73d3f8edb0b4c629d0c991f9b46768b/PREVIEW.html) · [实际 GPU 独立检查](../../t3b_unreal/Validation/ge_sprite_runs/d73d3f8edb0b4c629d0c991f9b46768b/independent_verification.json) · [原端点／固定上游对照](../../t3b_unreal/Validation/ge_sprite_runs/d73d3f8edb0b4c629d0c991f9b46768b/sprite_geometry_proof.json)
