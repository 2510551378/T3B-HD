# 原版武器特效颜色：实际 native GPU 验证

已验证此前同运行 CPU→GE 精确匹配的 3 组、24 次 draw。生产颜色 core 从 CPU 改写前顶点、原 palette、颜色引用与 source/parent RGBA 开始执行，再交给生产 geometry decoder；在 NVIDIA GeForce RTX 2080 Ti 上实际运行 D3D11。其 VS 输出、RGBA、owner 和 depth-stencil buffers 与直接使用原 GE 顶点的路径逐 byte 相同。

- [实际三帧与对照预览](../../t3b_unreal/Validation/fx_palette_gpu_runs/96c007b73ee04d5cb5055ad87d887f3a/PREVIEW.html)
- [独立验证报告](../../t3b_unreal/Validation/fx_palette_gpu_runs/96c007b73ee04d5cb5055ad87d887f3a/independent_verification.json)
- [原文件保护与工具快照](../out/FX_PALETTE_GPU_20261021/checkpoint.json)
- [此前 CPU→GE 证据](FX_VERTEX_COLOR_GE_20261021.md)

原始 WORLD/VIEW/PROJECTION、UV scale/offset、64×32 原 CLUT 贴图、alpha test、双倍颜色/alpha、加法 blend、GEQUAL 与禁写深度状态保留。24 draw 展开 144 个 GPU 顶点、48 个三角形；最大投影偏差 0.000005856 PSP pixel，小于原定 0.01 阈值。实际 blend/depth getter 每 draw 检查；12 次捕获另检查 raster、sampler 与 PS SRV 绑定。

| 原记录 | owner pixels | 有 RGB 的 pixels | 换白贴图的 RGB 差异 pixels |
|---|---:|---:|---:|
| 0 | 1711 | 1329 | 1699 |
| 1 | 2056 | 1622 | 2040 |
| 2 | 2234 | 1761 | 2222 |

每帧另运行两组对照。改写前颜色在相同当前矩阵、UV 和材质下不产生可见特效；这不是上一完整游戏帧。将原贴图替换为白色会改变 RGB，但几何覆盖一致。另一个明确合成的 additive/double-alpha 校准样例给出预期 RGB。总计 13 次实际 GPU 捕获。已人工查看三帧输出和两种对照，呈现橙黄色放射形特效。

最终 native 进程 PID 10308，自然退出 0；前一次 PID 95456 运行留存，但最终 proof 指向增加 raster/sampler/SRV 检查后的新运行。旧 reference renderer 未改动：保留源副本，adapter 仅将旧 main 重命名以复用实现。当前 verifier 首次因 sparse register dictionary 缺少未出现命令的键而失败，修为与输入序列一致的零初始化比较；失败源码与说明保留在 verifier_audit，修正后通过，未重复运行 GPU。

验证范围是孤立特效在黑色背景上的 native D3D11 回放。两个输入路径共享现有 source-state renderer，因此不构成原 PSP 最终 framebuffer 的独立像素真值，也没有验证完整场景遮挡。正式 UE module、默认 M1、高清纹理和可玩战斗尚未完成。原 ISO、slot0、INI 与 185 个既有 UE 包逐文件哈希保持一致。

下一步应接入正式 UE pass 与场景组合，或继续未恢复的共享属性/生命周期；不重复把此孤立特效子集当作新的完整战斗进展。工具链按本次用户新授权另开安装记录，结果独立保存，不能由上述 native GPU 验证代替。
