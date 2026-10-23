# 原版 11-bone 异形与 Aya 同帧恢复

本轮将此前 UE 场景链路遗漏的原版异形，按同一份 GE 捕获接入独立 D3D11 场景参考。12 组画面均实际可见。此成果没有替换正式 UE M1，也没有完成敌人 AI、伤害逻辑或高清材质。

## 身份和骨骼依据

原 `ORIGINAL_ACTOR_SOURCE_METADATA.json` 给出 11 个 source bone、28 个有序 draw、1,800 个顶点。新 exporter 对 Aya／枪械使用的全部 12 份原 PPDMP 按原始 VTYPE＋顶点 payload SHA 匹配；每组有且仅有同序 28 个 draw，全部 position、normal、原权重与 UV 对 metadata 的原始分量一致。该模型的外形和贴图支持原版异形的判断；具体敌人名称与解剖骨名没有确认。

对每个原 draw 重放实际 BONE 上传，按已恢复的 palette slot→source index 映射恢复 11 个有效矩阵。每组中重复观察到同一 source index 时，矩阵 payload 必须完全一致；全部 11 个 source index 在每组中均被覆盖。11 组相邻样本比较中，每个 source bone 均有变化。WORLD 在单个角色组内一致，VIEW／PROJECTION 与该份捕获的 Aya 相同。没有使用旧独立 60-frame CPU clip 去冒充同一时刻。

父索引保留为 `[-1,0,1,0,3,0,5,6,7,8,9]`。这些是已恢复的 source index 关系；不能将 GE 有效 skin matrix 当作新恢复的 authored local animation，也不能自行命名手、脚或枪口。

## 实际执行与验证

新 `recover_other_actor_ge_series.py` 导出 `OTHER_ACTOR_GE_PAIRED_20261021/inputs_v1`：336 draws、21,600 顶点、12 组有效骨骼、1 张 256×256 原 RGBA atlas。桥接格式为已有 `T3BLIT1`，不声称是原 PSP 文件格式。

`build_aya_lighting_reference.py` 使用固定 PPSSPP v1.20.4 Math3D／Lighting 源码算术与显式测试适配，实际比较新增全部顶点：transform bit mismatches=0，color vertex mismatches=0。`verify_other_actor_ge_series_runtime.py` 实际编译生产 `T3BGESeries`／`T3BGELighting` 并执行，输出 position／normal／primary／secondary 与 reference 逐 byte 相同，UV bits 保留。这是重建结果与 software reference 的对照，不是原机 GPU 像素采样。

`export_observed_ge_scene.py` 新增显式 `--other-actor-proof`，默认原 Aya／gun 子集保留。新的 `inputs_with_actor_v1` 合并 3,228 draws、435,024 顶点、78 个有效原 RGBA atlas，保留原 draw 顺序和每次 draw 自身相机。当前这 12 份捕获中的所有 weighted draw 均已进入此参考；其他未加权 FX、HUD 等仍未加入，不代表全游戏角色覆盖。

真实 native GPU run `f99ea978f2644fe3aa63b5af15c39251`，PID 77984，自然退出 0。64 组真实 GPU 采集；独立 auditor 核原 PPDMP、GE flags、原 WORLD／BONE／lighting 输入与原 position／normal／weight／UV，核 435,024 条 GPU stream-output、78 份 atlas staging Map、颜色／owner／D24S8。可见顶点投影最大差 0.0000619505 PSP 像素，保留原阈值，fog／stencil controls 全通过。

`verify_ge_actor_addition.py` 对已接受的无异形基线作对照：原有全部 draw 的几何、矩阵、flags、寄存器、有效纹理身份与顺序未变，实际编译的 VS／PS DXBC 逐 byte 一致。每组仅增加 28 draws／1,800 顶点；最终异形 owner 覆盖 2,672–8,755 像素，RGB 改变 2,731–8,763 像素。实际查看全部 12 组 CONTACT_SHEET，模型动作、原贴图、Aya 与枪械同画面可见。

## 未完成与下一步

目前是独立 native D3D11 参考，新异形姿态和 78-atlas 源状态未接入正式 UE C++ pass。普通 UE translucent 主深度问题、PSP 完整固定点栅格／D16 depth／framebuffer alpha-stencil 耦合仍未解决。12 个样本的原时钟未确定，预览仅手动选帧。原碰撞、AI、命中／受击／倒地逻辑、完整 M1 与高清化仍未完成。

下一步将这份同捕获原异形数据接入 UE，保持数据检查和材质绑定；继续恢复原 FX／命中与受击行为。正式 UE C++ 构建仍需解决先前 Windows 提权取消后的 MSVC／SDK 安装；既有用户授权有效，不重复提权或宣称安装成功。

原 ISO、slot0、INI 和 184 个旧 UE packages 在本 run 末尾再次 hash 检查全同。未启动 UE／PPSSPP、未修改旧包或用户存档。完整工作目标保持 active。

[同帧场景与加入前后对照](../../t3b_unreal/Validation/observed_ge_scene_runs/f99ea978f2644fe3aa63b5af15c39251/PREVIEW.html) · [GPU 独立检查](../../t3b_unreal/Validation/observed_ge_scene_runs/f99ea978f2644fe3aa63b5af15c39251/independent_verification.json) · [原有输入不变与新增异形验证](../../t3b_unreal/Validation/observed_ge_scene_runs/f99ea978f2644fe3aa63b5af15c39251/independent_actor_addition_verification.json)
