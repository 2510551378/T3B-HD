# 原版 FX 属性回调、type155 UV 曲线与实际 GE 命令写入

本阶段把上一轮节点时钟继续接到原属性回调和实际 UV OFFSET 命令。原版 descriptor `10c78` 的 type155 六个曲线字段已导出，生产 C++ core 实际执行通过。证据根：`out/FX_PROPERTY_CURVES_20261021/`。原 ISO、slot0、INI 和185个既有 UE 资源包哈希保持不变。

## 实际采集与原记录绑定

隔离 portable PPSSPP 隐藏运行，读取 slot0 副本。初始在 `08b69d64` 精确选择原 rifle 的 type155/ID19 handler；确认 context/node/parent/FEP 指针、descriptor `+10c78`、原 FEP192 bytes、3 source records、243 vertices、VTYPE522 与原枪全量 geometry SHA。随后始终只保留一个自有 CPU breakpoint，按分派点→真实 callback entry→返回点切换；结束释放输入和断点，只停止自有进程。

最终采用：

| 采集 | 原入口 | 完整 callback triples | type155 |
|---|---|---:|---:|
| `reset21_v2` | `08b68ce4 → vtable+30` | 21，3组7类 | 3 |
| `key9_v4` | `08b68ad4 → vtable+10` | 9，1组9类 | 1 |

`combined_audit_v3/verification.json` 是最终独立审计。它重读原指令与反汇编、寄存器、三阶段 tick、FEP descriptor、definition、真实虚表及输入数据记录；只容许与原 section offset 精确对应的指针 relocation。输入 record 的有界窗口不当成已恢复的 allocation size。30次回调有真实 class/record/parameter binding，完整标量算术回放只针对4次 type155，不外推其他类。

原 definition 与共享参数块：

| definition | source type | parameter offset | 本次观察 |
|---:|---:|---:|---|
| 0 | 1 | 0 | key、reset |
| 1 | 6 | 20 | key、reset |
| 2 | 23 | 60 | key |
| 3 | 7 | 60 | key、reset |
| 4 | 24 | 80 | key |
| 5 | 16 | 80 | key、reset |
| 6 | 61 | b0 | key、reset |
| 7 | 62 | f0 | reset |
| 8 | 14 | 110 | key |
| 9 | 155 | 110 | key、reset |

数字 offset 用十六进制。`60`、`80`、`110` 三处存在原始别名：不能把这些 definition 各自分配独立状态后覆盖原顺序。type155 仅处理共享块 `+8..+1c` 的六个 float；同块前两个字段由其他原路径维护。

## type155 的真实曲线更新

普通 key callback 为 `08b9a3ec..08b9a514`，回绕 callback 为 `08b9ad1c..08b9aebc`。两者都是已保留完整原码的 scalar MIPS/COP1 路径。

六个状态字段位于参数块 `+8..+1c`，按两个 position/base、两个 velocity、两个 acceleration 解释；原 key 的对应字段位于 record `+10..+24`。普通切换在相同时间点保留当前曲线与旧 key 的差，再叠加新 key；回绕在旧相对时间计算累计值和导数，再针对新相对时间重基。每次乘法/加减均按原顺序独立 F32 舍入。

回绕还对 base 做原始4096区间处理：条件为 `<0` 或 `>=4096`，先加4096，再以 `1/4096` 缩放、`trunc.w.s`、乘回并相减。它不是任意输入下的正值 `fmod`。原 callback 的返回寄存器也不同：reset 写 v0=1，普通 key 函数保持入口 v0；审计按真实指令比较，没有统一强加布尔返回。

独立指令 interpreter 执行固定 module words，重放4次实际 callback，并逐 byte 比较返回后的整个有界参数窗口；六字段外的 bytes 也保持一致。生产 `T3BGEEffectCurve.h/.cpp` 实现 `ChangeOriginalEffectCurve`、`WrapOriginalEffectCurve`。`runtime_curve_v2` 实际编译运行当前源码，4次真实调用的24个 F32 分量全部逐 bit 相同；另8个明确合成的原指令数值样例覆盖小数、不同 keys、非零 acceleration、负值、4096边界及大值，5个非法输入实际拒绝。它们不增加真实动作或动态 key 的覆盖。

`source_curve_bank_v1/source_curve_bank.json` 导出原 definition、共享 offset、7个 reset initializer indices，以及原始的两个 type155 payload：

- initial block `11620` / entry `11674` / payload `117a0`，signed start/end为0/0。
- time-key block `118c0` / entry `1190c` / payload `11a40`，signed start/end为0/2。
- 两个 payload 的六字段都是 `(0,0,32,0,0,0)`，即当前原数据的二维 base、velocity、acceleration。全部4次实际调用的新旧 operand 与这些原始 payload 前40 bytes交叉核对。

这两个 payload 是同一 descriptor 的原资源，不是拟合的高清特效。时间单位仍为原版 source units，秒数转换未确认。

## 时间、UV 与实际命令之间的直接链路

`uv6_v1` 从同一原节点取得6次完整 render invocation。每次按 dispatcher→原 polynomial evaluation→texture binder→GE offset emitter→返回依次采样。完整 type155 renderer、binder `08bbfbc4..08bbfcc8`、emitter `08c00aa8..08c00aec` 与 group renderer 的运行时原码都与固定 module 核对。

原 renderer `08b9a674..08b9a6cc` 用六状态字段和 dispatcher 相对时间计算两个 pixel offsets；它们在 `08b9a71c` 的 f20/f24 与随后 binder 的 f12/f13完全一致。binder 通过实际 texture bank→slot→object→header 读取64×32尺寸，按原 F32 加减循环处理 pixel offsets，除以宽/高，再加 per-group offset。原循环接受恰好等于 width/height 的数值，因此它会得到1.0，不能直接换成 `[0,1)` 的 `fmod`。

| 实际 invocation | 相对时间 | U pixel offset | 最终 U OFFSET |
|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 |
| 1 | 1 | 32 | 0.5 |
| 2 | 0 | 64 | 1 |
| 3 | 1 | 96 | 0.5 |
| 4 | 0 | 128 | 1 |
| 5 | 1 | 160 | 0.5 |

本次 V pixel/normalized offset 和 group offsets均为0。跨回绕累计的 U base 保留，说明只循环播放固定 draw 或把时钟清零后丢弃参数状态会改变原效果。

emitter 用真实 f12/f13 的高24 bits 写出 `4a/4b` 两条命令。审计读取返回后的实际 DL memory，检查相同 DL context、cursor 正好增加8、uncached alias 和两条完整 word，6次共12条全部相同。`uv_audit_v1` 保存逐调用原始输入与实测输出。

生产新增 `EvaluateOriginalEffectCurve`、`BindOriginalEffectUV`。`runtime_uv_v1` 实际执行当前 core，6个真实调用的24个 F32 分量和12个实际命令 words 全部逐 bit 相同；8个明确合成样例与5个非法输入检查通过。完整源码快照、编译参数、exe、输入、reference、输出及 SHA 保留。给现有 GE UV decoder 时应先按原 emitter 打包高24 bits，不能把同一 offset 再应用两次。

这里确认的是**真实 CPU 命令写入**。本次没有另取同一调用的 GE dump 或最终像素；不把 command-write 证据说成新的 GPU 消费验证，也不根据64×32尺寸单独认领 CLUT 内容。

## 失败保留与后续

`reset14_v1` 初次成功采集但 callback 原码窗口为0x180，短于完整 type155 reset函数；最终采用0x200的 `reset21_v2`。`key14_v1`、`key20_v2` 因采集器错误要求4-byte对齐，遇到实际2-byte对齐输入记录失败；已修正普通 byte-window 读取，未改原游戏数据。`key20_v3` 完整记录了9次调用，随后达到 bounded stop 上限，未满足请求20次，保留失败；最终 `key9_v4` 按实际9次窗口成功。旧失败不计入30次最终证据。`combined_audit_v1` 曾错误要求普通 key 返回1，按原指令修正为比较实际 v0；最终 v3 独立通过。

所有7个隔离采集进程均已终止，原文件和资源保护结果见 `source_protection.json`。当前工具另存 `current_tool_snapshots`，launch-time executed JS/runner 分别保留。正式 UE module 仍缺 MSVC/SDK，未重试提权安装；本阶段没有启动 UE、修改 Content 或替换默认 M1。

下一步恢复 type16 颜色路径和 type6/type7 的实际参数语义，连同共享 type23/24/14 的顺序一并追踪。完整 FX 生命周期、其他 FEP branches、原伤害/AI/碰撞、高清美术与正式可玩 M1 仍未完成。
