# 原版顶点颜色写入与 GE 消费对齐，生产颜色/几何 core 串联

本阶段补齐前轮只有 CPU 写入的缺口：同一次隔离 PPSSPP 运行中，同时取得完整颜色链路和16份 GE 记录，确认3组实际记录使用改写后的顶点。随后将现有生产颜色 core 与 effect geometry core 在同一可执行程序中串联，输出逐 byte 同原 GE 数据。证据根：`out/FX_VERTEX_COLOR_GE_20261021/`。

## 同运行采集

`color6_GE16_v1` 保存6次 exact rifle/descriptor10c78/type155/ID19 调用，5次实际 palette 转换、40次 draw/160个 vertices 的 CPU改写，与前轮相同的 source/record/cache/ABI核对重新通过 `CPU_write_audit_v1`。

新增可选 `FX_COLOR_GE=1`：在首次精确目标入口启动有界并发 `gpu.record.dump`，保留16个原始 PPDMP；颜色 CPU采样完成后移除断点并恢复自有暂停，等待原 GE请求完成。没有在暂停状态等待整帧导致死锁，也没有重启来替代超时观察。实际采集无 CPU/GE failure；runner exit0，自有进程已经终止，输入和断点已释放。

每次还保留真实 VIEW writer `08c01088` 的输入、DL context/cursor、已写入的13-word VIEW packet，以及原枪 WORLD 和 main VIEW，在 writer 与后续 renderer 暂停点的 bytes一致。原 writer输入按真实12个 F32分量打包高24 bits，实际命令必须完全相同。

原 palette flush 使用另一个 stack：前轮 dispatcher约 `09ffe650`，flush约 `083ffeb0`。因此本阶段没有按墙钟先后或“调用后”猜同一渲染帧，而是直接比较记录内容与矩阵。

## 独立精确关联

`correlation_v3/verification.json` 重读原 PPDMP并解析每个 PRIM。候选必须同时满足：

1. 原8个子 draw的 VTYPE、resolved PRIM4、vertex count与完整 raw vertex bytes连续一致。
2. 全部12个 VIEW payload与该次 CPU实际写出的 packet一致。
3. 之前最近的原枪 draw由完整 geometry SHA识别，其 WORLD高24与 CPU原枪矩阵一致，main VIEW高24也一致。
4. 每个 CPU调用最多一个精确匹配，原改写前的8个 buffers不能匹配同一锚定调用。

最终对应：

| CPU 调用 | GE sample | 连续 draw起点 | 子 draw数 | 输入状态 |
|---:|---:|---:|---:|---|
| 1 | 0 | 310 | 8 | after-write |
| 3 | 1 | 312 | 8 | after-write |
| 5 | 2 | 294 | 8 | after-write |

共3份 GE记录、24次 draw观察、96个 vertices；before-write匹配为0。CPU调用2/4没有在这组 GE记录中取得对应，不能据此说它们没有渲染，也不将这些结果扩大成所有调用的全局 frame ID或调度规则。最终运行显式要求保持3个 matched CPU rows的覆盖。

每个匹配 draw保留实际 WORLD/VIEW/PROJECTION、全部 scalar registers、材质、UV、texture/CLUT。原纹理仍是64×32、RGBA SHA `75ee19dc59a0118645523e2711eec0c7e3cfc950a9d8bc0abaa313794d91941d`；新解码 PNG已实际查看。它与原顶点颜色 palette仍是不同的数据层，没有进行高清重绘。

当前匹配输入使用原 UV scale `(1.84375,1.9375)`、offset `(0.5,0)`，repeat、原 alpha test、blend `a6`、color-double 等字段全部保留，不能只把新的 RGBA塞进任意透明材质就认定画面相同。

## 串联生产 core

`ge_effect_tinted_strip_probe.cpp` 实际链接当前生产 `T3BGEEffectVertexColor.cpp` 与已有 `T3BGEEffectGeometry.cpp`，对每条精确 GE对应执行：

`source RGBA × parent → 原 color mode → 原 vertex palette调制 → 按 color indices改写vertices → DecodeOriginalEffectStrip`

输入包含真实原 palette、CPU before vertices、原 parent/source参数，以及该次 GE的实际 registers；不是直接把 GE after vertices作为生产 core输入。独立 reference 则从实际 palette return、GE raw vertices重新解码 local position、UV、RGBA和 strip topology。

`runtime_integrated_v2` 实际 g++ C++17/O2、`-ffp-contract=off` 编译/运行通过：24次 draw、96个 vertices、48个 triangle观察的 palette、完整 patched vertices、position/UV/color/indices全部 bytes相同。UV仅按原 scale/offset应用一次；其他矩阵和 raster/material输入单独保留。4个接口反例（不支持 lighting、UV generation、错误 PRIM、截断）实际拒绝。源码、编译参数、exe、输入、reference、output及 SHA全部保留。

`negative_join_v1` 另外对 CPU after颜色、原枪 WORLD、VIEW writer输入制造 SHA一致的合成坏证据，全部在指定 join覆盖/packet provenance gate拒绝。它们没有修改原捕获或原游戏文件。

## 范围与下一步

这是新的**GE命令/输入记录消费证据**和生产 core串联执行；尚未做这些新输入的最终 GPU framebuffer像素对照，也未运行正式 UE module或切换默认 M1。当前24次观察仍是同8个模型子 draw在3份记录中的重复，不是24种独立资源或动作。

原 ISO、slot0、INI与185个现有 UE包同前基线哈希；仅运行一个隔离 PPSSPP进程，已终止。没有启动 UE、写入 Content、操作桌面或重试工具链安装。

下一步将新的逐 draw bindings用于 native GPU renderer验证，包括原矩阵、CLUT、blend/alpha/depth/cull和颜色；之后正式接入 UE pass/M1。不能因为 local geometry逐 byte一致就跳过变换、raster状态或 GPU输出验证。源 cache调度、其他颜色分支、共享23/24、type6/RNG和完整战斗系统也仍需继续恢复。
