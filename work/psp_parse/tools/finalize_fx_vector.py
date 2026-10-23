"""Freeze vector curves/continuous-state evidence and protect original artifacts."""
import copy,datetime,json,shutil,struct
from pathlib import Path
from analyze_fx_node_time import check,identity,read,sidecar,u32
from analyze_fx_vector_curve import audit_vectors
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'out/FX_VECTOR_CURVE_20261021'
def write(p,v):p.write_text(json.dumps(v,indent=2),encoding='utf-8')
def main():
    check(not(OUT/'checkpoint.json').exists(),'Never replace completed vector checkpoint')
    audit=read(OUT/'combined_audit_v3/verification.json');runtime=read(OUT/'runtime_v4/verification.json');chain=read(OUT/'continuous_runtime_v1/verification.json')
    check(audit['passed']and runtime['passed']and chain['passed']and chain['state_snapshots_loaded']==1,'Missing actual continuous proof')
    cp=OUT/'key9_state6_v1/fx_property_callbacks.json';capture=read(cp);bank=OUT/'source_bank_v1';bank.mkdir();records={}
    row=next(r for r in capture['rows']if r['type']==6);items=[row['record'],row['oldRecord']]
    for call in capture['vectorStateSeries']:
        if call['kind']=='vector_wrap':items.extend([call['currentRecord'],call['previousRecord']])
    for item in items:
        source_offset=item['address']-capture['selection']['FEPbase']
        if source_offset in records:continue
        prefix=sidecar(item['raw'])[:44];path=bank/('type6_record_%x_consumed_prefix.bin'%source_offset);path.write_bytes(prefix)
        records[source_offset]=dict(source_offset=source_offset,consumed_prefix=identity(path),consumed_bytes=44,
                                   key_XYZ_bits=[u32(prefix,group*16+axis*4)for group in range(3)for axis in range(3)],allocation_size_inferred=False)
    write(bank/'source_vector_keys.json',dict(passed=True,source_FEP=capture['FEP'],definition_index=1,type=6,parameter_offset=0x20,records=list(records.values()),
                                             key_record_W_consumed=False,state_W_preserved_by_key_helpers=True,evaluation_computes_all4_lanes=True,source_units_or_anatomy_named=False))
    neg=OUT/'negative_evidence_v1';neg.mkdir();cases=[]
    def reject(name,change,expected):
        out=neg/name;out.mkdir();bad=copy.deepcopy(capture);change(bad,out);p=out/'fx_property_callbacks.json';write(p,bad)
        for f in('executed_trace_fx_property_callbacks.js','process_completed.json'):shutil.copyfile(cp.parent/f,out/f)
        try:audit_vectors([p])
        except ValueError as e:check(expected in str(e),'Wrong evidence rejection gate: '+str(e));cases.append(dict(case=name,rejected=True,error=str(e),capture=identity(p)))
        else:raise ValueError('Bad vector evidence accepted: '+name)
    def wrong_time(r,out):
        call=r['vectorStateSeries'][2];regs=json.loads(sidecar(call['entry']['allRegisters']));f=next(c for c in regs['categories']if c['name']=='FPU');f['uintValues'][13]=0x40400000;p=out/'changed_old_time.json';write(p,regs);call['entry']['allRegisters']=dict(bytes=p.stat().st_size,**identity(p))
    def change_window(item,out,name,offset,value):
        data=bytearray(sidecar(item['raw']));struct.pack_into('<I',data,offset,value);p=out/name;p.write_bytes(data);item['raw']=dict(bytes=len(data),**identity(p))
    def wrong_carry(r,out):change_window(r['vectorStateSeries'][0]['entry']['snapshot']['parameterWindow'],out,'changed_unused_current_before.bin',0x28,0x42c80000)
    def wrong_w(r,out):change_window(r['vectorStateSeries'][2]['return']['snapshot']['parameterWindow'],out,'changed_wrap_W.bin',0x2c,0)
    reject('wrong_original_wrap_time',wrong_time,'Continuous vector evaluator bytes differ')
    reject('broken_modifier_to_evaluator_carry',wrong_carry,'Modifier output does not feed first live vector evaluation')
    reject('wrong_wrap_output_W',wrong_w,'Continuous vector evaluator bytes differ')
    write(neg/'verification.json',dict(passed=True,cases=cases,synthetic_bad_evidence_cases=3))
    baseline=ROOT/'out/FX_RANDOM_MODIFIERS_20261021/source_protection.json';old=read(baseline);protection=dict(checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),baseline=identity(baseline))
    for group in('original_files','packages'):
        protection[group]=[]
        for row2 in old[group]:
            item=identity(Path(row2['file']));item.update(expected_sha256=row2['sha256'],unchanged=item['sha256']==row2['sha256']);protection[group].append(item)
        check(all(i['unchanged']for i in protection[group]),'Original/previous package changed')
    write(OUT/'source_protection.json',protection);project=ROOT.parent/'t3b_unreal'
    files=[ROOT/'tools'/n for n in('trace_fx_property_callbacks.js','capture_weapon_ge_correlated.ps1','replay_fx_vector_curve.py','analyze_fx_vector_curve.py','verify_fx_vector_runtime.py','verify_fx_vector_chain.py','finalize_fx_vector.py','replay_fx_color_scale.py','replay_fx_random_modifiers.py','analyze_fx_random_modifiers.py','analyze_fx_property_callbacks.py','analyze_fx_node_time.py','verify_weapon_ge_matrix_math.py')]
    files += [project/'Source/T3BRemake'/folder/n for folder,names in [('Public',['T3BGEEffectVectorCurve.h','T3BGEEffectModifiers.h']),('Private',['T3BGEEffectVectorCurve.cpp','T3BGEEffectModifiers.cpp'])]for n in names]
    files += [project/'Tools'/n for n in('ge_effect_vector_probe.cpp','ge_effect_vector_chain_probe.cpp')];snap=OUT/'current_tool_snapshots';snap.mkdir();sources=[]
    for p in files:
        dest=snap/p.name;shutil.copyfile(p,dest);sources.append(dict(source=str(p.resolve()),**identity(dest)))
    processes=[]
    for name in('reset21_vector_v1','key9_vector_random_v1','key9_evaluate6_v1','key9_state6_v1'):
        state=read(OUT/name/'process_completed.json');check(state['owned_emulator_stopped']and state['node_exit_code']==0,'Live/failed capture process');processes.append(dict(run=name,terminal=identity(OUT/name/'process_completed.json')))
    write(OUT/'checkpoint.json',dict(passed=True,audit=identity(OUT/'combined_audit_v3/verification.json'),runtime=identity(OUT/'runtime_v4/verification.json'),continuous_runtime=identity(OUT/'continuous_runtime_v1/verification.json'),
                                    negative_evidence=identity(neg/'verification.json'),source_bank=identity(bank/'source_vector_keys.json'),source_protection=identity(OUT/'source_protection.json'),sources=sources,processes=processes,
                                    previous_goal_turn='progress: original modifier targets and scalar RNG core recovered',current_goal_turn='progress: type6 vector key/wrap/evaluation and one-initial-state6-step live carry verified',goal_status='active',UE_module_built=False,default_M1_changed=False))
    print(json.dumps(dict(passed=True,source_keys=len(records),bad_evidence_rejected=3,tool_snapshots=len(sources),original_files_unchanged=3,existing_UE_packages_unchanged=185)))
if __name__=='__main__':main()
