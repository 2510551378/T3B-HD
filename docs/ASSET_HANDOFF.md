# 本地资产交接

Git 仓库仅承载源码与文档。为了运行当前工程，同事需通过双方私下约定的位置取得以下目录，并保持相对路径：

| 目录 | 用途 |
| --- | --- |
| `work/t3b_hd/assets/` | C 原型的 source skins、动作片段、原材质、场景及可选 4× 重采样 |
| `work/t3b_unreal/Content/SourceData/` | UE 自定义 source bundle、贴图与 `manifest.json` |
| `work/t3b_unreal/Content/T3B/` | 已保存的地图、材质和 Texture2D 等 UE 包 |

本次整理已生成 [runtime_asset_manifest.json](runtime_asset_manifest.json)，逐项记录上述目录的相对路径、文件长度与 SHA-256。它不是资产下载地址，也不包含资源内容。

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
