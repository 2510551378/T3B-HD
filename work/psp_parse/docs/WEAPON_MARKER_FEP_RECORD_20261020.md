# state+0x198 的原版 FEP record 局部关联

本分析只读已知单个 FEP section、选定模块和54组已保存 state capture，没有重扫整个 ISO、连接 PPSSPP 或修改现有采样。原始 bytes、SHA 和结构化记录在 `out/WEAPON_MARKER_FEP_RECORD_20261020/record_analysis.json` 及同目录 sidecar。具体 FX/socket 的 `semanticName=null`。

## 已保存字节对应的局部表链

Parent 的全 ISO exact search 将64-byte资源前缀唯一匹配至 ISO `0x56bfc4b0`。其 pack 为 type12、base `0x56bf7000`，section1 为 `FEP\x07`、base `0x56bf7bc0`、size `0xbe240`。本分析仅 seek/read 这一已知 section；其 SHA256 为 `97443c71b1c1d644f323c6ff611afb740329cfe11a47a711f39dc59de06ec802`。

以下都是 FEP-relative offset，未将原版相对值假装成 runtime 指针：

| 层级 | 位置和 raw 值 |
|---|---|
| header 的 table0 | u16(+0x1c)=93，u32(+0x28)=0x50 |
| table0[4] | slot0x60 → descriptor0xab8 |
| descriptor0xab8 | 12 bytes，u32=[0x00286800,0x00010004,0x000048e0] |
| descriptor 的 table1 index/count | u16(+4)=4；u16(+6)=1 |
| descriptor pointer list | u32(+8)=0x48e0；list[0]=0x48f0 |
| 选中 subrecord | 0x48f0，首 word 同为0x00286800 |
| header 的 table1 | u16(+0x1e)=93，u32(+0x2c)=0x1c4 |
| table1[4] | slot0x1d4 → 0xfb4 |

邻接 table0[5] 的 pointer list 从0x49b0开始，因此目标 record 到下一 list 的区间为0xc0，已保存这整个区间，SHA256 `2652c7c76cb44411ebf29fe24ff71b20060f127ed4547447f172dd3da79bef20`。这只是该 record 的局部候选 extent，不是已证明所有 FEP record 都用0xc0 stride。

record+0x10/+0x20 各为 (0,-0,-0,0)，+0x30 为 (1,1,1,0)，+0x40 为 (100,100,100,0)，+0xb0 为 (1,1,1,1)。保留 raw F32 与 signed-zero bit pattern；不把这些默认值直接命名为粒子尺寸、颜色或发射方向。

## 与实际 state 的三字段交叉证据

对 square6、aimfire24、strafefire24 的54组 row，重新核对 entry/helper-return/generic-return/state-return 四阶段 raw state sidecar 的 SHA，并读取同三个字段，结果全部一致：

| state 字段 | 实测值 | 与原 section 的对应关系 |
|---|---:|---|
| +0x190 | `08d4d280` | 候选 FEP base 本身，由 state 实际声明 |
| +0x194 | `08d4e234` | base+0xfb4，即 table1[4] |
| +0x198 | `08d51b70` | base+0x48f0，即 table0[4]/subrecord0 |

因此候选 base 既由已知 record 地址差得到，又直接存在 state+0x190；+0x194 提供第二个独立 offset 对齐。这里没有读取 runtime header/relocated pointer chain，尚不能把三字段和前缀匹配外推为完整 loaded FEP 身份验证。

## 有界静态初始化与选择路径

原模块 SHA256：`b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f`。以下每条 machine word 已与原模块核对，完整有界函数 byte sidecar 已保存。

`08b639f0`（size0x77c）初始化 state：

- `08b63a14:8cb10014`：s1=[入口a1+0x14]，作为源 header/base。
- `08b63a24:00e0b825`：s7=入口a3，保留选中 subrecord 地址。
- `08b63a74:8e24002c`、`08b63a78:00122880`、`08b63a80:00852021`、`08b63a88:8c950000`：s5=[header.table1 + 4×入口a2]。
- `08b63f34:ae640190`：将保存的 s1 写 state+0x190。
- `08b63f38:ae750194`：写 s5 至 state+0x194。
- `08b63f3c:ae770198`：写 s7 至 state+0x198。

`08b6416c` 的普通 table0 选择分支：

- `08b642d8:94a9001c` 读取 header 的 count；`08b642f4:8ca50028` 读取 table0。
- `08b642f8:8caa0000` 取得 descriptor；按其首 word 的 `(word&0x1fc00)>>10` 与请求值比较。
- `08b64310:95460006` 读取 descriptor subrecord count；`08b64324:8d470008` 取得 pointer list；`08b64328:8ce80000` 取得选中 subrecord。
- 对 subrecord 首 word 使用 low9 bits 与请求值比较；本目标 low9=0。
- `08b64374:01003825` 设置 a3=选中 subrecord；`08b64378:95460004` 设置 a2=descriptor table1 index；`08b64384:0e2d8e7c` 调上述初始化函数。

这说明 descriptor 的 count/index 不是凭表形猜测；静态选择器确实按这些字段读取。当前 capture 发生在后续 helper/state update，没有观测这次初始化调用的实际入参，因此不把静态可达路径声称为已经动态命中。

## consumer 与尚未恢复的语义

实际 outerRA=`08b69f00` 对应函数 `08b69dbc` 的更新循环：从 context+0x6c 取 state 链，`08b69e84` 读取 state+0x198，`08b69e8c..a4` 用 record首word的高4位构造 context+0x24 的过滤位；本 record 高4位为0。`08b69ef8:0e2d8d3b` 调 parent `08b634ec`，delay a1=state，返回08b69f00。state 链 next 指针为 +0x124，与 skeleton record+0x124 不能混为同一结构。

初始化先将 state+0x14c/0x154 清零。仅当 record byte+8为1或2且+0xc非零时，才从该外部配置读取 selector/flags；这个原 ISO record byte+8=0、+0xc=0。实测 state 的 source selector 为1，故不能把原 record 内某个值直接命名为 source1/muzzle 绑定；还需追踪后续配置写入或实际调用参数。静态函数随后调用的 `08b627dc` 可能应用调用者配置，但本报告没有继续追踪或给它赋名。

已经建立的是：原版 table0/group/subrecord 选择结构与运行时 state 的源记录三字段对应，以及该记录参与 helper 后最终 state 的生成。尚缺 runtime FEP header/relocation 指纹、后续 renderer/FX consumer 的具体资源引用；因此仍不命名 muzzle flash、弹道发射器或常驻 attachment。
