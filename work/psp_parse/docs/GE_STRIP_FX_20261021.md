# 原版 depth-tested 三角条带 FX 恢复

本轮从与 Aya／枪械／异形相同的 12 份原 GE 捕获中，恢复全部满足原 perspective、main framebuffer、depth-tested、unweighted triangle-strip 条件的 draw。新增 407 次 draw、3,081 个展开三角顶点、10 个有效原 CLUT RGBA 变体。合并场景为 3,635 draws、438,105 条实际 GPU 顶点输出、88 个原 atlas。

## 原始状态与导出

新 `recover_ge_strip_fx_scene.py` 从已验证场景桥接格式读取原有 draw，原数据／材质／相机／顺序保持；逐原 PRIM 重放其余源状态。支持 VTYPE 0x81、0x102、0x19f、0x11e 的实际 S8／S16／F32 position、U8／U16／F32 UV、RGBA 或原 material ambient color。原 triangle strip 按奇偶 winding 展开，退化三角仍保留顺序和重数。

这些 draw 全部 unlit、depth-test GEQUAL、depth-write disabled、stencil disabled；UV 不全是单位映射，实际 scale 包括 2.0、1.84375、13.953125 等，offset 也变化。按原 F32 direct-UV scale／offset 烘入 UV 输入，保留 repeat／clamp。min-filter raw=7 的 draw 仍记录 mip_max_level=0，当前实际只有一级纹理，使用该级 linear sampling；没有凭空补 mip atlas。

原 blend 有 0x32（source-alpha／inverse-source-alpha）、0x76（double-source-alpha／inverse-clamped-double-source-alpha）和 0xa6（double-source-alpha／FIXB=white）。新 `ge_strip_fx.hlsl` 在 fog 后用未截断的 2*a 预乘 source RGB，目标使用 inverse-clamped-alpha 或 ONE；alpha test 在此前按原开关执行。实际 OMGetBlendState 检查已启用的 source／destination factors，关闭 blending 时只检查 enable，避免把 D3D runtime 规范化的无效 factors 当作生效差异。

`T3BGEF2` 是自定义导出格式，新增 sampler、double-alpha、FX category、alpha-test-disabled 和 raw cull winding flags，未声称是 PSP 文件格式。每次 draw 保留自身 VIEW／PROJECTION；FX 的不同 VIEW 不再被错误当作天空背景。

## 精度问题与失败记录

首次 exporter 只支持 cull-mode=0、单位 UV，实际源状态暴露了两项假设错误。`inputs_v1`／`inputs_v2` 的 failed producer 与失败原因保留；实现支持两种有效原 winding，并恢复原 UV affine。

第一组 synthetic double-alpha 控制漏设 blend-enable，验证不通过，保留 run `efd737.../failed_control_audit.json`。随后状态检查错误约束了 blending disabled 时未使用的 factors，两个失败 run 的实际 stderr 和 diagnosis 保留。正确检查仍要求所有生效 factors 一致，全部数值控制不变。

`inputs_v3` 统一减去 Aya 世界原点。部分 FX 的 placement 编码在 VIEW 中，其原顶点本来很小；统一重定位造成 float32 相消，source sample0 最大可见投影差 0.055496 PSP 像素，超过既定 0.01。原 producer／auditor／失败报告留在 inputs_v3 和 run `b52e354...`。最终 `inputs_v4` 使用每个 FX 原 WORLD bbox 的中心作局部原点，并保留等价矩阵；这仍是真实 3D 局部几何，未改为屏幕 PNG。最终最大差降至 0.0000376102 PSP 像素，检查阈值没有放宽。

## 实际 GPU 检查

新 `ge_strip_fx_reference.cpp`／`run_ge_strip_fx.py` 在 RTX 2080 Ti 上实际编译 D3D shaders 并执行。成功 run `eb127720dab34700b91773818e73350e`，PID 79512 自然退出 0；91 组实际 GPU color／owner／D24S8 采集（12×7 源状态干预＋7 synthetic）。

新 `verify_ge_strip_fx.py` 独立从原 PPDMP 重算 eligible draw 全集、原矩阵、flags、UV affine、primary color、strip parity 和 CLUT binding。407 次源 draw 无遗漏／虚构；3,081 条新增实际 VS stream-output 的 clip／fog 在 F32 算术界内，UV／color bits 同输入。88 份实际 GPU atlas staging readback byte exact。

原有 435,024 条 GPU VS 输出逐 byte 保持；关闭新增 FX 后的颜色／规范化原 draw owner／depth-stencil 与已接受的含异形基线逐 byte 相同。开启 FX 后 main depth-stencil 不变，符合其原 no-depth-write contract。三种 double-source-alpha 控制在实际 GPU 上得到 [48,96,144]、[96,191,255]、[128,255,255]，原 fog／stencil 控制也全同既有结果。

root 已查看全部 12 组 CONTACT_SHEET。画面出现烟雾、闪光、红色碎片与地面暗影；源名称及 gameplay cause 尚未确认，不能仅根据外形把每项标为 muzzle／hit。D3D texture filtering／interpolation／blend 仍使用连续算术，与完整 PSP integer pixel、D16 depth、framebuffer alpha-stencil 耦合不等价。

## 武器 FX 原点候选

新 `analyze_ge_fx_weapon_anchors.py` 保留每个 FX 的原 local origin，经 FX WORLD／VIEW 转到主相机对应 PSP world，再通过实际单权重 gun BONE×WORLD 的逆变换进入原武器 local。该 rigid derivation 对真实生产 gun world positions 在原 F32 算术界内。候选 projection 的 X／Y／W 部分与主相机相同，避免把 HUD 位置误作空间挂点。

14／15-vertex 的两次条带 draw 在 samples 1、2、11 中共享同一原点；每组仅算一个独立观察。三次 weapon-local 原点均值约 `[-1.084484, 0.000469, 0.126473]`，最大局部残差 0.002048。它位于原枪几何负 X 端外侧，支持枪口 emitter 的假设。相邻 samples1/2 姿势接近，不能称六个独立姿态验证。

这是候选，原 attachment object／named muzzle record 尚未定位，原枪口方向与 gameplay attachment 未确认，未据此替换任何 M1 binding。完整推导与全部 407 个原点观察保存于 `weapon_anchor_candidates_v1/candidates.json`，run 中附同份副本。

## 未完成与下一步

这些新 FX 仅进入独立 native GPU reference，尚未进入 UE C++ pass／正式 M1。矩形 sprites（VTYPE0x119、每组约千个源点）、line segments、HUD、framebuffer-backed postprocess 仍未恢复。下一步应依据固定 PPSSPP Rasterizer／TransformUnit 的 rectangle 规则恢复 sprite topology／flat color／depth，不能把两个 3D 点随意连成 world quad；也可追踪这份武器 FX 原点的原 attachment writer。

原 ISO、slot0、INI 与目前 185 个 UE packages 在本轮结束后 hash 全同。没有启动 UE／PPSSPP、未重试系统安装。MSVC／SDK 的先前 Windows 提权取消仍未解决，已有用户授权有效、UAC 诊断待回复。UE 透明透体、原 clock、AI／伤害／碰撞／受击倒地、命名 socket、高清材质与完整游戏仍未完成，完整目标保持 active。

[实际 FX 同帧预览与关闭对照](../../t3b_unreal/Validation/ge_strip_fx_runs/eb127720dab34700b91773818e73350e/PREVIEW.html) · [独立 GPU 检查](../../t3b_unreal/Validation/ge_strip_fx_runs/eb127720dab34700b91773818e73350e/independent_verification.json)
