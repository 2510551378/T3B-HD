# UE M1 v4：可玩的单敌人战斗切片

默认地图现在运行第三人称 M1 战斗：Aya 在原街景中移动、锁定 Twisted、持续射击、换弹；敌人追击、近战、受击和死亡，Overdive 镜头自动返回。v4 同时包含 v3 的原材质遮挡修正和 Aya/枪械同步动作。

## 安装和操作

更新源码，从 [v4 Release](https://github.com/2510551378/T3B-HD/releases/tag/runtime-assets-20261023-v4) 下载运行包及 SHA-256 文件，按 [资产交接](ASSET_HANDOFF.md) 安装：

```powershell
python -X utf8 scripts/runtime_bundle.py install 'C:\Transfer\T3B-HD-runtime-assets-20261023-v4.zip' --sha256 <SHA256>
.\scripts\run_unreal.ps1 -Game
```

需要 UE **5.8.4 / CL 58902052 / module BuildId 55116800**。运行包提供项目 DLL、模型、贴图及 UE Content；通过 Editor host 运行，尚未提供 cooked 独立游戏。

| 输入 | 行为 |
| --- | --- |
| WASD、Shift | 移动、快跑 |
| Mouse | 转动镜头；上下观察保持捕获动作的枪械 pitch |
| RMB / Tab | 锁定、解除锁定；锁定校准真实枪管水平朝向 |
| LMB | 持续射击；HUD 准星投影实际枪口射线 |
| R | 换弹；胜负结束后重开 |
| E | 锁定存活目标时进入 Overdive 镜头，自动返回 |
| Backspace | 重开 |
| Esc、LMB | 释放、重新捕获鼠标 |

每发伤害 25、间隔 0.22 秒、弹匣 30 发、换弹 1.2 秒。Twisted 会追击并近战造成 20 伤害。Overdive 进入/停留/返回为 0.32/1.0/0.32 秒，返回后冷却 3 秒。

## 数据与行为边界

- **原版数据**：原街景、Aya、武器及 Twisted 网格、atlas、逐 draw 材质状态、捕获的骨骼矩阵与动作对。
- **场景碰撞**：对 blend off、depth write on 且所有纹理/顶点 alpha 都大于零的面构建 8,551 个实体三角形。Capsule 移动、地面支撑、台阶、墙滑动和相机遮挡是 PC 适配；原游戏碰撞格式尚未恢复。
- **弹道**：从当前枪管网格 tip/base 得到枪口和方向，对当前姿态 Twisted 三角面及场景查最近交点，同距优先场景。锁定不绕过墙或自动赋予伤害；tip/base 仍是几何代理，未宣称恢复原版命名枪口。
- **表现**：Aya 与枪械共享位置、旋转和动作相位，动作末尾有 120 ms 共同过渡；受击闪色/后仰、倒下、追击和数值为 PC 战斗适配。当前移动片段是 `approach_fire`，不是完整 locomotion。
- **Overdive**：当前实现为 M1 的进入、停留、返回镜头流程；外侧镜头避免进入 Twisted 躯体。尚未实现原作队友宿主与控制权转移系统。
- 原版光照、fog/stencil、状态/事件调度和完整高清美术仍需恢复/制作。当前材质修正不增加原贴图缺失的细节。

## 可复现验证

不需要资产的 `python -X utf8 scripts/check_source.py` 包含 57 项 source-data、29 项动作兼容/循环、41 项碰撞几何检查，共 **127 项**。

已安装运行包的工程可运行实际 UE 战斗验收：

```powershell
python -X utf8 work/t3b_unreal/Tools/validate_m1_combat.py --project C:/src/T3B-HD/work/t3b_unreal/T3BRemake.uproject --output build/combat-validation --rhi d3d11
```

验证器启动实际 UE，要求新 run ID、正常退出、完整报告及全部检查通过。14 项检查覆盖：真实街景墙阻挡、墙后真实敌人遮挡、近战伤害、换弹计时、重开、锁定、Overdive 进入/拒绝重入/返回/冷却、实际枪口命中、连续射击扣弹、敌人死亡和解除锁定。确定性验收在射击阶段暂停 AI 追逐，正常游玩及画面采集保持 AI 开启。

实测墙阻挡停在 UE Y=-1543.8573 cm；遮挡场景中墙交点 367.8759 cm、敌人网格交点 597.7296 cm，伤害被拦截。正常战斗画面采集也得到 4 shots / 4 hits / enemy HP 0，并完成一次 Overdive 返回。

证据摘要保存在 [v4 验证目录](evidence/ue_m1_v4/)，完整原始日志和 PNG 保存在维护者本地 `dist/ue_m1_20261023_v4/`。Release 附锁定、Overdive、受击和战斗结束截图。

全新 clone 安装 v4 ZIP 后，D3D11 / NullRHI 各 14 项检查、655 资产身份、实际 source 顶点与 361 个连续动作采样均通过；重复安装写入 0 个文件。公开下载已回读并核对 SHA-256，见 [交付记录](evidence/ue_m1_v4/published_release.json)。

[锁定画面](https://github.com/2510551378/T3B-HD/releases/download/runtime-assets-20261023-v4/M1_locked.png) · [Overdive 外侧镜头](https://github.com/2510551378/T3B-HD/releases/download/runtime-assets-20261023-v4/M1_overdive.png) · [受击](https://github.com/2510551378/T3B-HD/releases/download/runtime-assets-20261023-v4/M1_hit.png) · [战斗结束](https://github.com/2510551378/T3B-HD/releases/download/runtime-assets-20261023-v4/M1_clear.png)

## 诊断入口

```powershell
.\scripts\run_unreal.ps1 -Game -ReplayOnly
```

该模式保留原 Spectator 回放和 `T3B.Replay.Probe` / `T3B.Replay.MotionProbe`，可核对原始采样而不混入战斗位置变换。战斗模式下拒绝输出这两类不可变 source probe。

战斗控制台支持 `T3B.Combat.Reset`、`Lock`、`Fire 0|1`、`Overdive`、`Probe`、`Smoke`。实际战斗报告写入项目 `Saved/Combat/m1_combat_probe.json`。
