# 来源与依赖说明

- 《The 3rd Birthday / 寄生前夜：第三次生日》的游戏代码及资产属于其原权利人。仓库不包含 ISO、EBOOT/PRX、提取模型/贴图或存档；资产清单仅记录路径、长度和 hash。
- Unreal Engine 由 Epic Games 提供，开发者自行安装并适用其许可。仓库不包含引擎或 SDK。
- SDL2、MinGW/GCC、Python、Node.js、Pillow、NumPy、Capstone 等由开发者单独安装，遵循各自许可；本仓库不捆绑第三方二进制。
- PPSSPP 是采集和对照工具。部分软件光照、sprite 和 VFPU 随机数验证以 PPSSPP v1.20.4 的实现为参考。具体来源、固定版本、函数和验证范围见 `work/psp_parse/docs/` 中的 `AYA_GE_VERTEX_LIGHTING_20261020.md`、`GE_RECT_SPRITES_20261021.md`、`FX_VFPU_RCX_20261021.md` 及相关源码注释。上游源码不随第三方下载目录提交。

当前未为整个仓库声明统一的开源许可证。后续对外发布前，需要分别确认自有代码、参考实现和新增资产的授权范围；本说明不替代任何上游许可，也不授予原游戏内容的再分发权。
