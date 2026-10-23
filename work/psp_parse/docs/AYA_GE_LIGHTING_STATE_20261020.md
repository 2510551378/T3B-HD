# Aya 原版光照状态：已恢复的输入与当前 UE 差异

`tools/inventory_aya_ge_lighting.py` 对既有三个原版 PPDMP 逐条重放 GE words，在真实 PRIM 位置核对106个 Aya packet 的 VTYPE/完整几何 SHA、primitive/count、全部相关 register payload 与原材质快照；共318个观测全部一致。PPDMP reader/context range沿用既有格式工具，没有将此步骤称为全新独立容器解析器。

结果为 `out/AYA_GE_LIGHTING_20261020/lighting_states.json`：damage frame0/frame11各106个draw共享一个光照状态，idle frame0的106个draw共享另一个状态。两个状态均 lighting enabled、Gouraud、启用light0/1/2而禁用light3，light0为directional、light1/2为point；材质颜色为白色，原顶点格式不含color0。light type、computation、RGB8颜色、float24位置/方向、attenuation、全局ambient与specular exponent都保留原payload及解码值。

原materialupdate虽为7，但没有color0时不能把它解释为已经存在顶点颜色；这一条件与 [PPSSPP v1.20.4 Lighting::ComputeState](https://github.com/hrydgard/ppsspp/blob/v1.20.4/GPU/Software/Lighting.cpp#L136) 一致。light computation的枚举依 [同版本 ge_constants.h](https://github.com/hrydgard/ppsspp/blob/v1.20.4/GPU/ge_constants.h#L382)：1为diffuse和specular，2才是powered diffuse，不能凭数字名称猜测。

当前保存的 `M_Aya_000` 是unlit基线，manifest中rgb_scale=2、blend=1、cull=0、源要求depth_write=1。native glTF没有COLOR_0；它没有携带C预览的动态face-shade值，也没有实现原版三灯计算。原始纹理RGBA已保存，并不意味着最终身体颜色已经正确。已有native preview材质的这些差异必须保留在视觉验收中，不以重新绘制贴图掩盖。

本报告只恢复三份记录的光照输入，未将它套用为60帧全时段或其它关卡/服装的固定配置，也没有计算/认证最终lit vertices。实现对应shader前仍需核对原WORLD与坐标单位、weighted normals、diffuse/specular精度、texture function/colorDouble、UE输出色彩与曝光，以及混合/主深度/剔除/逐draw顺序。UE实际离屏图像仅作为当前baseline的可见结果，不能先称原版pixel-equivalent或高清完成。
