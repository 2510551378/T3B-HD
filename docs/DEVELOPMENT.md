# 开发环境与检查

推荐把仓库 clone 到英文短路径，例如 `C:\src\T3B-HD`，以减少 Windows/UE 对中文长路径的兼容问题。所有命令从仓库根目录运行。

## 1. 纯源码检查

Python 3.10+、C++17 `g++`（本机原有 Strawberry MinGW 可用）：

```powershell
python -X utf8 scripts/check_source.py
```

无需游戏数据或额外 Python 包。输出在忽略的 `build/source_check/`，执行 57 项 source-data、29 项动作兼容性/连续循环、41 项碰撞 tests，共 127 项。GitHub Actions 的 Linux 结果不替代 Windows/UE 验证。

分析工具按需使用隔离环境：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`unreal` 由 UE Editor 的 Python plugin 提供，`bpy/bmesh` 由 Blender 提供；不要从 pip 安装同名包替代。JS 采集工具使用 Node.js 的全局 `WebSocket`，需支持该 API 的版本。某些旧脚本有本机绝对路径，执行前检查 CLI/环境变量和默认输出目录。

## 2. 同步资产

v4 运行包将发布至 [Release](https://github.com/2510551378/T3B-HD/releases/tag/runtime-assets-20261023-v4)，发布后按 [ASSET_HANDOFF.md](ASSET_HANDOFF.md) 安装。`Content`、C 原型 `assets`、原版输入不在 Git 源码树中；clone 后需先安装匹配的运行包。不要用旧 staging 脚本覆盖包含新增字段的 manifest。

## 3. C / SDL2 对照原型

安装 Windows x64 GCC 和 SDL2 2.32.10 的 MinGW 开发包。独立下载 SDL，`SDL2Root` 指向包含 `include/SDL2`、`lib`、`bin/SDL2.dll` 的 `x86_64-w64-mingw32` 目录：

```powershell
.\scripts\build_m1.ps1 -SDL2Root 'C:\deps\SDL2-2.32.10\x86_64-w64-mingw32'
Push-Location work\t3b_hd
try {
    .\t3b_hd.exe --test-source-spawn
    .\t3b_hd.exe --test-source-clips
    .\run_m1_hd_sampling.ps1 -TestApproachFire
} finally { Pop-Location }
```

这些运行需要先安装运行包，测试退出码和日志应分别保存；`approach_fire` 只验证该片段选择/同步，不能要求它覆盖全部战斗状态。交互启动直接运行 `t3b_hd.exe`。旧 Makefile 保留，但默认 SDL 路径是本机历史布局。

## 4. UE 5.8

本机曾使用 UE 5.8.4、MSVC 14.44、Windows SDK 10.0.22621.0。Editor 的 SwarmInterface 还需 .NET Framework 4.8 SDK（仅安装 runtime 不够）。这些组件由开发者自行安装，本仓库脚本不安装系统软件。

```powershell
.\work\t3b_unreal\Tools\check_environment.ps1 -EngineRoot 'C:\Program Files\Epic Games\UE_5.8'
.\work\t3b_unreal\Tools\build_unreal.ps1 -EngineRoot 'C:\Program Files\Epic Games\UE_5.8' -Target Editor
```

资产交接完成、Editor target 构建成功后，用 UnrealEditor 打开 `work/t3b_unreal/T3BRemake.uproject`。默认地图为 `M1_SourceReplay`，Play 启动战斗 Pawn / HUD / Director。也可从仓库根目录直接启动：

```powershell
.\scripts\run_unreal.ps1 -EngineRoot 'C:\Program Files\Epic Games\UE_5.8' -Game
# 原 source replay 诊断，不创建战斗 Director：
.\scripts\run_unreal.ps1 -EngineRoot 'C:\Program Files\Epic Games\UE_5.8' -Game -ReplayOnly
```

默认 D3D11；预编译模块要求 UE 5.8.4 / CL 58902052 / BuildId `55116800` 与对应源文件哈希一致。引擎或源码变化后加 `-Build`。运行方式是 Editor-hosted，尚未提供 cooked 独立 exe。

WASD 移动、Shift 跑、Mouse View、RMB / Tab 锁定、LMB 连射、R 装填、E Overdive、Backspace 重启。Esc 释放鼠标并停止输入，单击重新捕获。准星对应实际枪管射线；Mouse pitch 只改变镜头。

在 `-ReplayOnly` 模式用 `T3B.Replay.Probe` 输出 `Saved/SourceReplay/`，再运行 `Tools/verify_unreal_replay.py`。`T3B.Replay.MotionProbe` 与 `Tools/verify_m1_motion.py` 检查同步动作；精确命令和战斗验收见 [UE_M1_V4.md](UE_M1_V4.md)。本机最终模块的 NullRHI / D3D11 严格战斗检查均 14 项通过，D3D11 战斗流程及外侧 Overdive 镜头复验通过；v4 包交付复验仍在进行。

Cook 示例（尚未验收，不保证当前成功）：

```powershell
$engineRoot = 'C:\Program Files\Epic Games\UE_5.8'
$projectFile = (Resolve-Path -LiteralPath 'work\t3b_unreal\T3BRemake.uproject').Path
& "$engineRoot\Engine\Build\BatchFiles\RunUAT.bat" BuildCookRun "-project=$projectFile" -noP4 -platform=Win64 -clientconfig=Development -build -cook -stage -pak -utf8output
```

历史 `Game` target 已编译成功，但直接用 Game exe 加载 loose map 曾失败。不能用“生成了 exe”替代地图加载、cook、GPU 或 M1 测试。

## 5. 进一步验证

`work/t3b_unreal/Tools/verify_source_core.py` 是包含原版冻结数据的完整比较，依赖未提交的 `psp_parse/out/` probes 和 `t3b_hd/assets/`。`verify_source_bundle.py` 还会读取 manifest 的绝对 provenance 路径；迁移路径需要先处理。`psp_parse/tools/verify_*` 各有不同输入要求，先看其 `--help` 与对应解析报告。
