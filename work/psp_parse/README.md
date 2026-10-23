> GitHub 协作入口：[../../README.md](../../README.md)，当前状态见 [../../docs/CURRENT_STATUS.md](../../docs/CURRENT_STATUS.md)。下文保留各阶段历史记录；本机数据路径不随 Git 发布。

# The 3rd Birthday（ULJM-05798）PSP 资源解析

只读解析 `PSP\The_3rd_birthday_cn_full_v101.iso`，把 `3rd.pkg` 里的 `pack` 容器拆成**网格（OBJ）**和**贴图（PNG）**。

- 原始 ISO、PBP 全程**只读**，未执行、未改动
- 本目录是派生物，约 366 MB
- 资源版权属 Square Enix，仅供个人研究/参照，不要二次分发

---

## 目录

```
work/psp_parse/
├─ README.md                 本文件
├─ docs/解析报告.md          完整技术报告（ISO / PBP / pkg / pack / SEDB / 文本取证）
├─ tools/                    可复用工具
│   ├─ psp_pack.py           pack 容器读取、拆段（list / show / dump）
│   ├─ pack_export.py        顶点池 → OBJ（点云或三角形列表）
│   ├─ pack_tex.py          贴图表 → PNG
│   ├─ pack_bundle.py        一个容器 → 一个目录（网格 + UV + 贴图 + README）
│   ├─ build_blend.py        容器 → .blend（顶点色 + UV + 材质 + 灯光 + 相机）
│   ├─ bind_assist.py        .blend（每段一个对象 + 贴图材质槽，手绑用）
│   ├─ render_obj.py         OBJ → PNG 预览（自带软件光栅化，无需 GPU）
│   ├─ ppst_extract.js       PPSSPP 存档 → 解压后的 RAM 大块（Node，用系统 zstd）
│   └─ dump_hunt.py          任意二进制里找 PSP 顶点数组 → OBJ（RAM 转储用）
├─ out/                      成品
│   ├─ ASSET_LIBRARY.md      素材库清单（尺寸/层高/贴图数，按面数排序）
│   ├─ assets.csv            逐容器数据（91 行）
│   ├─ blend/                .blend（直接双击用 Blender 打开）
│   │   ├─ packs_sample.blend   4 个容器，网格排列，带顶点色
│   │   ├─ packs_all.blend      91 个容器全量
│   │   ├─ room_inside.blend    单房间、相机在屋内的第一人称视角
│   │   ├─ room_split.blend     单房间按 floor / wall / prop / slab 拆开
│   │   ├─ bind_444e5000.blend  37 对象 + 21 贴图材质槽（手绑）
│   │   └─ auto_444e5000.blend  顶点色 × 灰阶细节图（自动近似）
│   ├─ preview/              PNG 预览
│   │   ├─ sheet.png            91 个容器的缩略图总览（带容器偏移标注）
│   │   ├─ v_*.png              小容器的四视图
│   │   └─ *.png                各 .blend 的渲染
│   ├─ meshes/               91 个 OBJ，125 MB（index.csv 有逐包统计）
│   ├─ textures/             6,195 张 PNG，68 MB
│   ├─ runs/                 10,291 个网格游程索引 + 12 个候选 OBJ
│   └─ bundle/               2 个样品包（网格+贴图+说明）
├─ raw/                      原始提取物
│   ├─ 3rd.pkg               包头 1 MB（不是全量）
│   ├─ packs/                4 个 pack 样本 + pack_sections.csv（1,663 段清单）
│   ├─ sedb/                 245 个 SEDB，53 MB
│   ├─ *.PNG / *.AT3 / *.BIN / *.SFO   镜像成员
│   └─ pkg_*.png / *.psmf     从 pkg 里抠出来的资源样本
└─ archive/                  70 个一次性探针脚本与日志，保留备查
```

`archive/` 里的脚本写死了旧路径（`extract/…`），保留原样，仅作过程记录，**不保证还能跑**。

---

## 快速上手

### 只想看成品 → 双击 .blend

```
work/psp_parse/out/blend/packs_sample.blend   4 个容器，网格排列
work/psp_parse/out/blend/packs_all.blend      91 个容器全量
```

打开就能看到带**顶点色**的模型，场景里已经放了太阳光、环境光和相机。
每个容器是一个对象（`pack_0x...`），按网格摆开互不重叠。

重新生成：

```bash
blender -b --factory-startup -P work/psp_parse/tools/build_blend.py -- \
        --out work/psp_parse/out/blend/packs_sample.blend \
        --packs 0x444e5000,0x49fb1000,0x4c199000,0x4c3ca800

blender -b --factory-startup -P work/psp_parse/tools/build_blend.py -- \
        --out work/psp_parse/out/blend/packs_all.blend --all
```

### 命令行工具

```bash
# 1) 看所有容器（436 个，含类型、段数、跨度）
python work/psp_parse/tools/psp_pack.py list

# 2) 看某个容器的段表
python work/psp_parse/tools/psp_pack.py show 0x444e5000

# 3) 把某个容器拆成段文件
python work/psp_parse/tools/psp_pack.py dump 0x444e5000 work/psp_parse/raw/tmp

# 4) 导出网格（--points 点云 / 默认三角形列表；--uv 带 UV）
python work/psp_parse/tools/pack_export.py 0x444e5000 /tmp/mesh --uv

# 5) 导出贴图
python work/psp_parse/tools/pack_tex.py 0x444e5000 /tmp/tex

# 6) 一步到位：网格 + UV + 贴图 + 说明
python work/psp_parse/tools/pack_bundle.py 0x444e5000 0x49fb1000 --out work/psp_parse/out/bundle

# 全量
python work/psp_parse/tools/pack_export.py all work/psp_parse/out/meshes
python work/psp_parse/tools/pack_tex.py    all work/psp_parse/out/textures
```

---

## 已解格式速查

### ISO / PBP

- UMD ISO9660：2048 B/扇区，PVD 在第 16 扇区，标识 `CD001`
- 卷标 `THE_3RD`，DISC_ID `ULJM05798|7EC2A2BA15D0F3AB|0001|G`，DISC_VERSION 1.01，FW 6.31
- `SYSDIR/EBOOT.BIN` 是 Kirk 加密的 `~PSP`；原始文件不直接暴露 ELF，但可在 PPSSPP v1.20.4 运行后从 guest RAM 提取已解密模块，再用 map + Capstone 做地址对齐的静态反汇编。当前矩阵路径报告见 `out/AYA_EBOOT_MATRIX_ANALYSIS.md`。

### 3rd.pkg（1,344,292,864 B）

顶层是若干 **0x800 对齐**、自带长度的块，靠「当前块尾对齐后等于下一块起点」当判据：

| 魔数 | 内容 | 数量 / 体积 |
|---|---|---|
| `PSMF` | 视频（长度是大端 u32 @ +0x0C） | 42 个，1,088,458,752 B（81%） |
| `SEDBSSCF` | 场景实体表 v3（LE32 长度 @ +0x10） | 245 个，53 MB |
| `pack` | 网格/贴图容器 | 436 个，198.6 MB |
| `\x89PNG` / `RIFF` | 图片 / AT3 音频 | 12 / 624 |

### pack 容器

```
+0x00  char[4]  "pack"
+0x04  u32      type / version（实测 2 / 4 / 7 / 8 / 11 / 12 / 34）
+0x08  N × (u32 size, u32 offset)
        N = (首段 offset − 8) / 8，首段 offset 就是头长
        段与段首尾相接（gap ≤ 0x100），(0,0) 是空槽
```

435/436 个容器通过连续性校验。**只有 type 8 含几何**（91 个，135.9 MB）。

### 顶点池（type 8 容器里最大的那一段）

段头：

```
+0x00 u32 0
+0x04 u32 0x3002     顶点格式字
+0x0C u16 网格数     +0x14 u16 材质数
+0x20 u32 贴图表偏移
```

顶点记录 **20 字节**，靠 `+0x0A` 处的 `0xCCCC` 恒定填充定位（样本里 6,911 个间距全部正好 20）：

```
+0x00  4 × u8   RGBA / 烘焙色（A 基本 0xFF）
+0x04  3 × s16  位置定点：米 = raw / 32768 × 3.125
+0x0A  u16      0xCCCC 恒定填充  ← 记录签名
+0x0C  f32      U
+0x10  f32      V
```

顶点按三角形拆开（`顶点数 = 3 × 三角形数`），**没有索引缓冲**，所以直接按三角形列表写 OBJ 就是完整网格。

### 贴图表

表地址 = 段头 `+0x20`，每 16 字节一条：

```
+0x00 u16 宽, u16 高
+0x04 u32 bpp（4 或 8）
+0x08 u32 CLUT 偏移（4bpp 是 16 色 × RGBA）
+0x0C u32 像素偏移（w*h*bpp/8 字节）
```

CLUT 与像素首尾相接，可互相印证（`CLUT + 0x40 == 像素起点`，`像素终点 == 下一条 CLUT`）。

### FEP（type-12，只有材质/动画）

`FEP` + 版本 1/4/5；`+0x14` 块大小、`+0x48` 对象数（样例 157）。对象记录 **200 字节**，
内容是材质/灯光：`+0x30` 的 `1.0,1.0,1.0`、`+0x40` 的 `100.0×3`、`+0x90` 的 `300/500`、
`+0xC0` 指向下一个对象的偏移。段里还有 `ANM\0` + `"0.00"` 的动画块。

**顶点流仍未定位**：有索引缓冲（全 u16 < 4096 的区，max 3593/3854/3855），但按索引数反推的
顶点数组（stride 6–32、s16/f32、slack 0–0x200、尺度无关判据）全部 0 命中。

### 角色网格：包里没有

- pkg 的 1.34 GB 已全部对账：PNG(1) + 杂包(6) + SEDB(245, 53 MB) + 视频(42, 1.04 GB) + 几何包(430, 198 MB)
- 10,291 个 mesh run 里没有人体尺寸 + 肤色的主体（576 个"肤色" run 全是 0.01–0.44 m 的小道具）
- 所以角色要么在加密的 EBOOT 里，要么只能从运行时内存里取 —— 见下

### 从运行时内存取角色（管道已验证，卡在模拟器）

不用存档也能拿：**直接读 PPSSPP 进程的 guest RAM**（32 MB × 3 份镜像），
再用 `dump_hunt.py` 在里面找顶点数组。管道已实跑通过 —— 读到的确实是 PSP 内存
（能搜到 `ULJM05798`、`SEDBSSCF`、`pack` 等游戏内数据）。

```bash
# 1) 从活着的 PPSSPP 进程里抓 guest RAM（会写出若干 .bin，32 MB 的那几个就是内存镜像）
powershell -ExecutionPolicy Bypass -File work/psp_parse/tools/read_psp_ram.ps1 -Out work/psp_parse/raw/ram.bin

# 2) 扫顶点数组
python work/psp_parse/tools/dump_hunt.py work/psp_parse/raw/ram.bin.5.bin work/psp_parse/out/dump
python work/psp_parse/archive/ram_f32.py work/psp_parse/raw/ram.bin.5.bin work/psp_parse/out/dump
```

配套工具（都在 `tools/`）：

| 工具 | 作用 |
|---|---|
| `read_psp_ram.ps1` | 枚举 PPSSPP 进程内存区，把 ≥16 MB 的块整块 dump 出来 |
| `ppst_extract.js` | 备用：`.ppst` 存档 → 解压后的 RAM（Node 24 自带 zstd） |
| `dump_hunt.py` | 在任意二进制里找顶点数组（s16/f32 × stride 12–48），导 OBJ |
| `psp_keys.ps1` | 用 PostMessage 往 PPSSPP 送按键（**不需要窗口焦点**） |
| `ocr_psp.ps1` / `ocr_psp.py` | 用 Windows OCR 读 PPSSPP 的 F12 截图，当"眼睛"用 |
| `drive_game.ps1` | 组合上面两个：按键 → 截图 → OCR，逐步推进 |

当前使用的 PPSSPP v1.20.4 可通过 WebSocket debugger 连续导出 GE frame dump，并注入按钮状态；新增姿态采样脚本见 `tools/capture_ge_pose_variants.js`。

### 44-bone source record ↔ GE draw 交叉映射

**2026-10-20 更正：以 `out/AYA_SLOT0_SKELETON_METADATA.md` 和 `out/AYA_EXPLICIT_PALETTE_GE_VERIFICATION.md` 为准。** 已从原版 metadata 恢复 44 根骨骼的完整父子索引，并在旧 RAM 与用户第一个即时存档的独立运行中验证全部 44 个 runtime parent pointers。106 个 draw packet 的 3,456 条顶点记录明确引用 35 根骨骼；另外 9 根在当前 mesh 中没有直接权重，其中 4 根是带权重骨骼的祖先。无需假定必须通过受击/倒地才能“补齐”这 9 根。

旧 GE 工具把 VERTICES 后的整个 REGISTERS 块当成当前 draw 快照，存在时序错误：块内 PRIM 后的命令可能更新下一次 draw。现用 `tools/replay_ge_draws.py` 按 PRIM 重放；两组共 36 帧的 106 个原版 packet 全部通过几何字节核对，9,252 次有效 palette/source 引用完全一致。旧的具体 source→身体部位命名、draw ordinal 和插槽绑定需要重新核对，不应直接作为 M1 的校准依据。

下面的历史统计保留用于追踪，不能替代以上新证据。材质侧的 draw/resource 数量包含候选和重复资源关系，尚不代表逐 draw 的唯一原版 CLUT 绑定。

`tools/map_aya_source_bones.py` 会把 `AYA_BONE_GE_PAIRS` 的 24 帧、每帧全部 Aya weighted draw 与 `0x08b5251c` 写入的 44 个 source record 做 float24 RMSE 匹配。当前样本得到 **624 个逐帧匹配实例、26 个稳定 source→GE draw 映射，全部 RMSE=0**；右手为 source `36` / GE slot `12` / draw `1037`。尚未在这组射击姿态中出现的 source index 保留为未覆盖，不能据此推断不存在。

结果：`out/AYA_SOURCE_BONE_GE_DRAW_MAP.json`、`out/AYA_SOURCE_BONE_GE_DRAW_MAP.md`。

历史版本加入 idle、strafe-left、strafe-right 和 60 帧 idle-long 的 source/GE 配对，曾报告 35/44 source indices 和 3,916 条 source/slot/draw 组合。draw ordinal 仅对本次 capture 有意义，且该报告受上述 REGISTERS 时序错误影响；“其余 9 根需要受击/倒地触发”的旧解释已被显式 metadata 推翻。

材质侧新增 `out/AYA_RUNTIME_CLUT_BINDINGS_ALL.md`：4 组 PPSSPP dump 共 81,110 个 draw observations、212 个 CLUT/TEXTURE0 runtime signatures；其中 81 个 runtime payload 已精确匹配到 type-8 pack 的 6,195 条 texture record。FEP 全量清点见 `out/FEP_SKINNING_INVENTORY.md`，覆盖 154 块并保留 index/weight/name 候选偏移。

进一步按同一 draw 的 TEXTURE0 反向解析 CLUT：`out/RUNTIME_MATERIAL_RESOLUTION.md` 已把 126,112 条 draw/resource 关系落到 296 个具体 pack texture（76 个 runtime CLUT payload），剩余 19 个 TEXTURE0 signature 仍未落地。

---

## 产出与数字

| 项目 | 数量 | 体积 |
|---|---|---|
| pack 容器 | 436 个 / 1,663 段 | 198.6 MB |
| 可导出几何容器 | 91 个（全部 type 8） | 135.9 MB |
| 顶点 / 三角形 | 4,120,816 / 1,324,784 | OBJ 125 MB |
| 贴图 | 6,195 张（4bpp 调色板） | PNG 68 MB |
| 网格游程（run） | 10,291 个 | 索引 0.6 MB |
| 视频 | 42 个 | 1,088,458,752 B |

---

## 未解 / 已知边界

1. **材质 ↔ 贴图绑定**：三条线索都不成立（段头 40 字节链表、游程后 12/64 字节尾记录、`aa 2a` 标记）。bundle 里写的是「assign by eye」，没有编假映射。
2. **type-12 / FEP 顶点流**：已知有索引、有蒙皮，按「索引最大值 = 顶点数」反推顶点数组（stride 6–32、s16/f32、slack 0–0x200、尺度无关判据）**0 命中**；SoA 假设无区分度。
3. **角色不在 pack 里**（已排查三条线）：10,291 个游程里最大只有 6 m 的房间件；12 个「人体比例」候选的顶点色是木棕/纯白/近黑（木箱、灯、机器）。角色网格仍未找到。
4. **贴图像素是否 PSP swizzle** 未定：线性与解混淆两种排布的相邻像素差几乎一样，导入 Blender 看一眼即可判定。
5. **文本**：pkg 里没有任何明文（7 种编码、XOR、zlib 全负），汉化文本只可能在加密 EBOOT 里 —— 详见报告 §6。

---

## 重新生成全部产物

```bash
python work/psp_parse/tools/pack_export.py all work/psp_parse/out/meshes
python work/psp_parse/tools/pack_tex.py    all work/psp_parse/out/textures
```

两步都需要读 1.34 GB 的 `3rd.pkg`，全量约 3–5 分钟；`pack_export.py all` 只扫一次镜像。
