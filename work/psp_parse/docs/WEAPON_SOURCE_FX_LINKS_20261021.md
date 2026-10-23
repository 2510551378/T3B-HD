# 原版武器 source1/source2 与 FX、线段的交叉证据

本轮只读已有 ULJM05798 模块、CPU sidecars 与12个 GE 捕获，没有启动 PPSSPP、改写 ISO/存档或替换正式 M1 枪口绑定。

## 原始 marker 定义与运行时接入

`analyze_weapon_fx_source_links.py` 重新执行旧 CPU emission/marker 独立审计，核对24个 dense helper-return snapshots。source0+0x80、source1+0x40、source2+0x40 共192 bytes 在24个快照中逐字节一致，parent pointers 为 `[null, source0, source0]`，source0+0x40 为 identity。三条都是原始矩阵，没有拟合 socket。原两条 marker 仍只称 source1/source2，具体语义为 null。

`out/WEAPON_SOURCE_FX_LINKS_20261021/recovery_v1/source_markers.bin` 为208-byte T3BWMK1：magic8、u32 count2、原枪单顶点权重 F32 `32767/32768`、原始 source0+80/source1+40/source2+40 三个16-F32矩阵。原始 bytes 及全部来源 SHA 保存于同目录 `verification.json`。source0+80 的12个分量取高24位，与全部12个 GE 枪 draw 的 BONE payload 一致；这是该枪绑定关系的进一步证据，不是其它武器通用格式证明。

新增 `T3BGEWeaponMarkers.h/.cpp` 接入实际生产 C++ core，`ge_weapon_marker_probe.cpp` 调用同一个 `T3BGESeries` reader 和 marker evaluator。最终路径直接组合原始 source1/source2 local matrix 与当前 GE WORLD，符合已恢复的原 helper `WORLD × source40` 关系；BONE 只检查该枪的 bind 身份，不绕经量化骨矩阵求逆。WORLD 仍为 GE F24，输出也未宣称逐 bit 等于同帧完整 CPU matrix。

`runtime_v2/verification.json`：实际 g++ 编译并执行，12个捕获、24条 marker pose，矩阵及单位 +Z 与独立 NumPy 原始 bytes 计算的最大 F64 差为 `1.1102230246251565e-16`，限值 `1e-9`。5个坏输入（截断、尾随 bytes、magic、weight、root bind）均被实际 executable 拒绝。执行源码、输入、binary、命令与输出 SHA 已保存。这里是独立原生 core 执行，未执行 UE C++ module，也未替换默认 M1。

早期 `runtime_v1` 使用 marker→raw mesh→量化 BONE 的绕行路径，通过后发现可直接采用原 helper 公式，故简化成 v2。v1 的 executable/report 与执行源码副本保留。`recovery_v1` 内 `reconstructed_marker_frames` 同属该早期诊断路径；最终姿态以 runtime_v2 实际输出为准。

## 原 FX 偏移与几何关联

旧6组真实 emission snapshots 中，type152/资源ID15/record+2b58 与 type155/ID18/record+2690 的原 input translation 是 `(0,-0,5)`；type155/ID19/record+26a8 是 `(0,-0,7)`。这些是原 marker 局部 PSP 单位，不是厘米，也不是 normalized 枪 mesh 单位。

source1 +Z 对应枪 raw local 的 −X。用未拟合的 source1 与原 `+5`，在加权枪 mesh 坐标得到 `[-1.0843449784, 0, 0.1264725663]`。与样本1/2/11的14/15顶点 FX 原点，距离分别为0.00125033、0.00063736、0.00228895 raw local units。这里未把误差调为零，或把特效原点替代 gameplay 射线起点。

从原 CPU 发射调用保存的 vertices 重读比较：ID18的14顶点完整 bytes 在12个 GE 捕获中只匹配 sample1/record1246；ID19的4顶点 bytes 只匹配 sample1/record1252。ID15的通用 quad 匹配36个 draw，说明仅凭相同几何不能定位具体 FX。上述 CPU/GE 对应项的完整 VIEW packet 均不同，故是跨采集的几何关联，不能宣称同一次调用、同帧或已命名 muzzle。

`check_weapon_fx_quantization_intervals.py` 不拟合参数，枚举每个 GE F24 输入所允许的低8位 F32 区间，按 separate rounded F32 multiply/add 传播 `source1 → WORLD → +5 → VIEW`。6条14/15顶点观察（只有3个独立原点）的三个 VIEW translation 分量区间均与观察区间相交；对同一簇改用0或7，全部不相交。见 `intervals_v1/verification.json`。这是量化区间相容性证据：重复矩阵元素存在相关性，分量区间相交不能证明联合解或 emitter identity，VFPU prefix/JIT 范围也未扩张。

## 原版线段

全部12捕获仅 sample3有21条、sample4有17条 PRIM2。38条都是 VTYPE19c、两顶点、F32 position、RGBA8888，无 UV；WORLD 一致，VIEW/PROJ/主 framebuffer 与 Aya 相同。已保存每条原始32 bytes、全部 register/matrix、世界→当前枪局部转换和方向。

最近端点和最近有限线段到 FX 候选点的距离都为 `0.5317989246` raw local units，不重合。不能把这些线段直接当枪口起点；也不能因此排除其为早先发射、已运动的粒子。用途仍未知。

## 剩余验证

下一步应在同一调用/帧取得 CPU 完整 WORLD、source1/state+60、FX handler 实际 VIEW/geometry，并与 GE 消费关联。当前已有原始 marker 定义、原始 +5/+7 配置、跨采集几何与量化区间证据；仍没有同帧 CPU/GE emitter identity、原版弹道/命中起点或 authored FX clock。正式 UE build、画面和可玩战斗验收继续待完成。

本次工具链安装 run `c793438269084fbd9e286606ddecd93a` 的 exec session17080 已真实 exit1；Windows 提权错误为“操作已被用户取消”，安装器没有启动。与原授权区分，不能把 pending snapshot 或授权当安装成功，不自动重复提权。
