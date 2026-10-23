# 原版武器关联矩阵与 CPU GE 命令：六组真实采集

完整原始记录为 `out/AYA_BONE_GE_ACTIONS/slot0_weapon_ge_emit_fire6_command_alias_v3/marker_ge_emit.json`，SHA256 `c71bde19a85420fa74c2bdb0dc7262fed18e9c926a671d179c33e340686917de`。Producer 在连接前冻结，SHA256 `464337805b2210071ae069fccb7b6423b84ae3b61226b4cd77d8327807a3bf74`，副本位于 `out/WEAPON_GE_EMIT_STATIC_20261020/trace_weapon_marker_ge_emit_command_alias_v3_offline_validated.js`，174 个离线 Mock 通过。真实采集 session42670 自然 exit0：102次入口暂停，96次非精确FEP资源排除，6组九阶段完整返回，failure/inFlight=null。输入释放、自有断点移除、暂停恢复均成功。

`tools/analyze_weapon_ge_emit.py` 独立重核真实枪243vertices/VTYPE522的完整身份、FEP192原record、definition/registry/参数来源、逐阶段SP/RA及saved GPR、实际geometry对象链、原码双恢复与命令字节。报告 `out/WEAPON_GE_EMIT_RUNTIME_20261020/fire6_independent_audit.json`：6rows/85code blocks通过。`verify_weapon_ge_emit_audit.py` 的16个合成坏证据均被拒绝，包含SHA有效但VIEW/PRIM payload、mode byte、资源ID和emitter实际对象错配；这些是auditor反例，不是运行采集。

| 样本 | 实际type | matrix mode | runtime资源ID | FEP源record | 首次PRIM顶点 | VTYPE/stride |
|---|---:|---:|---:|---|---:|---|
|0/1/4/5|152|1|15|2b58|4|102 /10bytes|
|2|155|0|18|2690|14|11e /16bytes|
|3|155|0|19|26a8|4|11e /16bytes|

六组各实际写入52bytes的VIEW包和16bytes的首个PRIM包。PRIM primitive=4；本表只保留原数值，不据小面片形状命名其FX。152的真实emitter stack+10/+14/+18匹配H/geometryObject/container20；155的s4/s5匹配geometryObject/container20，进一步将source ID实际绑定到发射时的数据流。只读独立review与closure报告在静态目录，记录原码spill与寄存器依据。

## 两次失败及窄修

首次 `slot0_weapon_ge_emit_fire6_20261020` 在matrix.entry失败：原component是字节结构指针08d5e27a，旧read4误要求4aligned。保留原componentPointer、fieldAddress=pointer+1、byteOffset；只读覆盖该byte的aligned4窗口，没有放宽普通指针校验。

第二次 `slot0_weapon_ge_emit_fire6_component_v2` 已取得实际matrix返回，但VIEW前发现DLcursor48c5a9d0属于uncached RAM alias，旧gate拒绝。v3仅对命令窗口映射48000000..4bffffff→08000000..0bffffff，分别保留CPU原cursor和readCursor/readAddress；所有对象、矩阵、vertices仍按普通RAM检查。两次失败记录、旧producer冻结和全部raw均保留，未重新标为完整成功。

## 数学回放与边界

`tools/verify_weapon_ge_matrix_math.py` 直接解释原module opcodes，不导入producer预测式。actual_v3及root_replay_v3的独立运行均对6matrix+6VIEW共192个float32输出得到0bit差异，6次matrix返回全部32GPR也相同。四个mode1实际f12=32；两个mode0实际f12约138.823532和35.730488，不能默认scale=1。

入口VFPU S/T/D prefix控制未由cpu.getAllRegs导出，因此matrix结论限于default-entry-prefix条件下的这些实际输出一致。mode1原6589c/104有同次runtime双恢复；mode0原657f8/a4仅从固定module取码，同次完整helper身份仍未采。VIEW用实际handlerMatrix与global588单独计算，不复用预测的matrix输出。其默认prefix路径有前面helper最终VFPU指令消耗prefix的静态依据，但仍不扩大为全部未知mode的证明。

## 接入边界与下一步

此处证明 CPU display-list writes，`geDrawObserved=false`、`semanticName=null`。尚未证明GE执行、最终像素、所有PRIM/材质状态或枪口/弹道语义，未替换M1正式socket/timeline。下一次新动作采集补657f8完整原码身份，并将实际命令流与GE draw/纹理/原机位画面关联；不以时间邻近把无关draw命名为枪口。
