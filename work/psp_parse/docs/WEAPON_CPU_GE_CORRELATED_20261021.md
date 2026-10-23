# 原版 source1 → 视觉特效 → GE draw/CLUT 的同运行交叉验证

## 新采集

使用独立 portable PPSSPP 副本、独立配置和 slot0 副本，隐藏启动并经 debugger API 输入。未修改原 ISO、原即时存档和原 INI；三个自有模拟器进程均已停止。Windows portable 默认 memstick 位置有固定版本[上游实现](https://github.com/hrydgard/ppsspp/blob/v1.20.4/Windows/main.cpp#L849)依据。

`capture_weapon_ge_correlated.ps1` 与 `trace_weapon_marker_ge_emit.js` 新增可选的同暂停点 full WORLD/三 source records，及并发、有界 GE recording。单个自有 CPU breakpoint、返回 ABI、原机器码双恢复、按钮/analog 释放等既有检查继续保留；新增 mode0 `08b657f8..08b6589c` 的完整同次 runtime code identity。

证据根为 `out/WEAPON_CPU_GE_CORRELATED_20261021/`。

| 采集 | 实际 CPU 完整记录 | GE captures | 满足全部条件的 CPU→GE 观察 |
|---|---:|---:|---|
| aimfire12_v1 | 12 | 4 | 0，首批未对齐，原始记录保留 |
| aimfire12_v2 | 12 | 16 | CPU4/5/6/7 → GE0 的4个 draw |
| strafefire16_v1，R+square+left x0.7 | 16 | 16 | CPU4/5/6/7 → GE0；CPU12/13/14/15 → GE1 |

第二次起将录制推迟到首次精确武器/FEP target entry，并扩大到16个 recording。没有通过放宽匹配条件把首批零匹配改成成功。`initial_capture_audit_v1` 仅确认该批证据一致，明确 `original_source1_to_visual_effect_GE_observed=false`。

## 匹配条件与覆盖

`analyze_weapon_cpu_ge_correlated.py` 重新运行原 CPU emission 审计，再直接重读 GE dump。每个匹配同时满足：原 vertices 完整 bytes、VTYPE/PRIM/count、全部12个 VIEW payload、同一 GE 流中此前原枪 draw 的 WORLD payload，以及原主相机 VIEW payload。后两项分别与 CPU 完整 WORLD、CPU VIEW global 的高24位相同。所选原枪还以243顶点/VTYPE522/完整原 geometry SHA 鉴别。

最终为28条 CPU 记录中的12条唯一 GE 对应，覆盖3个实际 GE 记录帧；并非12种独立姿态或12次射击。跨两次采集共有7个不同完整 WORLD snapshot。Recorder 不保留 CPU display-list PC，因此结论是同运行、完整内容的唯一对应，不将其外推为普适 invocation ID。

每条新 CPU 记录在 matrix-entry 和 emitter-entry 保存的 WORLD 与全部三 source records 均逐字节一致。原三 source 的定义 bytes 也与前轮 T3BWMK1 catalog 相同。对 source1 原 local matrix 与同暂停点完整 WORLD 做 separate rounded F32 组合，28/28条均逐 bit 等于真实 state+0x60，不是拿 GE 量化矩阵预测另一个采集。

## 具体 FEP/几何/材质绑定

以下四项在瞄准和移动瞄准的匹配帧中重复观察。descriptor/record 都是已核对 FEP section 的相对 offset；definition index 必须连同 descriptor 使用，不能全局混同。

| descriptor | definition index | 实际 type | 几何 ID / source record | matrix mode | 原 local translation | 匹配材质 |
|---|---:|---:|---|---:|---|---|
| 10ba0 | 7 | 152 | 15 / 2b58 | 1 | (0,0,5) | a8e415f87f8ed3cd…，256² CLUT4/ABGR8888 |
| 10be8 | 5 | 152 | 15 / 2b58 | 1 | (0,0,5) | 同上，但原 input scale 不同 |
| 10c30 | 7 | 155 | 18 / 2690 | 0 | (0,0,5) | 75ee19dc59a01186…，64×32 CLUT4/ABGR8888 |
| 10c78 | 9 | 155 | 19 / 26a8 | 0 | (0,0,7) | 同上，但原 input matrix/geometry 不同 |

完整 descriptor/definition/source/GE 观察目录另存 `visual_FX_bindings.json`，共12项，保留原始 input 与 actual state60。完整原 texture/CLUT/registers、source vertex bytes、矩阵、definition 与 SHA 均在 `correlation_v2/verification.json` 和 `strafe_correlation_v1/verification.json` 中。两张 PNG 是机械解码后的原版材质，已经实际查看；没有高清重绘或猜配贴图。相同 geometry ID 不意味着同一材质/definition，四个实际 draw 的绑定分别保留。

source1 现在有直接的视觉 FX consumer 证据。type152 的 mode1 basis 使用 camera basis，不能把 billboard 面朝方向当枪的方向；原武器方向仍取 source1 +Z。真实 gameplay bullet/raycast/damage 起点未因视觉链路确认而自动确认，marker 的原作者命名仍未知。

## 原指令和生产 core 回放

独立 `verify_weapon_ge_matrix_math.py` 对两次新采集回放原 mode0/1 和 VIEW 指令：24+32=56个实际 stage 输出逐 bit 相同，全部所选 helper 的同次完整 code identity 已齐。VFPU entry prefix controls 仍未由 API 导出，不能宣称所有 prefix/JIT/mode 一般等价。

生产 `T3BGEWeaponMarkers.cpp` 新增 `ComposeOriginalWeaponMarker`：直接 full-F32 WORLD×原 source40，每次乘法和加法分别舍入，不经 GE BONE 或 F64 拟合。`ge_weapon_marker_cpu_probe.cpp` 实际调用同一个 core，读取真实 CPU WORLD，输出与真实 CPU state60 bytes 比较：

- `runtime_F32_v1`：12条、3个不同 WORLD、192 F32 components，0 bit difference。
- `strafe_runtime_F32_v1`：16条、4个不同 WORLD、256 F32 components，0 bit difference。

实际源码副本、编译命令、executable、原输入/原 state60 reference、实际输出 SHA 均保留。这里运行的是生产独立 core；正式 UE module 和默认 M1 射击绑定尚未执行/切换。

`negative_correlation_v1` 的三个合成反例均在预期新检查处被拒绝：不同暂停点 WORLD、SHA有效但被改的 source definition、错误 GE hash。原证据没有被改写。输入覆盖的具体边界见各 verifier；没有把绿色汇总当作全游戏复现证明。

移动瞄准样本的 source1 原点 x/y/z 跨度为7.23535/1.99718/2.75557 PSP单位，+Z 相对首条最多变化3.57766°；瞄准样本对应1.83740/1.71513/2.26931与1.42135°。这是当前短窗口运动范围，不能替代完整射击、转向或 authored animation timeline。

## 下一步

当前只采每个 handler 的首个 CPU PRIM。下一步在 callback-return 读取从首个 emitter cursor 到返回时当前 DL cursor 的完整、有界 CPU 命令窗口，再解析后续 VADDR/PRIM/材质状态；优先把14顶点后的15顶点 companion draw 落到同一个原几何对象/FEP consumer。不能用相同原点或相邻 draw 自动认领。

之后才能补齐视觉 emitter 的全部子 draw 和时间行为，并在正式 M1 中进行视觉跟随/射击验收。原碰撞、弹道命中、伤害、AI 和完整高清美术仍是完整目标的未完成项。工具链提权取消的终态不变，本轮没有重试安装。
