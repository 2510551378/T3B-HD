"""Execute modifier -> live evaluate/wrap sequence with one initial state only."""
import argparse,json,shutil,struct,subprocess
from pathlib import Path
from analyze_fx_node_time import check,read,identity

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in('vectors','modifiers','compiler','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();check(not a.out.exists(),'Never overwrite continuous-state proof');a.out.mkdir(parents=True);v=read(a.vectors);m=read(a.modifiers)
    check(v['passed']and m['passed'],'Unverified continuous inputs');steps=[o for o in v['operations']if 'state_series_index'in o];modifier=next(o for o in m['operations']if o['type']==23)
    check(len(steps)==6 and [o['state_series_index']for o in steps]==list(range(6)),'Expected exact live6 transitions')
    check(all(o['capture']==modifier['capture']for o in steps),'Sequence mixes separate captures')
    check(modifier['expected_after_bits']==steps[0]['state_bits'],'Original random output does not feed sequence')
    for left,right in zip(steps,steps[1:]):check(left['expected_bits']==right['state_bits'],'Original state carry differs')
    raw=bytearray(b'T3BVCH1\0'+struct.pack('<I',len(steps))+struct.pack('<16I',*modifier['before_bits']))
    for c in modifier['channels']:raw.extend(struct.pack('<2I',c['enabled'],c['mode'])+struct.pack('<3I',*c['amplitude_bits']))
    raw.extend(struct.pack('<9I',*[value for c in modifier['channels']for value in c['observed_VRNDF2_bits']])+struct.pack('<3I',*modifier['vector_center_bits']))
    expected=bytearray(struct.pack('<16I',*modifier['expected_after_bits']))
    for o in steps:
        raw.extend(struct.pack('<3I',1 if o['kind']=='vector_evaluate'else 2,o['relative_time_bits'],o['previous_relative_time_bits'])+struct.pack('<18I',*(o['previous_key_bits']+o['current_key_bits'])));expected.extend(struct.pack('<16I',*o['expected_bits']))
    inp=a.out/'continuous_inputs.bin';inp.write_bytes(raw);reference=a.out/'original_continuous_states.bin';reference.write_bytes(expected)
    project=Path(__file__).resolve().parents[2]/'t3b_unreal';files=[project/'Tools/ge_effect_vector_chain_probe.cpp']+[project/'Source/T3BRemake'/folder/name for folder,names in [('Private',['T3BGEEffectVectorCurve.cpp','T3BGEEffectModifiers.cpp']),('Public',['T3BGEEffectVectorCurve.h','T3BGEEffectModifiers.h'])]for name in names]+[Path(__file__)];sources=[]
    for source in files:
        dest=a.out/source.name;shutil.copyfile(source,dest);sources.append(dict(source=str(source.resolve()),**identity(dest)))
    exe=a.out/'ge_effect_vector_chain_probe.exe';cmd=[str(a.compiler),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-I'+str(a.out),str(a.out/'ge_effect_vector_chain_probe.cpp'),str(a.out/'T3BGEEffectVectorCurve.cpp'),str(a.out/'T3BGEEffectModifiers.cpp'),'-o',str(exe)]
    build=subprocess.run(cmd,capture_output=True);(a.out/'build_stdout.log').write_bytes(build.stdout);(a.out/'build_stderr.log').write_bytes(build.stderr);check(build.returncode==0,'Continuous core build failed')
    output=a.out/'runtime_states.bin';command=[str(exe),str(inp),str(output)];run=subprocess.run(command,capture_output=True);(a.out/'stdout.log').write_bytes(run.stdout);(a.out/'stderr.log').write_bytes(run.stderr);check(run.returncode==0,'Continuous core execution failed')
    check(output.read_bytes()==expected,'Production continuous state differs from same-node original sequence')
    report=dict(passed=True,vectors=identity(a.vectors),modifiers=identity(a.modifiers),sources=sources,build_command=cmd,build_exit_code=build.returncode,command=command,exit_code=run.returncode,executable=identity(exe),
                inputs=identity(inp),reference=identity(reference),runtime_output=identity(output),live_steps=6,state_snapshots_loaded=1,verified_state_vectors=7,verified_F32_components=112,
                sequence=[dict(kind=o['kind'],relative_time_bits=o['relative_time_bits'],previous_relative_time_bits=o['previous_relative_time_bits'],output_bits=o['expected_bits'])for o in steps],
                all_bytes_equal=True,VFPU_RCX_seed_recovered=False,source_time_seconds_recovered=False,UE_module_built=False,default_M1_replaced=False)
    (a.out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,live_steps=6,loaded_initial_states=1,all7_state_vectors_equal=True)))

if __name__=='__main__':main()
