# UE M1 v3：材质遮挡与连续射击动作

本轮修正 UE source replay 中 Aya 的材质遮挡、动作切换检查，以及连续射击循环中的身体/枪械同步。仍不是完整 UE 战斗切片，也没有新增高清纹理细节。

## 行为变化

- 原街景、Aya、枪械和异形共用按序渲染 pass，读取原 atlas、UV、RGBA、blend/cull/depth-write 状态，写 UE 主深度。避免普通 UE 透明材质不写主深度，以及 Separate Translucency 后合成造成的透体和异形覆盖角色。
- 保留旧 UE 材质作为 A/B 开关。原贴图、模型、地图和材质包的 655 项资产身份保持不变；此次更新主要是 C++ 项目模块。
- Aya 与枪械始终选同一动作对、同一时间相位；保留过帧余量，在片段末尾用 120 ms smoothstep 共同过渡到首帧。该循环是 PC 预览适配，不代表恢复了原版动作时钟。
- 切换动作时校验 bind geometry、UV、normal、权重、层级、材质 packet 和 flags，拒绝静默换绑。实际 UE probe 现在比较选中的动作，不再固定拿 reference 动作作基准。
- 武器继续使用同次捕获的原变换，没有把独立 source36 timeline 当作固定 socket。接触点与枪口方向检查是网格代理，不是已恢复的原版命名挂点。

## 查看和操作

从 [v3 Release](https://github.com/2510551378/T3B-HD/releases/tag/runtime-assets-20261023-v3) 下载运行包，更新源码后安装。旧运行包中未修改的文件可以直接升级；本地修改过的资产仍会被保护。

```powershell
python -X utf8 scripts/runtime_bundle.py install 'C:\Transfer\T3B-HD-runtime-assets-20261023-v3.zip'
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_unreal.ps1 -Game
```

需要 UE 5.8.4 / BuildId `55116800`。按住左键推进连续射击动作，松开停在当前姿势。当前控制的是动作预览，尚未接入完整 UE 伤害/AI。

控制台命令：

| 命令 | 用途 |
| --- | --- |
| `T3B.Replay.ActionClip reference` | 参考射击捕获 |
| `T3B.Replay.ActionClip approach_fire` | 同源移动射击捕获 |
| `T3B.Replay.Fire 1` / `0` | 播放连续射击 / 停住 |
| `T3B.Replay.Pause 1`、`T3B.Replay.Seek 0.65` | 停在指定原采样时间，忽略循环过渡 |
| `T3B.Replay.OriginalMaterials 1` / `0` | 新按序材质 / 旧 UE 透明材质对照 |
| `T3B.Replay.Probe` | 当前选中动作的全部存储帧、实际组件顶点读回 |
| `T3B.Replay.MotionProbe` | 12 秒、361 个循环采样的接触点/枪管代理读回 |

## 实际画面对照

以下为同一 UE 机位、0.65 秒姿势，关闭时间抗锯齿以隔离材质差异。旧路径的背面能看到正面脸、手和衣服；新路径恢复背面衣料与正确自遮挡。颜色仍使用既有 C-adapter face shade，未宣称原 GE 光照或完整 PSP 像素等价。

旧 UE 透明材质：

![Legacy UE translucency](https://github.com/2510551378/T3B-HD/releases/download/runtime-assets-20261023-v3/Aya_material_legacy.png)

新按序主深度路径：

![Ordered source depth](https://github.com/2510551378/T3B-HD/releases/download/runtime-assets-20261023-v3/Aya_material_fixed.png)

## 验证

- UE Editor target 实际编译链接；D3D11 实际机位截图。
- reference / approach_fire 各 60 个存储采样的实际组件 CPU-world 顶点，独立比较通过。
- 每组 12 秒、361 个循环采样，包括 17 个过渡采样。独立 NumPy 比较实际接触/枪管代理；每组最大组件误差小于 0.00002 cm，枪管方向误差小于 0.00001°。
- 接触代理是同一组网格顶点，不是握把中心：reference 距离约 1.17–1.34 cm，approach_fire 约 1.18–1.32 cm，未出现循环跳脱。
- source-data 格式/数值 57 项，加动作兼容性/循环 29 项；不把这些 synthetic checks 当真实 UE 运行。

证据摘要见 `docs/evidence/ue_m1_v3/`。原始 CPU CSV 和六机位 PNG 保存在本地 `dist/ue_m1_20261023_v3/`；Release 附主要截图。

下一步仍需恢复原光照/完整 fog-stencil、动画/事件调度、UE 碰撞与伤害、敌人 AI，以及高清美术。原 ISO 和用户存档保持不变。
