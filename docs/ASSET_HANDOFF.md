# 本地资产交接

Git 仓库仅承载源码与文档。为了运行当前工程，同事需通过双方私下约定的位置取得以下目录，并保持相对路径：

| 目录 | 用途 |
| --- | --- |
| `work/t3b_hd/assets/` | C 原型的 source skins、动作片段、原材质、场景及可选 4× 重采样 |
| `work/t3b_unreal/Content/SourceData/` | UE 自定义 source bundle、贴图与 `manifest.json` |
| `work/t3b_unreal/Content/T3B/` | 已保存的地图、材质和 Texture2D 等 UE 包 |

本次整理已生成 [runtime_asset_manifest.json](runtime_asset_manifest.json)，逐项记录上述目录的相对路径、文件长度与 SHA-256。它不是资产下载地址，也不包含资源内容。

## 可安装的运行包

维护者本地已提供 `dist/T3B-HD-runtime-assets-20261023-v1.zip` 与同名 `.zip.sha256`。通过双方约定的私有位置传送这两个文件；压缩包不上传到公开 GitHub。

同事先更新源码，在仓库根目录执行（用 sidecar 中的实际 SHA-256 替换占位符）：

```powershell
python -X utf8 scripts/runtime_bundle.py install 'C:\Transfer\T3B-HD-runtime-assets-20261023-v1.zip' --sha256 <SHA256>
python -X utf8 scripts/asset_manifest.py verify
.\scripts\run_m1.ps1
```

运行包包含上述 655 个资产，以及 C 原型 exe、SDL2.dll/许可证、已编译的自有 UE Editor module；不含引擎、SDK、ISO、存档和采集 dump。安装会先逐项验证，再写入仓库相对路径；相同文件跳过，发现已修改文件默认拒绝覆盖。备份后可显式加 `--replace-existing`。

UE 使用本机已验证的 5.8.4 / CL 58902052 / module BuildId `55116800`：

```powershell
.\scripts\run_unreal.ps1 -EngineRoot 'C:\Program Files\Epic Games\UE_5.8'
# 直接进入 source replay：
.\scripts\run_unreal.ps1 -EngineRoot 'C:\Program Files\Epic Games\UE_5.8' -Game
```

启动器检查 UE BuildId、module 哈希和对应源文件。相同引擎可直接加载预编译 module；引擎不同或代码变动时加 `-Build`，这需要 MSVC/SDK。首次启动可能编译 shader；运行包不是 cooked Unreal 独立游戏，画面与 gameplay 的限制见 `CURRENT_STATUS.md`。

维护者重新打包时，必须显式指定已验证的 build copy、引擎与 SDL 许可证：

```powershell
python -X utf8 scripts/runtime_bundle.py pack --output 'dist/T3B-HD-runtime-assets-NEW.zip' --ue-binary-root 'C:\T3BRemakeBuild_20261021_markerprobe' --engine-root 'C:\Program Files\Epic Games\UE_5.8' --sdl-license 'work/third_party_dl/sdl2/SDL2-2.32.10/LICENSE.txt'
```

打包器核对全部原资产身份、build copy 的源码/shader 与 UE BuildId，写入完整 payload 清单及外部 ZIP checksum；不覆盖已有版本。`verify ZIP --sha256 ...` 可只读检查压缩包。

同步到 clone 根目录后运行：

```powershell
python -X utf8 scripts/asset_manifest.py verify
```

该命令只读核验，不复制、不下载、不覆盖。缺失或 hash 不同会返回失败，未列入清单的文件不被当作相同资产。清单的边界是首次运行资产，不包括完整解析证据。

维护者需要为一个**明确的新资产版本**更新身份快照时运行：

```powershell
python -X utf8 scripts/asset_manifest.py snapshot
```

先审查资产变化，再提交清单差异；不为“让检查通过”重写旧 hash。脚本拒绝跟随符号链接和 Windows reparse points。

## 进一步恢复原版与证据

完整解析仍需要各开发者自行准备的原版 ISO，以及按任务交接的 `work/psp_parse/raw/`、`out/`、`map.ppmap*` 等。本仓库没有它们。旧报告所引用的绝对路径、CPU sidecar、GE dump、截图和逐位比较输出应从本地归档取得；不要假设运行一个导出命令就能重建所有阶段。

PPSSPP 采集时先复制存档与配置，在独立 emulator 目录启动；某些旧脚本会发送按键、继续执行 guest 或写输出。`trace_*_selftest.js` 使用模拟环境，不能当成真实运行采集。

原资产的使用和私下交接由参与者自行确认权限；不把这些文件提交到此仓库、Git LFS、GitHub Release 或 Actions artifact。第三方程序与 SDL/UE SDK 单独安装。
