# Aya 原版逐 draw 材质与 alpha 恢复（2026-10-20）

当前选定的 Aya 原版 mesh 的 **106/106 packet** 已建立明确 runtime 材质绑定。三个独立 GE capture 中共 **318/318 draw**，几何字节、纹理字节、CLUT 字节和材质状态全部一致；没有未匹配 packet。这里的“一种材质”只适用于当前选定服装/mesh，不推广到全部 Aya 服装、其他 LOD、武器或敌人。

## 输入与精确匹配

- `out/AYA_SLOT0_SKELETON_METADATA.json`：106 packet，3456 vertex records。
- `out/AYA_BONE_GE_ACTIONS/manual_slot0_damage_probe/frame_0000.ppdmp`。
- 同目录 `frame_0011.ppdmp`。
- `out/AYA_BONE_GE_ACTIONS/idle/frame_0000.ppdmp`：旧状态，交叉验证。
- 每次匹配使用 `SHA256(little_endian_u32(VTYPE) + original_vertex_bytes)`，不按 command 序号、包长、屏幕位置或身体部位猜测。
- 每帧106个 packet 各出现一次；PRIM type=3，即 TRIANGLES；顶点数量和 metadata 完全相符。

完整输入 SHA256、源文件 SHA256、每个 packet 的匹配记录、PRIM 所在 register word 和原始寄存器 payload 保存在 `out/AYA_EXACT_MATERIALS/materials.json`。验证所用的源代码为本项目已保存的 PPSSPP `Record.cpp`、`RecordFormat.h`、`GPUState.cpp/.h`、`VertexDecoderCommon.cpp`。alpha/blend/filter 枚举另核对了 [PPSSPP 官方 ge_constants.h](https://github.com/hrydgard/ppsspp/blob/master/GPU/ge_constants.h)。

## 状态时序

`Record.cpp::EmitPrim` 先刷新纹理、顶点数据，再将 PRIM 写入待刷新的 registers。因此，紧随 VERTICES 的 REGISTERS record 必须逐个 word 执行，到 PRIM 处截取状态；同一 record 后面的变化属于后续 draw。不能整块先应用后再绑定前一个 VERTICES。

INIT 同样不是256个连续的 cmdmem：`GPUState.cpp::Save` 在17个 u32之后按 contextCmdRanges 保存寄存器，本工具按该布局恢复。CLUT record 保存的是原始 palette bytes，不能无条件解释为 RGBA8888。初始1024字节 CLUT 和后续 LOADCLUT 分开处理，部分加载只覆盖前缀，保留未覆盖的 palette RAM。

## 观测到的原版材质

| 字段 | 原版状态 |
|---|---|
| TEXTURE0 | 65536 bytes，256×256，buffer width=256 |
| TEXFORMAT | 5 = CLUT8 |
| TEXMODE | 1 = swizzled，mip max level=0 |
| Swizzle | 每块16 bytes × 8 rows |
| CLUTFORMAT | 0xff03，ABGR8888，shift=0，mask=255，start=0 |
| CLUT RAM | 1024 bytes |
| UV | U16 /32768；scale=(1,1)，offset=(0,0)，direct UV |
| TEXFUNC | 0x10100：MODULATE，使用 texture alpha，RGB doubling |
| TEXFILTER | min/mag LINEAR |
| TEXWRAP | U/V REPEAT |
| ALPHATEST | 0xff0006：GREATER，ref=0，mask=255；enabled |
| BLEND | 0x32：SRC_ALPHA、ONE_MINUS_SRC_ALPHA、ADD；enabled |
| Cull | enabled，mode=0 |

纹理 SHA256：`8960ecf7b90c6dd544202bb11bccad8aa069c65e4c3590f26496f55383c0da9f`。

CLUT SHA256：`101044bdb1c61f296f22d7c68d44061a9f22195655c5324e321a97ad8d5c8a87`。

解码 RGBA SHA256：`15d1850ff7828d8c60989b9115f741139df8795659a9e142d9cd3c5ebe857955`。

图像已视觉检查，包含 Aya 的脸、头发、皮肤、黑色服装和破损牛仔裤。解码后的 alpha 范围2..255；65536个像素中24718个不完全不透明。alpha 来自原版记录，不能一律设为255。图像未增强或生成细节。

## 接入接口与产物

目录 `out/AYA_EXACT_MATERIALS/`：

- `materials.json`：`packets[*].runtime_material_indices=[0]`，同时保留内容摘要 material_id；observations 给出各帧完整状态。
- `aya_506dc44780fe0539.png`：原始256×256 RGBA，top-left rows，不预翻转。
- `aya_506dc44780fe0539.bmp`：BITMAPV4HEADER，32bpp BGRA bottom-up，BI_BITFIELDS，显式 RGBA masks。用 Pillow 重新读取后全部 RGBA bytes 与 PNG 一致。
- 同名 `.texture.bin` / `.clut.bin`：供独立检查的原始纹理和 palette RAM。
- `aya_original_materials.txt`：简单 M1 交接格式，路径供 parent 复制资源后使用。

```text
T3BMAT1 1
0 assets/materials/original_aya/aya_506dc44780fe0539.bmp 0 1 1.0 1.0 0.0 0.0 0 0
```

列为 `material_index texture_bmp_relative_path alpha_test_ref alpha_blend uv_su uv_sv uv_ou uv_ov wrap_s wrap_t`。wrap取0=repeat、1=clamp。此格式对当前已验证状态固定使用 GREATER alpha test 和标准 alpha blend。完整状态仍以 JSON 为准。实现原版颜色时还需要等效 MODULATE 与 RGB scale=2，不能将“正确 atlas”视为已经完整复现光照。

## 验证与边界

新增 `tools/exact_aya_materials.py`；没有修改旧提取脚本、原始 capture 或 M1 runtime。`tools/test_exact_aya_materials.py` 的7项语义回归测试全部通过：PRIM前后寄存器隔离、INIT布局、部分CLUT加载、swizzle块行顺序、16bit palette和CLUT index转换、拒绝未知CLUT条目、BMP alpha和上下行方向。

```powershell
python -X utf8 -m unittest discover -s work/psp_parse/tools -p test_exact_aya_materials.py -v
python -X utf8 work/psp_parse/tools/exact_aya_materials.py --metadata work/psp_parse/out/AYA_SLOT0_SKELETON_METADATA.json --capture work/psp_parse/out/AYA_BONE_GE_ACTIONS/manual_slot0_damage_probe/frame_0000.ppdmp --capture work/psp_parse/out/AYA_BONE_GE_ACTIONS/manual_slot0_damage_probe/frame_0011.ppdmp --capture work/psp_parse/out/AYA_BONE_GE_ACTIONS/idle/frame_0000.ppdmp --out work/psp_parse/out/AYA_EXACT_MATERIALS
```

未在这里建立 FEP/pack 中的唯一资源身份；相同 texture bytes 可能存在多个资源副本。没有推断其他服装或武器的材质，也没有把 framebuffer、压缩纹理或非 direct UV 的未支持情况强行套到此材质。此次只负责材质证据与资源导出；M1 runtime 的接入与整体验证由 parent 负责。
