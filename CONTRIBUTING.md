# 协作开发

1. 从 `main` 创建任务分支，例如 `ue/editor-probe`、`recovery/weapon-marker`、`art/aya-materials`。
2. 一次 PR 聚焦一个可验证结果。先写清输入身份、预期行为、验证方法，再改对应模块；避免同时改解析器、动作格式与渲染基线。
3. 提交前执行 `python -X utf8 scripts/check_source.py`。更改涉及 UE、GE、材质或玩法时，补做对应实际运行检查，记录引擎版本、命令、退出码、输入/输出 SHA-256 和已知限制。
4. PR 说明：解决什么问题、改变什么行为、如何验证、还有哪些未覆盖范围。截图需要注明相机、采样帧、原版/增强配置，不能把 native D3D11 结果当 UE 验收。
5. 合并通过 Pull Request；当前仓库尚未设置 branch protection。不要 force-push `main`，不要把本机生成目录或游戏资产加入 Git。

## 建议任务分工

| 工作线 | 主要目录 | 首个目标 |
| --- | --- | --- |
| UE 接入 | `work/t3b_unreal/Source`、`Shaders`、`Config` | Editor 编译、cook、实际 `T3B.Replay.Probe` 输出 |
| 原版还原 | `work/psp_parse/tools` | 同一采集的 CPU→GE→draw 关联，保留匿名 source index |
| 角色与材质 | UE `Tools`、解析工具、私有资产目录 | 同机位原版材质/透明深度核验，再制作高清资源 |
| M1 战斗 | `work/t3b_hd/src` | 保持可运行数值对照，迁移碰撞/锁定/射击/Overdive |

任务分工是建议，不代表已有负责人。修改共用二进制格式、source bundle、坐标转换或着色器 contract 前先在 PR 中说明兼容范围。

## 数据与证据

- 原 ISO、用户存档保持只读。采集用独立副本；不要运行会自动改写主存档/配置的历史脚本而未检查参数。
- 不提交 ISO、解密程序、内存/GE dump、游戏图片、模型、贴图、UE 二进制包或第三方 SDK。新增可再分发的原创资产另行明确来源与跟踪方式。
- 运行资产通过维护者发布的版本化 Release 提供，不加入 Git 历史；新增版本需附文件清单与 SHA-256。
- `docs/runtime_asset_manifest.json` 是本次交接的身份快照。资产变更需使用新快照并说明来源，不能静默覆盖旧证据。
- `work/psp_parse/docs` 是历史研究记录，部分链接指向未提交的 `out/`。完整证据需从本地归档取得；仅有摘要不代表独立复现通过。
- 明确区分 compile、load、CPU 数值、GPU 出图和 playable；失败报告保留，不用扩大阈值掩盖失败。
- Windows 使用 UTF-8，保留现有行尾，不对整个工程格式化。
