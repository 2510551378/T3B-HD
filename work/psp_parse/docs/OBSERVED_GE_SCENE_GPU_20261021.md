# 原版逐 draw 场景 GPU 对照：12 组样本

独立 D3D11 run `d16757dbab6645ababbe99e4d838841d`，PID 80080 自然退出 0，RTX 2080 Ti。实际编译、DXBC、进程身份、纹理 staging Map、顶点 stream-output 和颜色／owner／D24S8 读回均保留。此次没有启动 UE 或 PPSSPP，也没有完成正式 UE C++ 编译。

## 恢复范围

从同 12 份原 PPDMP 恢复所有已观察的无权重 VTYPE 0x11f triangle draws，并加入已验证的 Aya 106 draws／真实枪械 1 draw 每组。共 2,892 draws、413,424 顶点、77 个有效 CLUT 解码 RGBA atlas。包括此前未匹配的 40 次 draw 观察／10,548 个顶点，不能据此称完整关卡或完整游戏已经恢复。

每次 draw 保留自身 WORLD／VIEW／PROJECTION、原 source 顺序、纹理与有效 CLUT。独立相机背景没有被强制套进 Aya 主相机；输入几何没有预先投影为屏幕图片。`T3BGEF1` 是本工程导出的桥接格式，不是原 PSP 文件格式。

## 实际检查

- 413,424 条 GPU VS clip／UV／primary color／fog 输出按原 PPDMP 独立重算。可见顶点的最大投影差为 0.0000619505 PSP 像素；此结果不等于完整 PSP 像素等价。
- 77 次实际 GPU atlas 上传读回逐 RGBA byte 同原解码，逐 draw 绑定保留。
- 60 张源状态／关闭背景／仅背景／关闭 fog／关闭 depth writes 图，加 4 张合成 fog／stencil 控制图，共 64 组真实 GPU 采集。三个 fog 控制色为 [68,112,142]、[98,88,166]、[128,64,191]；depth-fail stencil replacement 实际读回为 73，颜色 owner 保持近表面 1。
- 所有组关闭背景后主 depth／stencil 完全不变；关闭 fog 不改变 owner／depth；关闭 depth writes 不改变 union coverage。
- 样本 4–7 的独立背景在单独渲染时有覆盖，但完整场景中被后续 draw 全部覆盖。原 auditor 错误要求每组背景必须产生最终 RGB 差，导致失败。原源码与失败原因留在 `failed_auditor_v1.py`／`failed_audit_v1.json`。最终 auditor 检查实际背景 coverage、后续 draw 覆盖与最终 owner 一致，保留全部投影和数据精度阈值；已有 PNG 只读核对像素，不覆盖。
- 已人工查看 source sample0 与全部 12 组 CONTACT_SHEET。原 ISO、slot0、INI 和 184 个旧 UE packages 的 hash 全部保持不变。

## 边界与下一步

这是独立 native D3D11 reference；新增逐 draw 相机、fog、depth/stencil 子集尚未进入 UE C++ pass。D3D11 texture sampling／interpolation／blend、D24S8 与 PSP 完整固定点栅格／16-bit depth 有差异；PSP framebuffer alpha/stencil 耦合没有复现。其他 weighted actors、FX、HUD、全关卡、原动作时钟、命名手骨／握把／枪口、高清材质和完整 M1 仍未完成。

官方 PPSSPP v1.20.4 `DrawPixel.cpp` 已只读保存到本 run 的 `official_ppsspp_v1.20.4`，附 URL／SHA，用于核对 fog 整数量化／混色与 stencil 操作，没有整份复制进运行时代码。

用户已授权 Microsoft 官方 MSVC 14.44＋Windows SDK 22621 后台安装。原 bootstrapper 已下载并验签；实际 Windows RunAs 返回“操作已被用户取消”，未启动 installer，当前目录／SDK headers 仍不存在。现有 UAC 诊断问题尚待回复，未重复提权，不能宣称安装完成或正式 UBT 通过。

[手动查看 12 组及对照](../../t3b_unreal/Validation/observed_ge_scene_runs/d16757dbab6645ababbe99e4d838841d/PREVIEW.html) · [独立检查](../../t3b_unreal/Validation/observed_ge_scene_runs/d16757dbab6645ababbe99e4d838841d/independent_verification.json)
