# T3B-HD ·《寄生前夜：第三次生日》PC 高清重制

基于本地原版资源与 PPSSPP 运行时证据，恢复角色、材质、动作及场景，再迁移到 **Unreal Engine 5.8 / C++**。当前处于原版还原与 UE 接入阶段，尚无完成的 UE 可玩高清版本。

## 从这里开始

- [当前状态与下一步](docs/CURRENT_STATUS.md)：已验证范围、已知失败、优先任务。
- [开发环境与运行](docs/DEVELOPMENT.md)：纯源码检查、C 原型、UE 构建。
- [运行包下载与安装](docs/ASSET_HANDOFF.md)：GitHub Release、资产同步及 SHA-256 校验方法。
- [协作约定](CONTRIBUTING.md)：分支、PR、数据与验证记录。
- [架构与入口](docs/ARCHITECTURE.md)：模块职责、坐标与矩阵约束。

| 目录 | 职责 |
| --- | --- |
| `work/psp_parse/tools/` | ISO/容器、CLUT/FEP、EBOOT/PRX 分析及 PPSSPP CPU/GE 采集工具 |
| `work/psp_parse/docs/` | 解析报告及历史交接记录 |
| `work/psp_parse/archive/` | 早期工具及部分被现有工具引用的辅助模块 |
| `work/t3b_hd/` | C + SDL2 + OpenGL 2.1 战斗验证原型 |
| `work/t3b_unreal/` | UE5 正式迁移工程、独立数值 core、导入与验证工具 |
| `docs/evidence/` | 本机既有构建/失败报告的交接快照，非 CI 结果 |

## 不需要游戏资产的检查

需要 Python 3.10+ 和支持 C++17 的 `g++`：

```powershell
python -X utf8 scripts/check_source.py
```

该命令检查 Python 语法并运行已有的 57 项 source-data 数值与格式拒绝测试；不会启动游戏、安装引擎或读取 ISO。GitHub Actions 运行相同入口。它不覆盖 UE 编译、画面或可玩验收。

## 当前范围

C 原型已接入 Aya 的 44 source bones、原版枪械、一个原版异形和 140-draw 街景，并具备锁定、射击、碰撞适配与 Overdive 验证流程。UE Game/Editor target 已编译；全新 clone 配合运行包，已通过 Editor-hosted 地图加载、实际 CPU 顶点 probe 和 D3D11 离屏启动。像素/材质、cook 与正式 UE M1 可玩验收仍未完成。

Git 源码树包含源码、工具、技术文档和资产身份清单；运行所需的模型、贴图、UE Content 与预编译项目模块由 Release 单独提供。原版 ISO、EBOOT/PRX、存档和内存/GE 转储留在本地。来源与依赖见 [来源说明](THIRD_PARTY_NOTICES.md)。

各子目录 README 和 `CONTINUATION_CHECKPOINT.md` 保留大量历史记录；当前状态以 `docs/CURRENT_STATUS.md` 为准。

从 [GitHub Release 下载运行包](https://github.com/2510551378/T3B-HD/releases/tag/runtime-assets-20261023-v2)，安装到 clone 后用 `scripts/run_m1.ps1` 或 `scripts/run_unreal.ps1` 启动。具体校验、引擎版本与命令见[运行包交接](docs/ASSET_HANDOFF.md#可安装的运行包)。
