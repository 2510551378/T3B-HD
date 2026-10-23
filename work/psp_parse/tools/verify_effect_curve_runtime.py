"""Execute production type155 curve transitions against actual and original-opcode references."""
import argparse
import copy
import json
import shutil
import struct
import subprocess
from pathlib import Path

from analyze_fx_node_time import bits,check,identity,read,sha,sidecar
from analyze_fx_property_callbacks import replay155


def packet(ops):
    return b'T3BCV1\0\0'+struct.pack('<I',len(ops))+b''.join(struct.pack('<21I',
        int(o['mode']=='reset'),o['relative_time_bits'],o['previous_relative_time_bits'],
        *o['state_bits'],*o['previous_key_bits'],*o['current_key_bits'])for o in ops)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--proof',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();check(not args.out.exists(),'Never replace production curve evidence');args.out.mkdir(parents=True)
    proof=read(args.proof);check(proof['passed']and proof['type155_operations']==4,'Missing actual curve transitions')
    check(identity(Path(proof['producer']['file']))==proof['producer'],'Property auditor changed')
    actual=[];templates={}
    for c in proof['captures']:
        check(identity(Path(c['capture']['file']))==c['capture'],'Actual property capture changed')
        capture=read(Path(c['capture']['file']))
        actual.extend(c['operations'])
        templates[c['mode']]=next(r for r in capture['rows']if r['type']==155)
    module=Path(capture['module']['file']).read_bytes()
    check(sha(module)==capture['module']['sha256'],'Original callback module changed')
    # Numeric cases change operands only; expected bytes come from the same
    # independently executed original words, not the production formulas.
    state=[1.25,-2.5,3,-4,0.25,0.5];previous=[0,-1,1,2,0.125,-0.25];current=[2,3,4,5,1,-2]
    cases=[('fractional_key','key',0.5,2.5,state,previous,current),
           ('fractional_wrap','reset',0.25,2.5,state,previous,current),
           ('range_edges','reset',0,0,[-0.25,4096.25,0,0,0,0],[0]*6,[0]*6),
           ('large_negative_original_trunc','reset',0,0,[-8192.25,8192.25,0,0,0,0],[0]*6,[0]*6),
           ('key_cancellation','key',3.75,2,[16777216,-16777216,1.125,-1.125,0.125,-0.125],previous,current),
           ('wrap_acceleration','reset',1.75,4.5,state,previous,current),
           ('key_signed_zero','key',-0.0,0,[-0.0]*6,[0]*6,[0]*6),
           ('large_float_wrap','reset',0,0,[5e9,-5e9,0,0,0,0],[0]*6,[0]*6)]
    synthetic=[];fixture_root=args.out/'synthetic_original_instruction_inputs';fixture_root.mkdir()
    for name,mode,t,oldtime,s,old,new in cases:
        folder=fixture_root/name;folder.mkdir();row=copy.deepcopy(templates[mode])
        def retained(name,raw):
            path=folder/name;path.write_bytes(raw);return dict(file=str(path.resolve()),bytes=len(raw),sha256=sha(raw))
        op=dict(mode=mode,state_bits=list(map(bits,s)),previous_key_bits=list(map(bits,old)),current_key_bits=list(map(bits,new)),
                relative_time_bits=bits(t),previous_relative_time_bits=bits(oldtime),classification='synthetic numeric operands',case=name)
        pw=row['entry']['before']['parameterWindow'];raw=bytearray(sidecar(pw['raw']));offset=row['parameterAddress']-pw['address']
        struct.pack_into('<6I',raw,offset+8,*op['state_bits']);pw['raw']=retained('parameter_window.bin',raw)
        for key,address,values in [('record',0x0b000000,op['current_key_bits']),('oldRecord',0x0b001000,op['previous_key_bits'])]:
            item=row[key];raw=bytearray(sidecar(item['raw']));struct.pack_into('<6I',raw,0x10,*values)
            item['address']=address;item['raw']=retained(key+'.bin',raw)
        regs=json.loads(sidecar(row['entry']['allRegisters']));g=next(c['uintValues']for c in regs['categories']if c['name']=='GPR')
        f=next(c['uintValues']for c in regs['categories']if c['name']=='FPU')
        g[6],g[8]=row['record']['address'],row['oldRecord']['address'];f[12],f[13]=bits(t),bits(oldtime)
        row['entry']['allRegisters']=retained('registers.json',json.dumps(regs).encode('utf-8'))
        predicted=replay155(module,row,reference_only=True)
        op['expected_bits']=list(struct.unpack_from('<6I',predicted,offset+8));synthetic.append(op)
        (folder/'synthetic_input.json').write_text(json.dumps(row,indent=2),encoding='utf-8')
    project=Path(__file__).resolve().parents[2]/'t3b_unreal';public=project/'Source/T3BRemake/Public'
    sources=[project/'Source/T3BRemake/Private/T3BGEEffectCurve.cpp',project/'Tools/ge_effect_curve_probe.cpp']
    snapshot=args.out/'executed_source_snapshot';snapshot.mkdir();inventory=[]
    for source in sources+[public/'T3BGEEffectCurve.h',Path(__file__),Path(__file__).with_name('analyze_fx_property_callbacks.py'),Path(__file__).with_name('analyze_fx_node_time.py')]:
        target=snapshot/source.name;shutil.copyfile(source,target);inventory.append(dict(**identity(source),retained_copy=str(target.resolve())))
    exe=args.out/'ge_effect_curve_probe.exe'
    build=['C:\\Strawberry\\c\\bin\\g++.exe','-std=c++17','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off',
           '-I'+str(public),*map(str,sources),'-o',str(exe)]
    process=subprocess.run(build,capture_output=True)
    (args.out/'build_stdout.log').write_bytes(process.stdout);(args.out/'build_stderr.log').write_bytes(process.stderr)
    check(process.returncode==0,'Production curve build failed')
    runs=[]
    for name,ops in [('actual',actual),('synthetic',synthetic)]:
        inputs,reference,output=(args.out/(name+s)for s in ('_inputs.bin','_expected.bin','_output.bin'))
        inputs.write_bytes(packet(ops));reference.write_bytes(b''.join(struct.pack('<6I',*o['expected_bits'])for o in ops))
        command=[str(exe),str(inputs),str(output)];process=subprocess.run(command,capture_output=True)
        (args.out/(name+'_stdout.log')).write_bytes(process.stdout);(args.out/(name+'_stderr.log')).write_bytes(process.stderr)
        check(process.returncode==0,'Production curve execution failed: '+name)
        check(output.read_bytes()==reference.read_bytes(),'Production curve differs from original output: '+name)
        runs.append(dict(classification=name,operations=len(ops),F32_components=len(ops)*6,inputs=identity(inputs),reference=identity(reference),
                         output=identity(output),command=command,all_F32_bits_equal=True))
    unknown=bytearray(packet(actual[:1]));struct.pack_into('<I',unknown,12,99)
    nonfinite=bytearray(packet(actual[:1]));struct.pack_into('<I',nonfinite,24,0x7f800000)
    too_large=copy.deepcopy(synthetic[2]);too_large['state_bits'][0]=bits(1e20)
    negatives=[]
    for name,raw in [('truncated',packet(actual)[:-1]),('trailing',packet(actual)+b'\0'),('unsupported',unknown),
                     ('nonfinite',nonfinite),('outside_normalize_trunc',packet([too_large]))]:
        path=args.out/('negative_'+name+'.bin');path.write_bytes(raw)
        process=subprocess.run([str(exe),str(path),str(args.out/('negative_'+name+'.output'))],capture_output=True)
        check(process.returncode!=0,'Invalid curve input accepted: '+name)
        negatives.append(dict(case=name,exit_code=process.returncode,diagnostic=process.stderr.decode('utf-8',errors='replace').strip()))
    for item in inventory:
        check(identity(Path(item['file']))['sha256']==item['sha256']==identity(Path(item['retained_copy']))['sha256'],'Source changed during execution')
    report=dict(schema='production-original-effect-curve-proof/v1',passed=True,proof=identity(args.proof),actual_executable=identity(exe),
                build_command=build,source_inventory=inventory,runs=runs,synthetic_fixtures=synthetic,negative_controls=negatives,
                actual_UE_module_executed=False,default_M1_binding_replaced=False,full_FX_lifecycle_verified=False,
                limits=['Only type155 six scalar fields are implemented; other classes retain verified bindings without inferred behavior.',
                        'Actual inputs cover one key transition and three loop callbacks. Fractional/nonzero acceleration cases are explicitly synthetic.',
                        'Record/timeline selection, material interpretation, original events, seconds conversion and formal UE integration remain external.'])
    (args.out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,actual_operations=len(actual),actual_F32_components=len(actual)*6,synthetic_operations=len(synthetic),rejected_controls=len(negatives))))


if __name__=='__main__':main()
