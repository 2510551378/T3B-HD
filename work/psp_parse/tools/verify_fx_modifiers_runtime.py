"""Execute production modifiers against actual writes and explicit original-opcode cases."""
import argparse,copy,json,shutil,struct,subprocess
from pathlib import Path
from analyze_fx_node_time import check,read,identity,bits,u32,sidecar
from replay_fx_random_modifiers import Machine
from verify_weapon_ge_matrix_math import vindices

def overwrite(machine,address,raw):
    for i,b in enumerate(raw):machine.memory[address+i]=b

def synthetic(row,module,name,mode,independent=False,disabled=False):
    m=Machine(module,row);r=row['random'];base=r['resolvedBase'];start=0 if row['type']==23 else 16
    case=dict(type=row['type'],name=name,synthetic=True,independent_axes=independent,seed_before=0x87654321,seed_after=0,
              before_bits=[bits(x)for x in(1.,2.,3.,4.,10.,20.,30.,40.,50.,60.,70.,80.,90.,100.,110.,120.)],
              channels=[dict(enabled=not disabled,mode=mode,amplitude_bits=[bits(x)for x in(5.25,8.5,13.75)],observed_VRNDF2_bits=[bits(2.25),bits(3.),bits(3.75)])for _ in range(3)],
              vector_center_bits=[bits(3.)]*3)
    overwrite(m,base,struct.pack('<16I',*case['before_bits']));tables=sidecar(r['tables']['raw']);address=row['record']['address']
    for k,c in enumerate(case['channels']):
        overwrite(m,address+tables[start+k],bytes([int(c['enabled'])]));overwrite(m,address+tables[start+3+k],bytes([mode]))
        overwrite(m,address+tables[start+6+k],struct.pack('<3I',*c['amplitude_bits']))
    # Independent-axis flag is distinct from the per-channel enable/mode bytes.
    if row['type']==24:
        overwrite(m,address+12,bytes([int(independent)]));seed_address=m.rng[0]['entry']['seed']['address'];overwrite(m,seed_address,struct.pack('<I',case['seed_before']))
    else:
        case['seed_before']=0;overwrite(m,r['vectorCache']['address'],struct.pack('<5I',*case['vector_center_bits'],0,1));m.vrnd={}
        for c in case['channels']:
            if not c['enabled']:continue
            pc=0x08bb8eb8 if mode==1 else 0x08bb8f64 if mode==2 else 0x08bb8e20;v=list(m.v)
            for index,value in zip(vindices(0,3),c['observed_VRNDF2_bits']):v[index]=value
            m.vrnd.setdefault(pc,[]).append(v)
    result=m.run(reference_only=True);case['expected_after_bits']=[m.load(base+i*4)for i in range(16)]
    if row['type']==24:case['seed_after']=m.load(seed_address)
    return case,result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in('audit','capture','compiler','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();check(not a.out.exists(),'Never overwrite runtime evidence');a.out.mkdir(parents=True)
    proof=read(a.audit);capture=read(a.capture);check(proof['passed']and identity(a.capture)==proof['source_capture'],'Actual modifier audit changed')
    module=Path(capture['module']['file']).read_bytes();ops=[];traces=[]
    for operation in proof['operations']:
        op=copy.deepcopy(operation);op.update(name='actual_type%d'%op['type'],synthetic=False);ops.append(op)
        row=next(r for r in capture['rows']if r['type']==op['type'])
        for mode in(0,1,2,255):
            for independent in((False,True)if op['type']==24 else(False,)):
                case,trace=synthetic(row,module,'synthetic_type%d_mode%d_axes%d'%(op['type'],mode,independent),mode,independent);ops.append(case);traces.append(dict(case=case['name'],replay=trace))
        case,trace=synthetic(row,module,'synthetic_type%d_disabled'%op['type'],0,disabled=True);ops.append(case);traces.append(dict(case=case['name'],replay=trace))
    data=bytearray(b'T3BMDO1\0'+struct.pack('<I',len(ops)));expected=bytearray()
    for op in ops:
        data.extend(struct.pack('<3I',op['type'],op['independent_axes'],op['seed_before'])+struct.pack('<16I',*op['before_bits']))
        for c in op['channels']:data.extend(struct.pack('<2I',c['enabled'],c['mode'])+struct.pack('<3I',*c['amplitude_bits']))
        data.extend(struct.pack('<9I',*[v for c in op['channels']for v in c['observed_VRNDF2_bits']])+struct.pack('<3I',*op['vector_center_bits']))
        expected.extend(struct.pack('<16I',*op['expected_after_bits'])+struct.pack('<I',op['seed_after']))
    inp=a.out/'inputs.bin';ref=a.out/'original_opcode_expected.bin';inp.write_bytes(data);ref.write_bytes(expected)
    (a.out/'operations.json').write_text(json.dumps(dict(operations=ops,synthetic_opcode_traces=traces),indent=2),encoding='utf-8')
    project=Path(__file__).resolve().parents[2]/'t3b_unreal';files=[project/'Source/T3BRemake/Private/T3BGEEffectModifiers.cpp',project/'Source/T3BRemake/Public/T3BGEEffectModifiers.h',project/'Tools/ge_effect_modifiers_probe.cpp',Path(__file__)]
    sources=[]
    for source in files:
        dest=a.out/source.name;shutil.copyfile(source,dest);sources.append(dict(source=str(source.resolve()),**identity(dest)))
    exe=a.out/'ge_effect_modifiers_probe.exe';cmd=[str(a.compiler),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-I'+str(a.out),str(a.out/'ge_effect_modifiers_probe.cpp'),str(a.out/'T3BGEEffectModifiers.cpp'),'-o',str(exe)]
    build=subprocess.run(cmd,capture_output=True);(a.out/'build_stdout.log').write_bytes(build.stdout);(a.out/'build_stderr.log').write_bytes(build.stderr)
    request=dict(audit=identity(a.audit),capture=identity(a.capture),sources=sources,build_command=cmd,build_exit=build.returncode,input=identity(inp),expected=identity(ref))
    (a.out/'request.json').write_text(json.dumps(request,indent=2),encoding='utf-8');check(build.returncode==0,'Production modifier build failed')
    output=a.out/'runtime_output.bin';cmd=[str(exe),str(inp),str(output)];run=subprocess.run(cmd,capture_output=True);(a.out/'stdout.log').write_bytes(run.stdout);(a.out/'stderr.log').write_bytes(run.stderr)
    request.update(command=cmd,executable=identity(exe),run_exit=run.returncode);(a.out/'request.json').write_text(json.dumps(request,indent=2),encoding='utf-8')
    check(run.returncode==0,'Actual production modifier execution failed')
    wrong=[ops[i]['name']for i in range(len(ops))if output.read_bytes()[i*68:(i+1)*68]!=expected[i*68:(i+1)*68]]
    check(not wrong,'Production differs from original instructions: '+str(wrong))
    cases=[]
    for label,offset,value in [('bad_type',12,22),('bad_axis_flag',16,2),('nonfinite_target',24,0x7fc00000),('missing_VRNDF2',148,bits(1.5))]:
        bad=bytearray(data);struct.pack_into('<I',bad,offset,value);file=a.out/(label+'.bin');file.write_bytes(bad);o=a.out/(label+'.out');r=subprocess.run([str(exe),str(file),str(o)],capture_output=True)
        check(r.returncode!=0 and not o.exists(),'Bad modifier interface accepted: '+label);cases.append(dict(case=label,exit_code=r.returncode,error=r.stderr.decode('utf-8').strip()))
    for label,bad in [('truncated',data[:-1]),('trailing',data+b'\0')]:
        file=a.out/(label+'.bin');file.write_bytes(bad);o=a.out/(label+'.out');r=subprocess.run([str(exe),str(file),str(o)],capture_output=True);check(r.returncode!=0 and not o.exists(),'Bad modifier extent accepted');cases.append(dict(case=label,exit_code=r.returncode))
    report=dict(passed=True,request=identity(a.out/'request.json'),runtime_output=identity(output),expected=identity(ref),actual_callbacks=2,actual_target_float_components=32,
                synthetic_original_opcode_cases=len(traces),invalid_inputs=cases,all_output_bytes_equal=True,UE_module_built=False,VFPU_RCX_seed_recovered=False)
    (a.out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,actual_callbacks=2,synthetic_opcode_cases=len(traces),invalid_inputs=len(cases))))

if __name__=='__main__':main()
