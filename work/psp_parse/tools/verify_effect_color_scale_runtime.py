"""Execute production RGBA/percent-scale cores against real return memory and opcode fixtures."""
import argparse
import copy
import json
import shutil
import struct
import subprocess
from pathlib import Path

from analyze_fx_node_time import bits,check,identity,read,sha,sidecar
from analyze_fx_color_scale import replay


KINDS={'color_key':0,'color_reset':1,'color_evaluate':2,'scale_key':3,'scale_reset':4}


def padded(values,n):
    check(len(values)<=n,'Oversized transport array');return values+[0]*(n-len(values))


def packet(ops):
    return b'T3BCS1\0\0'+struct.pack('<I',len(ops))+b''.join(struct.pack('<31I',KINDS[o['kind']],o['relative_time_bits'],o['previous_relative_time_bits'],
        *padded(o['state_bits'],12),*o['previous_key_bits'],*o['current_key_bits'])for o in ops)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--proof',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();check(not args.out.exists(),'Never replace color/scale execution proof');args.out.mkdir(parents=True)
    proof=read(args.proof);check(proof['passed']and proof['actual_operations']==11,'Missing original callback proof')
    for key in ('producer','oracle'):check(identity(Path(proof[key]['file']))==proof[key],'Auditor/oracle changed')
    actual=proof['operations'];templates={}
    for op in actual:
        check(identity(Path(op['capture']['file']))==op['capture'],'Actual capture changed')
        capture=read(Path(op['capture']['file']));row=copy.deepcopy(capture['rows'][op['capture_row']])
        if op['kind']=='color_evaluate':entry=row['nested']['entry'];before=entry['snapshot']
        else:entry=row['entry'];before=entry['before']
        templates[op['kind']]=(row,entry,before,capture)
    case_state=[99,99,99,99,-1,300,-0.0,128.25,3,-4,0,80]
    old=[10,20,30,40,1,2,3,4];new=[50,60,70,80,5,6,7,8]
    cases=[('color_fractional_evaluation','color_evaluate',0.5,0,case_state,[0]*8,[0]*8),
           ('color_zero_clamp_sign','color_evaluate',-0.0,0,[0]*4+[-0.0]*8,[0]*8,[0]*8),
           ('color_fractional_key','color_key',0.75,2,case_state,old,new),
           ('color_fractional_reset','color_reset',0.25,1.5,case_state,old,new),
           ('color_clamped_reset','color_reset',2,3,[0]*4+[-300,500,128,0]+[5,-6,7,8],old,new),
           ('color_key_cancellation','color_key',3.75,0,[0]*4+[1e7,-1e7,1.25,-1.25]+[0.125,-0.125,3,-4],old,new),
           ('scale_key_shared_W','scale_key',0,0,[2.4,1.5,2.5,17,240,150,250,23],[250,250,250,0,0,0,0,0],[100,200,300,0,0,0,0,0]),
           ('scale_roundtrip','scale_reset',0,0,[0.1234,1.5460344553,2.4855072498,19,-7,-7,-7,11],[0]*8,[0]*8),
           ('scale_reset_signed_zero','scale_reset',0,0,[-0.0,0,1e-20,-0.0,10,20,30,-0.0],[0]*8,[0]*8),
           ('scale_key_fractional','scale_key',0,0,[1,1,1,9,123.456,234.567,345.678,17],[100,200,300,0,0,0,0,0],[111.125,222.25,333.5,0,0,0,0,0])]
    synthetic=[];fixture_root=args.out/'synthetic_original_instruction_inputs';fixture_root.mkdir()
    for name,kind,t,previous_time,state,old_values,new_values in cases:
        row,entry,before,capture=copy.deepcopy(templates[kind]);folder=fixture_root/name;folder.mkdir()
        def retain(name,raw):
            path=folder/name;path.write_bytes(raw);return dict(file=str(path.resolve()),bytes=len(raw),sha256=sha(raw))
        op=dict(case=name,classification='synthetic finite/default-prefix original opcode operands',kind=kind,state_bits=list(map(bits,state)),
                previous_key_bits=list(map(bits,old_values)),current_key_bits=list(map(bits,new_values)),relative_time_bits=bits(t),previous_relative_time_bits=bits(previous_time))
        pw=before['parameterWindow'];raw=bytearray(sidecar(pw['raw']));offset=row['parameterAddress']-pw['address']
        struct.pack_into('<%dI'%len(state),raw,offset,*op['state_bits']);pw['raw']=retain('parameter_window.bin',raw)
        for field,address,values in [('record',0x0b000000,op['current_key_bits']),('oldRecord',0x0b001000,op['previous_key_bits'])]:
            item=row[field];raw=bytearray(sidecar(item['raw']));struct.pack_into('<8I',raw,0,*values)
            item['address']=address;item['raw']=retain(field+'.bin',raw)
        regs=json.loads(sidecar(entry['allRegisters']));g=next(c['uintValues']for c in regs['categories']if c['name']=='GPR');f=next(c['uintValues']for c in regs['categories']if c['name']=='FPU')
        g[6],g[8]=row['record']['address'],row['oldRecord']['address'];f[12],f[13]=bits(t),bits(previous_time)
        entry['allRegisters']=retain('registers.json',json.dumps(regs).encode('utf-8'))
        module=Path(capture['module']['file']).read_bytes();check(sha(module)==capture['module']['sha256'],'Original module changed')
        vm,result=replay(module,row,entry,before,None)
        op['expected_bits']=list(struct.unpack_from('<%dI'%len(state),result,offset));op['original_instruction_trace']=vm.trace;synthetic.append(op)
        (folder/'synthetic_inputs.json').write_text(json.dumps(dict(row=row,entry=entry,before=before),indent=2),encoding='utf-8')
    project=Path(__file__).resolve().parents[2]/'t3b_unreal';public=project/'Source/T3BRemake/Public'
    sources=[project/'Source/T3BRemake/Private/T3BGEEffectColorScale.cpp',project/'Tools/ge_effect_color_scale_probe.cpp']
    snapshot=args.out/'executed_source_snapshot';snapshot.mkdir();inventory=[]
    for source in sources+[public/'T3BGEEffectColorScale.h',Path(__file__)]+[Path(__file__).with_name(n)for n in ('analyze_fx_color_scale.py','replay_fx_color_scale.py','analyze_fx_node_time.py','analyze_fx_property_callbacks.py','verify_weapon_ge_matrix_math.py')]:
        target=snapshot/source.name;shutil.copyfile(source,target);inventory.append(dict(**identity(source),retained_copy=str(target.resolve())))
    exe=args.out/'ge_effect_color_scale_probe.exe';build=['C:\\Strawberry\\c\\bin\\g++.exe','-std=c++17','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off',
        '-I'+str(public),*map(str,sources),'-o',str(exe)]
    process=subprocess.run(build,capture_output=True)
    (args.out/'build_stdout.log').write_bytes(process.stdout);(args.out/'build_stderr.log').write_bytes(process.stderr)
    check(process.returncode==0,'Production color/scale build failed');runs=[]
    for name,ops in [('actual',actual),('synthetic',synthetic)]:
        inputs,reference,output=(args.out/(name+s)for s in ('_inputs.bin','_expected.bin','_output.bin'))
        inputs.write_bytes(packet(ops));reference.write_bytes(b''.join(struct.pack('<12I',*padded(o['expected_bits'],12))for o in ops))
        command=[str(exe),str(inputs),str(output)];process=subprocess.run(command,capture_output=True)
        (args.out/(name+'_stdout.log')).write_bytes(process.stdout);(args.out/(name+'_stderr.log')).write_bytes(process.stderr)
        check(process.returncode==0 and output.read_bytes()==reference.read_bytes(),'Production color/scale bits differ: '+name)
        runs.append(dict(classification=name,operations=len(ops),original_F32_components=sum(len(o['expected_bits'])for o in ops),
                         command=command,inputs=identity(inputs),reference=identity(reference),output=identity(output),all_output_bytes_equal=True))
    unknown=bytearray(packet(actual[:1]));struct.pack_into('<I',unknown,12,99)
    nonfinite=bytearray(packet(actual[:1]));struct.pack_into('<I',nonfinite,24,0x7f800000)
    negatives=[]
    for name,raw in [('truncated',packet(actual)[:-1]),('trailing',packet(actual)+b'\0'),('unsupported',unknown),('nonfinite',nonfinite),('zero_count',b'T3BCS1\0\0'+struct.pack('<I',0))]:
        path=args.out/('negative_'+name+'.bin');path.write_bytes(raw)
        process=subprocess.run([str(exe),str(path),str(args.out/('negative_'+name+'.output'))],capture_output=True)
        check(process.returncode!=0,'Invalid color/scale input accepted: '+name)
        negatives.append(dict(case=name,exit_code=process.returncode,diagnostic=process.stderr.decode('utf-8',errors='replace').strip()))
    for item in inventory:
        check(identity(Path(item['file']))['sha256']==item['sha256']==identity(Path(item['retained_copy']))['sha256'],'Source changed during compilation')
    report=dict(schema='production-original-effect-color-scale-proof/v1',passed=True,proof=identity(args.proof),actual_executable=identity(exe),
                build_command=build,source_inventory=inventory,runs=runs,synthetic_fixtures=synthetic,negative_controls=negatives,
                actual_UE_module_executed=False,default_M1_binding_replaced=False,full_FX_lifecycle_verified=False,
                all_entry_prefix_controls_directly_observed=False,
                limits=['Production implements finite/default-entry-prefix arithmetic; prefix provenance differs per actual case as recorded by the original auditor.',
                        'Scale transport pads four output floats with zeros; original comparison count excludes those padding fields.',
                        'Synthetic ramps, arbitrary alpha and different percentage keys are numeric fixtures, not additional original animation captures.'])
    (args.out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,actual_operations=len(actual),actual_F32_components=proof['F32_components'],synthetic_operations=len(synthetic),rejected_controls=len(negatives))))


if __name__=='__main__':main()
