# Aya 身体细节检查

检查对象：`assets/models/aya_original_runtime.obj`、`assets/materials/aya_albedo.bmp`、M1 no-flip 预览。

## 已确认

- face、eyes、hair、neck、black vest、belt 和 jeans 的 UV 映射正常；脸部纹理不再出现在腿部。
- 2650 个 UV 全部位于 `[0,1]`，没有越界 UV。
- 256×256 CLUT atlas 能正确覆盖头发、脸、衣服和裤子细节。
- 当前渲染阶段使用原始 `(u,v)`，不再重复做 V 翻转。

## 仍需单独处理

- 手臂的浅色断带和三角面接缝来自原版低面数几何、CPU pose 分区和法线/光照，不是 atlas 错绑。
- 武器 socket 已重新校准：idle 不再使用错误的静态 `bone4` fallback，而是使用 hand-local frame；射击时继续使用 44-bone source index `36` 的连续矩阵。mount correction 已按右手 draw bbox 中心重新拟合。
- 原场景建筑会遮挡躯干，已用空场景预览排除其对身体贴图判断的干扰。
