# 原版 FX parent 颜色、更新缓存与实际顶点颜色写入

本阶段恢复 rifle/descriptor `10c78` 的真实颜色消费路径。关键修正：选定对象没有把颜色直接写成 GE material；它用两个原顶点颜色 palette 条目，经缓存调制后改写模型顶点。生产 C++ core 已复现这些实际 CPU 写入，默认 M1 仍待接入。证据根为 `out/FX_COLOR_MATERIAL_20261021/`。

## 实际路径与数据

`color6_v2` 隔离 PPSSPP 采集同一原节点6次 render invocation，每次保留 dispatcher、parent modulation、颜色模式处理、binder entry/return。发生缓存更新时，继续跟踪确切 queue entry→flush→palette converter→vertex patch→flush return。原枪、FEP、definition、resource、geometry 和 context身份沿用严格校验；始终仅一个自有 CPU breakpoint。采集结束后释放输入和断点，只停止自有进程。

两种“mode”不能混淆：

- 原 type155 record `+4b` 是 renderer 的颜色处理 flag，本次值为1，此路径保持调制后的 RGBA。
- 原 model group `+10` 是顶点颜色 palette 的条目数，本次为2。binder 对0、1、多条目采用不同处理；多条目进入缓存。

type155 renderer 的 definition 引用表将颜色关联到同一节点的 type16 共享参数块。实际 parent `P+40` 与 type16 RGBA逐分量 F32 相乘，结果和 renderer 栈上值相同，随后进入 `08b60080` binder：

| 调用 | parent 调制后 RGBA | 缓存行为 |
|---:|---|---|
| 0 | `(128,44.7999992371,4,0)` | 原对象已有相同 bytes，不入队 |
| 1 | `(128,56,8,48)` | 入队并实际转换/改写 |
| 2 | `(128,44.7999992371,4,0)` | 同上 |
| 3 | `(128,56,8,48)` | 同上 |
| 4 | `(128,44.7999992371,4,0)` | 同上 |
| 5 | `(128,56,8,48)` | 同上 |

这里的交替来自实际 parent 颜色，不是新造的闪烁动画。VFPU prefix controls 仍未直接导出；当前 parent 乘法结论是这些真实输入/输出的逐 bit 对应，不外推任意 prefix 状态。

## 缓存与 palette

多色 binder 检查 bank `+28` pending count 与 `+30` capacity，然后按16个原始 bytes比较新 RGBA 与对象 `+10` last color。允许入队时，将 RGBA写入 `bank+24 + count*32`，在 record `+10` 写对象指针，更新对象 last color 并增加 pending count。尾部12 bytes未改；真实 cache record和计数已核对。`+0` 与 `-0` 的 bytes不同，不能用数值近似比较替代 memcmp。

`08b60758` 从 `bank+2c` processed index选择实际 cache record与对象，遍历 group，真实调用：

1. `08b5f684`：输入 group `+14` 原 RGBA palette、cache RGBA，输出到 group `+18` converted palette。
2. `08b5f780`：根据原 draw/inner records 的颜色引用，将 converted palette 写入实际 vertices。

本次只有一个 group/draw-header，processed count 每次实际增加1；不将这个样本的调度规律外推到所有 group 数量。

运行时原 palette 为两条 RGBA bytes：`ff ff ff 00`、`80 80 80 80`。原 converter 先将 tint 各通道乘 `1/128`，再乘 source byte，按 `trunc.w.s` 取整数；仅对整数 `>=256` 置255，最后以 SB 保存低8 bits。它不是除以255，也不是四舍五入或双边 clamp。负值低 byte wrapping 的覆盖仅来自合成原指令样例。

| 实际 tint | 两条实际转换结果 |
|---|---|
| `(128,56,8,48)` | `ff 6f 0f 00`、`80 38 08 30` |
| `(128,44.7999992371,4,0)` | `ff 59 07 00`、`80 2c 04 00` |

5次 palette 转换均逐原 scalar MIPS/COP1 opcode 回放；输出 bytes、返回 GPR/FPR 都与真实停止点相同。这是**顶点颜色 palette**，独立于纹理 CLUT；本阶段没有修改或重新认领纹理 CLUT。

## 实际顶点改写

原 patcher 读取 draw-header、16-byte inner records 及每顶点的 color-reference pointer。每个引用都确切指向刚转换的 palette 中某个4-byte条目；本次是 VTYPE `11e`，stride16、color offset4。每个实际更新覆盖8个 draw/32个 vertices，共5次更新、40个 draw/160个 vertices。

独立审计重新从 raw pointer tables生成预期颜色，只替换原位置的4 bytes，然后与 return 后的完整 vertex buffers比较。RGBA全部相同，UV、position、padding等其他 bytes全部保持相同。这里没有凭“颜色看起来类似”关联资源，也没有把 palette 条目索引猜成 texture CLUT index。

`source_bindings_v1/vertex_color_bindings.json` 导出8个 draw模板、32个顶点及原 color indices、原 palette，交叉检查5次观察的非颜色 geometry/reference布局不变。模板 vertex buffer中的颜色仍是先前某次真实 tint；使用者必须在绘制前按当前 palette重写全部颜色。导出中的 layout SHA 只标识当前观察布局，不是通用原 resource GUID，也未将该 RAM model palette 追溯成新的 ISO 内文件 offset。

## 生产 core 与验证

新增 `T3BGEEffectVertexColor.h/.cpp`：

- `ModulateOriginalEffectRGBA`：原 source×parent F32乘法。
- `ProcessOriginalEffectColorMode`：保留原 flag 的运算顺序。6使用 `1−A/128` 并仅 clamp RGB下界；10使用 `2−A/128` 并仅 clamp上界；9/11/12使用 `A/128` 并仅 clamp上界；其他 flag当前直接保持。实际 flag1，其他分支由原 opcode合成样例验证。
- `NeedsOriginalEffectColorUpdate`：有界 count/capacity 与16-byte精确比较。
- `ModulateOriginalEffectVertexPalette`：原 F32→trunc→上界处理→低byte保存。
- `PatchOriginalEffectVertexColors`：当前支持 `11e` 的 stride16/color4 和 `11c` 的 stride12/color0；后者是明确的合成布局验证。

`runtime_vertex_color_v2` 实际 g++ C++17/O2、`-ffp-contract=off` 编译执行同一生产 core：6次真实颜色/缓存决策、5次真实 palette输出，以及40个 draw/160个顶点的完整改写 bytes全部相同。17个明确合成样例覆盖各 scalar flag、负值/截断、signed-zero cache、cache hit/full与无UV布局；6个非法输入实际拒绝。所有源码、编译参数、exe、输入、独立 reference、输出及 SHA 保留。

`negative_evidence_v1` 再对 palette output、vertex position、producer cache decision分别制造 SHA 一致的坏证据，3次实际独立 auditor 调用全部在指定 gate拒绝；原采集数据未改。

## 保留尝试与范围

`color6_v1` 初次采集在发现多色分支后严格失败并保留，未宣称 material emission成功。`vertex_color_audit_v1` 曾错误使用 JALR 前 a2 作为 renderer record；原 `08b69d68` delay slot实际将 t0复制到 a2，已改为原 opcode校验与真实 t0→record对应，最终 audit_v2通过。`runtime_vertex_color_v1` 因编译器 `-Werror=misleading-indentation` 未构建，保留日志；修正 braces后 runtime_v2成功，没有降低检查。

两个自有 PPSSPP 进程均已终止。`source_protection.json` 核对原 ISO、slot0、INI 与185个既有 UE包哈希相同；本阶段没有启动 UE、桌面操作或重试安装。

当前证据止于实际 CPU vertices写入。没有新的同调用 GE dump/GPU消费或最终像素对照；没有证明其他0/1颜色条目分支、通用 cache调度或所有 VFPU prefixes。正式 UE module、默认 M1、HD美术和完整可玩目标仍待完成。

下一步优先将这条 palette→vertex链路与同次 GE PRIM的 raw vertices对齐，确认GPU实际消费，并把新 color bindings接到现有 effect geometry decoder/native renderer。接入时保持原 UV offset只应用一次，保留原 texture CLUT、矩阵和 blending各自的输入；不要把新顶点palette当成纹理替换。
