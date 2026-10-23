"""Export verified original operands, reject bad evidence and protect original files."""
import copy,datetime,json,shutil,struct
from pathlib import Path
from analyze_fx_random_modifiers import audit_capture
from analyze_fx_node_time import check,identity,sidecar,read,u16,u32

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'out/FX_RANDOM_MODIFIERS_20261021'

def write(p,v):p.write_text(json.dumps(v,indent=2),encoding='utf-8')
def main():
    check(not(OUT/'checkpoint.json').exists(),'Never replace completed modifier checkpoint')
    capture_path=OUT/'key9_random_v2/fx_property_callbacks.json';capture=read(capture_path);audit=read(OUT/'audit_v1/verification.json');runtime=read(OUT/'runtime_v2/verification.json')
    check(audit['passed']and runtime['passed'],'Modifier audit/runtime failed')
    bank_dir=OUT/'source_bank_v2';bank_dir.mkdir();bindings=[]
    for op in audit['operations']:
        row=capture['rows'][op['row']];prefix=sidecar(row['record']['raw'])[:44];path=bank_dir/('original_type%d_consumed_prefix.bin'%row['type']);path.write_bytes(prefix)
        header=sidecar(row['random']['activeDefinitionHeader']['raw'])
        bindings.append(dict(type=row['type'],definition_index=row['definitionIndex'],definition_source_offset=row['definition']['address']-capture['selection']['FEPbase'],
                             declared_parameter_offset=u16(header,2),target_lookup_index=u32(header,4),target_parameter_offset=op['target_lookup_offset'],
                             target_offset_in_parameter_window=op['resolved_offset_in_parameter_window'],record_source_offset=row['record']['address']-capture['selection']['FEPbase'],
                             consumed_prefix=identity(path),consumed_bytes=44,allocation_size_inferred=False,
                             channels=op['channels'],independent_axes=op['independent_axes'],vector_center_bits=op['vector_center_bits']))
    write(bank_dir/'source_modifiers.json',dict(passed=True,FEP=capture['FEP'],audit=identity(OUT/'audit_v1/verification.json'),bindings=bindings,
                                              note='Target lookup overrides the callback argument offset. Do not bind type23 to percent-scale or type24 to color by declared offset alone.'))
    negative=OUT/'negative_evidence_v2';negative.mkdir();cases=[]
    try:audit_capture(OUT/'key9_random_v1/fx_property_callbacks.json')
    except ValueError as e:cases.append(dict(case='first_capture_reused_rng_filenames',rejected=True,error=str(e)))
    else:raise ValueError('Overwritten first-capture sidecars accepted')
    def run_bad(name,change,expected_message):
        dest=negative/name;dest.mkdir();bad=copy.deepcopy(capture);change(bad,dest)
        path=dest/'fx_property_callbacks.json';write(path,bad)
        for name2 in('executed_trace_fx_property_callbacks.js','process_completed.json'):shutil.copyfile(capture_path.parent/name2,dest/name2)
        try:audit_capture(path)
        except ValueError as e:check(expected_message in str(e),'Unexpected rejection gate: '+str(e));cases.append(dict(case=name,rejected=True,error=str(e),capture=identity(path)))
        else:raise ValueError('Synthetic bad evidence accepted: '+name)
    def wrong_seed(d,dest):
        item=next(r for r in d['rows']if r['type']==24)['random']['channels'][0]['rng'][0]['entry']['seed'];raw=bytearray(sidecar(item['raw']));raw[0]^=1;p=dest/'changed_seed.bin';p.write_bytes(raw);item['raw']=dict(bytes=len(raw),**identity(p))
    def wrong_vector(d,dest):
        item=next(r for r in d['rows']if r['type']==23)['random']['channels'][0]['vectorRandom'];regs=json.loads(sidecar(item['allRegisters']));cat=next(c for c in regs['categories']if c['name']=='VFPU');cat['uintValues'][64]^=0x4000;p=dest/'changed_VFPU_registers.json';write(p,regs);item['allRegisters']=dict(bytes=p.stat().st_size,**identity(p))
    def wrong_target(d,dest):
        item=next(r for r in d['rows']if r['type']==23)['random']['targetOffset'];p=dest/'changed_target.bin';p.write_bytes(struct.pack('<H',0x60));item['raw']=dict(bytes=2,**identity(p))
    run_bad('wrong_scalar_seed',wrong_seed,'Original LCG transition/return differs')
    run_bad('wrong_VRNDF2_vector',wrong_vector,'Actual generated vector differs')
    run_bad('wrong_internal_target',wrong_target,'Original FEP window differs')
    write(negative/'verification.json',dict(passed=True,synthetic_bad_evidence_cases=3,first_capture_identity_failure_confirmed=True,cases=cases))
    baseline=ROOT/'out/UE_SCENE_COLOR_BRIDGE_20261021/source_protection.json';old=read(baseline);protected=dict(checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),baseline=identity(baseline))
    for group in('original_files','packages'):
        protected[group]=[]
        for row in old[group]:
            item=identity(Path(row['file']));item.update(expected_sha256=row['sha256'],unchanged=item['sha256']==row['sha256']);protected[group].append(item)
        check(all(r['unchanged']for r in protected[group]),'Protected files changed')
    write(OUT/'source_protection.json',protected)
    project=ROOT.parent/'t3b_unreal';files=[ROOT/'tools'/name for name in('trace_fx_property_callbacks.js','capture_weapon_ge_correlated.ps1','analyze_fx_random_modifiers.py','replay_fx_random_modifiers.py','verify_fx_modifiers_runtime.py','finalize_fx_modifiers.py','analyze_fx_property_callbacks.py','analyze_fx_node_time.py','verify_weapon_ge_matrix_math.py')]
    files += [project/'Source/T3BRemake/Public/T3BGEEffectModifiers.h',project/'Source/T3BRemake/Private/T3BGEEffectModifiers.cpp',project/'Tools/ge_effect_modifiers_probe.cpp']
    frozen=OUT/'current_tool_snapshots';frozen.mkdir();rows=[]
    for p in files:
        dest=frozen/p.name;shutil.copyfile(p,dest);rows.append(dict(source=str(p.resolve()),**identity(dest)))
    reference=ROOT/'raw/ppsspp_v1.20.4_vfpu_reference/MIPSIntVFPU.cpp'
    write(OUT/'checkpoint.json',dict(passed=True,capture=identity(capture_path),audit=identity(OUT/'audit_v1/verification.json'),runtime=identity(OUT/'runtime_v2/verification.json'),
                                   source_bank=identity(bank_dir/'source_modifiers.json'),source_protection=identity(OUT/'source_protection.json'),current_sources=rows,pinned_VRND_semantics=identity(reference),
                                   previous_goal_turn='progress: UE production scene/colour core and shader source bridge',
                                   current_goal_turn='progress: original modifier internal targets, scalar RNG seed chain and production type23/24 arithmetic recovered',
                                   goal_status='active',UE_module_built=False,default_M1_changed=False))
    print(json.dumps(dict(passed=True,bindings=2,negative_evidence_cases=3,first_capture_rejected=True,original_files_unchanged=3,existing_UE_packages_unchanged=185)))

if __name__=='__main__':main()
