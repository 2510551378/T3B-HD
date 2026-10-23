# 正式重制引擎：Unreal Engine 5

2026-10-20 根据用户要求选定。正式重制采用 Unreal Engine 5；本机迁移基线为 UE 5.8.3（CL 58210709）。已建立 `work/t3b_unreal/T3BRemake.uproject` 与 C++ source replay、资产 staging 和独立数值验证。引擎现已可执行，首次正式构建因缺少 Windows SDK 而失败；独立 content-only host 已在真实 UE commandlet 保存并核对 76 张原版纹理、84 个基线材质和 1 个空地图。尚未通过 UE C++ 编译、replay 运行或可玩验收。当前可运行的 `t3b_hd.exe` 仍为 C + SDL2 + OpenGL 2.1 验证原型。

## 选择依据

安装状态更新（2026-10-20 13:40 UTC）：当前引擎目录不变，Build.version/编辑器文件版本/Launcher manifest 均为 UE 5.8.4（CL 58902052），incomplete=false。`work/t3b_unreal/Validation/environment_engine_reply_20261020.json` 保存本次只读检查；原有 UE 5.8.3 运行证据仍保留其历史版本。MSVC/Windows SDK 仍未发现完整组合，本次没有安装系统组件或重复失败构建。

- 项目是 Windows 第三人称动作射击游戏，需要越肩相机、骨骼动画、武器挂接、敌人、关卡和过场的完整制作工具。UE 的 Third Person 模板提供角色与相机起点，Combat variant 提供 targeting/health 参考；这些模板行为不等于原版行为。
- 官方 skeletal mesh 内容管线支持骨骼动画、材质、UV、vertex colors 和 LOD，可用于后续生产资产制作。现有匿名 source bones、原始 bind compensation 和任意 affine 动画不能假定直接 FBX 导入即正确。
- Lumen 等现代渲染功能为高清场景提供升级路径。原版低分辨率贴图和低多边形模型仍需独立重建，换引擎不会自动产生高清细节。
- 代价是编辑器、构建和资源管理更重。首个目标仍为 1080p；先在实际机器上建立性能基线，再决定光照和后处理设置。

## 工程边界

- `work/psp_parse/`：原 ISO、EBOOT/PRX、RAM、GE、CLUT/FEP 的解析与证据工具。
- `work/t3b_hd/`：现有 C 原型和独立验证器，作为迁移的 golden reference。
- 正式 UE 项目已建立于 `work/t3b_unreal/`；工程源码和原始资源桥接已有初版，尚未完成 UE 编译及运行验收。
- UE 侧由 C++ 负责原始资源桥接、蒙皮/动作核对和战斗核心；Blueprint 用于场景、相机、UI 和经验证后的玩法编排。

## 最小迁移验收

1. **U0：街景导入**。重放已确认的 140 draws / 31,656 vertices / 81 render-material states / 73 RGBA textures，保留原始 UV、vertex RGBA、alpha 与相对 WORLD。先以便于对照的材质核对图像，再升级光照。
2. **U1：角色与动作**。接入 Aya 44-bone/106-packet、真实枪械和原版异形；将 UE 全 60 帧变形顶点、武器变换与冻结的 C/source probes 比较。转换明确处理坐标手性、单位、bind compensation、源时间以及法线/绕序。不能仅靠更换真人骨架或模板动画通过验收。
3. **U2：战斗切片**。迁移越肩镜头、锁定、枪口射线与场景碰撞适配，复现原版出生点的实际命中/遮挡结果。未恢复的原版 AI、muzzle consumer 和动画状态继续作为独立解析任务。
4. **U3：高清表现**。在原版接入通过后制作高模、高清贴图和 PBR 材质、特效、过场与性能分档。使用匹配机位对照原版和升级版，检查角色比例、脸部、衣物及动作。

每个阶段必须在真实 UE 运行结果中验收。安装引擎、创建工程或导入文件成功均不能替代可玩和数值验证。

## 官方依据

- [UE 5.8 正式发布](https://www.unrealengine.com/news/unreal-engine-5-8-is-now-available)
- [Third Person Template](https://dev.epicgames.com/documentation/en-us/unreal-engine/third-person-template-in-unreal-engine)
- [FBX Skeletal Mesh Pipeline](https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-skeletal-mesh-pipeline-in-unreal-engine)
- [Lumen](https://dev.epicgames.com/documentation/en-us/unreal-engine/lumen-global-illumination-and-reflections-in-unreal-engine)
- [引擎授权](https://www.unrealengine.com/license)：游戏的 royalty 适用条件按官方条款执行；当前标准对单个产品累计总收入超过 100 万美元的适用部分收取 5%，存在条款规定的例外。
