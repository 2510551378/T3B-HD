"""Run production vector state core against original callbacks and synthetic opcode paths."""
import argparse,copy,json,shutil,struct,subprocess
from pathlib import Path
from analyze_fx_node_time import bits,check,identity,read,sidecar
from analyze_fx_vector_curve import make_machine

KINDS={'vector_key':1,'vector_wrap':2,'vector_evaluate':3}
def synthetic(operation,name,t,old_time):
    op=copy.deepcopy(operation);op.update(name=name,synthetic=True)
    op['state_bits']=[bits(v)for v in(5.,-2.,3.,7.,1.25,-3.5,9.,1.5,2.25,5.5,-4.,-0.5,1.125,-2.75,3.5,0.25)]
    op['previous_key_bits']=[bits(v)for v in(8.,-9.,5.,1.75,2.5,-3.,4.,-2.,1.5)]
    op['current_key_bits']=[bits(v)for v in(6.,2.,-1.,-0.5,3.25,7.,1.25,-4.,2.75)]
    op['relative_time_bits']=bits(t);op['previous_relative_time_bits']=bits(old_time)
    if 'signed_zero'in name:
        op['state_bits']=[bits(-0.0 if i&1 else 0.0)for i in range(16)];op['previous_key_bits']=[bits(-0.0)]*9;op['current_key_bits']=[bits(0.0)]*9
    capture=read(Path(op['capture']['file']));row=capture['rows'][op['capture_row']]
    if 'state_series_index'in op:
        call=capture['vectorStateSeries'][op['state_series_index']];entry=call['entry'];snapshot=entry['snapshot'];start=entry['stop']['pc'];stop=call['return']['stop']['pc']
        if op['kind']=='vector_wrap':row=dict(row,record=call['currentRecord'],oldRecord=call['previousRecord'])
    elif 'evaluation_series_index'in op:
        call=capture['vectorEvaluations'][op['evaluation_series_index']];entry=call['entry'];snapshot=entry['snapshot'];start=0x08b94438;stop=call['return']['stop']['pc']
    elif op['kind']=='vector_evaluate':entry=next(s for s in row['vector']['stages']if s['stage']=='evaluate_entry');snapshot=entry['snapshot'];start=0x08b94438;stop=0x08b944e4
    else:entry=row['entry'];snapshot=entry['before'];start=row['target'];stop=row['return']['stop']['pc']
    module=Path(capture['module']['file']).read_bytes();vm=make_machine(module,row,entry,snapshot);base=row['parameterAddress']
    for i,w in enumerate(op['state_bits']):vm.memory[base+i*4]=w
    # Actual wrap may pass the same record as new and old. Give synthetic
    # different-key cases two explicit regions rather than overwriting aliases.
    new_record,old_record=0x08100100,0x08100200
    vm.retain(new_record,sidecar(row['record']['raw']));vm.retain(old_record,sidecar(row['oldRecord']['raw']));vm.g[6]=new_record;vm.g[8]=old_record
    for address,key in [(new_record,'current_key_bits'),(old_record,'previous_key_bits')]:
        for group in range(3):
            for axis in range(3):vm.memory[address+group*16+axis*4]=op[key][group*3+axis]
    vm.f[12]=op['relative_time_bits'];vm.f[13]=op['previous_relative_time_bits'];vm.run_checked(start,stop)
    op['expected_bits']=[vm.load(base+i*4)for i in range(16)];op['trace']=vm.trace;return op

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in('audit','compiler','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();check(not a.out.exists(),'Never overwrite vector runtime proof');a.out.mkdir(parents=True);proof=read(a.audit);check(proof['passed']and proof['actual_operations']>=7,'Wrong vector audit coverage');actual_count=proof['actual_operations']
    ops=[dict(o,name='actual_%s_%d'%(o['kind'],i),synthetic=False)for i,o in enumerate(proof['operations'])]
    templates={kind:next(o for o in ops if o['kind']==kind)for kind in KINDS}
    for kind,cases in [('vector_key',[('fractional',.375,0),('negative_time',-1.25,0),('signed_zero',0.,0)]),
                       ('vector_wrap',[('fractional',.375,2.5),('zero_new_time',0.,2.),('negative_time',-.25,1.75)]),
                       ('vector_evaluate',[('fractional',.375,0),('negative_time',-.5,0),('zero_time',0.,0),('nonzero_W',2.,0)])]:
        for name,t,old in cases:ops.append(synthetic(templates[kind],'synthetic_'+kind+'_'+name,t,old))
    raw=bytearray(b'T3BVEC1\0'+struct.pack('<I',len(ops)));expected=bytearray()
    for o in ops:
        raw.extend(struct.pack('<I',KINDS[o['kind']])+struct.pack('<16I',*o['state_bits'])+struct.pack('<18I',*(o['previous_key_bits']+o['current_key_bits']))+struct.pack('<2I',o['relative_time_bits'],o['previous_relative_time_bits']))
        expected.extend(struct.pack('<16I',*o['expected_bits']))
    inp=a.out/'inputs.bin';ref=a.out/'original_opcode_expected.bin';inp.write_bytes(raw);ref.write_bytes(expected);(a.out/'operations.json').write_text(json.dumps(ops,indent=2),encoding='utf-8')
    project=Path(__file__).resolve().parents[2]/'t3b_unreal';files=[project/'Source/T3BRemake/Private/T3BGEEffectVectorCurve.cpp',project/'Source/T3BRemake/Public/T3BGEEffectVectorCurve.h',project/'Tools/ge_effect_vector_probe.cpp',Path(__file__)];sources=[]
    for source in files:
        dest=a.out/source.name;shutil.copyfile(source,dest);sources.append(dict(source=str(source.resolve()),**identity(dest)))
    exe=a.out/'ge_effect_vector_probe.exe';cmd=[str(a.compiler),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-I'+str(a.out),str(a.out/'ge_effect_vector_probe.cpp'),str(a.out/'T3BGEEffectVectorCurve.cpp'),'-o',str(exe)]
    build=subprocess.run(cmd,capture_output=True);(a.out/'build_stdout.log').write_bytes(build.stdout);(a.out/'build_stderr.log').write_bytes(build.stderr)
    request=dict(audit=identity(a.audit),sources=sources,compiler=identity(a.compiler),build_command=cmd,build_exit=build.returncode,input=identity(inp),expected=identity(ref));(a.out/'request.json').write_text(json.dumps(request,indent=2),encoding='utf-8');check(build.returncode==0,'Vector core compile failed')
    out=a.out/'runtime_output.bin';cmd=[str(exe),str(inp),str(out)];run=subprocess.run(cmd,capture_output=True);(a.out/'stdout.log').write_bytes(run.stdout);(a.out/'stderr.log').write_bytes(run.stderr)
    request.update(command=cmd,executable=identity(exe),exit_code=run.returncode);(a.out/'request.json').write_text(json.dumps(request,indent=2),encoding='utf-8');check(run.returncode==0,'Vector core execution failed')
    wrong=[o['name']for i,o in enumerate(ops)if out.read_bytes()[i*64:(i+1)*64]!=expected[i*64:(i+1)*64]];check(not wrong,'Vector production differs from original opcodes: '+str(wrong))
    rejected=[]
    for label,offset,value in [('bad_magic',0,0),('bad_kind',12,99),('nonfinite_state',16,0x7fc00000),('nonfinite_time',152,0x7f800000)]:
        bad=bytearray(raw);struct.pack_into('<I',bad,offset,value);file=a.out/(label+'.bin');file.write_bytes(bad);output=a.out/(label+'.out');r=subprocess.run([str(exe),str(file),str(output)],capture_output=True);check(r.returncode!=0 and not output.exists(),'Bad vector input accepted: '+label);rejected.append(dict(case=label,exit_code=r.returncode,error=r.stderr.decode('utf-8').strip()))
    for label,bad in [('truncated',raw[:-1]),('trailing',raw+b'\0')]:
        file=a.out/(label+'.bin');file.write_bytes(bad);output=a.out/(label+'.out');r=subprocess.run([str(exe),str(file),str(output)],capture_output=True);check(r.returncode!=0 and not output.exists(),'Bad vector extent accepted');rejected.append(dict(case=label,exit_code=r.returncode))
    result=dict(passed=True,request=identity(a.out/'request.json'),runtime_output=identity(out),actual_operations=actual_count,actual_state_F32_components=16*actual_count,synthetic_opcode_cases=10,
                invalid_inputs=rejected,all_output_bytes_equal=True,formal_UE_module_built=False,authored_clock_seconds_confirmed=False)
    (a.out/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,actual_operations=actual_count,F32_components=16*actual_count,synthetic_cases=10,invalid_inputs=len(rejected))))

if __name__=='__main__':main()
