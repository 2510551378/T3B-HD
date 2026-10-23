# type6／type23 与局部矩阵消费者的关系审计

本阶段没有把连续 vector 状态直接接到矩阵 pass，而是用同一原属性快照和既有矩阵 verifier 把地址关系核对清楚，避免错误接线。

[关系审计](../out/FX_MATRIX_CONSUMER_MAP_20261021/verification.json) · [此前 type6 连续状态](FX_VECTOR_CURVE_20261021.md) · [原矩阵指令审计](../out/WEAPON_GE_MATRIX_MATH_20261020/actual_v3/matrix_math_verification.json)

确认结果：

- 当前节点 `N=0x097d1d10` 的 type6 参数地址为 `0x097d1d90`，即 `N+0x80`。
- type23 的 target lookup 在同一 capture 中也解析到 `0x097d1d90`，因此 type6 与 type23 共享该内部状态目标。
- type14 和 type155 的参数地址均为 `0x097d1e80`，即另一个 `P+0x60` alias。
- 已有实际矩阵 verifier 证明 matrix helper 读取 `P+0x60`，并通过原 opcode／GE matrix output 核验；它不是 type6／type23 的 `N+0x80`。
- 节点 `N+0x50` 是局部矩阵指针；已有矩阵输入／输出记录保留了真实 ABI 与结果。实时监测该指针的第一次尝试在外部 CPU stop 处终止，未产生完整 local-matrix write proof，故没有把它算作成功捕获。

这说明 type6／type23 的连续状态和矩阵 consumer 至少位于两个明确不同的地址区。它们可能通过后续 type14／共享记录／其他 handler 间接连接，但当前证据没有给出同一 writer 的直接 join。生产 UE pass 不会把 type6 buffer 直接当作 local matrix。

失败实时捕获 `FX_LOCAL_MATRIX_20261021/matrix3_v1` 仍保留：它确认了 type14 entry、local matrix pointer、leaf entry 及数次矩阵相关代码身份，但在下一阶段等待时收到外部 CPU stop，`localMatrixCalls=[]`，并非通过证明。下一次实验需要在已知 type14／matrix consumer 的 caller 上建立更窄的 stage gate，或在同一 GE draw capture 中做内容 join。

原 ISO、slot0、INI 和 185 个 UE package SHA 未改变；本阶段未启动 UE 或修改 Content。完整动作／矩阵调度、PC 相机和可玩 M1 仍未完成。
