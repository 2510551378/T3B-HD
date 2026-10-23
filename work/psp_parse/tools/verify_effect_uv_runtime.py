"""Run production curve evaluation/UV binding against six actual emitted command pairs."""
import argparse
import copy
import json
import shutil
import struct
import subprocess
from pathlib import Path

from analyze_fx_node_time import bits,check,identity,read
from analyze_fx_curve_uv_emissions import evaluate,normalize


def packet(ops):
    return b'T3BUV1\0\0'+struct.pack('<I',len(ops))+b''.join(struct.pack('<11I',
        o['relative_time_bits'],*o['state_bits'],o['width'],o['height'],*o['group_offset_bits'])for o in ops)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--proof',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();check(not args.out.exists(),'Never replace UV runtime evidence');args.out.mkdir(parents=True)
    proof=read(args.proof);check(proof['passed']and proof['actual_render_invocations']==6,'Missing original UV emissions')
    for k in ('producer','capture','module'):check(identity(Path(proof[k]['file']))==proof[k],'UV proof source changed')
    actual=proof['operations'];synthetic=[]
    cases=[('exact_dimensions',0,[64,32,0,0,0,0],[0,0]),
           ('negative_fraction',0,[-0.25,-0.25,0,0,0,0],[0,0]),
           ('negative_exact',0,[-64,-32,0,0,0,0],[0,0]),
           ('positive_multiples',0,[128,96,0,0,0,0],[0,0]),
           ('fractional_acceleration',1.25,[1.125,-2.25,3,-4,0.5,-0.25],[0.125,-0.25]),
           ('negative_time',-0.5,[1.125,-2.25,3,-4,0.5,-0.25],[0.125,-0.25]),
           ('signed_zero',-0.0,[-0.0,-0.0,-0.0,-0.0,-0.0,-0.0],[0,0]),
           ('F24_truncation',0,[21.333333333,7.11111111,0,0,0,0],[0.1,0.2])]
    for name,t,state,group in cases:
        o=dict(case=name,classification='synthetic numeric operands',relative_time_bits=bits(t),state_bits=list(map(bits,state)),width=64,height=32,group_offset_bits=list(map(bits,group)))
        o['expected_evaluation_bits']=evaluate(o['state_bits'],o['relative_time_bits'])
        o['expected_normalized_bits']=normalize(o['expected_evaluation_bits'],o['width'],o['height'],o['group_offset_bits'])
        o['expected_command_words']=[((0x4a+k)<<24)|(v>>8)for k,v in enumerate(o['expected_normalized_bits'])];synthetic.append(o)
    project=Path(__file__).resolve().parents[2]/'t3b_unreal';public=project/'Source/T3BRemake/Public'
    sources=[project/'Source/T3BRemake/Private/T3BGEEffectCurve.cpp',project/'Tools/ge_effect_uv_probe.cpp']
    snapshot=args.out/'executed_source_snapshot';snapshot.mkdir();inventory=[]
    for source in sources+[public/'T3BGEEffectCurve.h',Path(__file__),Path(__file__).with_name('analyze_fx_curve_uv_emissions.py'),Path(__file__).with_name('analyze_fx_node_time.py'),Path(__file__).with_name('analyze_fx_property_callbacks.py')]:
        target=snapshot/source.name;shutil.copyfile(source,target);inventory.append(dict(**identity(source),retained_copy=str(target.resolve())))
    exe=args.out/'ge_effect_uv_probe.exe';build=['C:\\Strawberry\\c\\bin\\g++.exe','-std=c++17','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off',
        '-I'+str(public),*map(str,sources),'-o',str(exe)]
    process=subprocess.run(build,capture_output=True)
    (args.out/'build_stdout.log').write_bytes(process.stdout);(args.out/'build_stderr.log').write_bytes(process.stderr)
    check(process.returncode==0,'Production UV core build failed');runs=[]
    for name,ops in [('actual',actual),('synthetic',synthetic)]:
        inputs,reference,output=(args.out/(name+s)for s in ('_inputs.bin','_expected.bin','_output.bin'))
        inputs.write_bytes(packet(ops));reference.write_bytes(b''.join(struct.pack('<6I',*o['expected_evaluation_bits'],*o['expected_normalized_bits'],*o['expected_command_words'])for o in ops))
        command=[str(exe),str(inputs),str(output)];process=subprocess.run(command,capture_output=True)
        (args.out/(name+'_stdout.log')).write_bytes(process.stdout);(args.out/(name+'_stderr.log')).write_bytes(process.stderr)
        check(process.returncode==0 and output.read_bytes()==reference.read_bytes(),'Production UV evaluation/normalization/commands differ: '+name)
        runs.append(dict(classification=name,operations=len(ops),F32_components=len(ops)*4,GE_words=len(ops)*2,command=command,
            inputs=identity(inputs),reference=identity(reference),output=identity(output),all_output_bytes_equal=True))
    bad_width=copy.deepcopy(actual[0]);bad_width['width']=0
    bad_nan=copy.deepcopy(actual[0]);bad_nan['state_bits'][0]=0x7fc00000
    no_progress=copy.deepcopy(actual[0]);no_progress['state_bits'][0]=bits(1e20)
    rejected=[]
    for name,raw in [('truncated',packet(actual)[:-1]),('trailing',packet(actual)+b'\0'),('zero_width',packet([bad_width])),
                     ('nonfinite',packet([bad_nan])),('normalization_no_progress',packet([no_progress]))]:
        path=args.out/('negative_'+name+'.bin');path.write_bytes(raw)
        process=subprocess.run([str(exe),str(path),str(args.out/('negative_'+name+'.output'))],capture_output=True)
        check(process.returncode!=0,'Invalid UV input accepted: '+name)
        rejected.append(dict(case=name,exit_code=process.returncode,diagnostic=process.stderr.decode('utf-8',errors='replace').strip()))
    for item in inventory:
        check(identity(Path(item['file']))['sha256']==item['sha256']==identity(Path(item['retained_copy']))['sha256'],'UV source changed during execution')
    report=dict(schema='production-original-effect-UV-proof/v1',passed=True,proof=identity(args.proof),build_command=build,source_inventory=inventory,
                actual_executable=identity(exe),runs=runs,synthetic_fixtures=synthetic,negative_controls=rejected,actual_UE_module_executed=False,
                default_M1_binding_replaced=False,new_GE_consumption_capture_verified=False,full_FX_lifecycle_verified=False,
                limits=['Actual evidence ends at CPU GE-command writes. No new GPU/GE dump or final-pixel comparison is claimed.',
                        'Float UV output must be packed to GE high24 before applying the existing source UV contract; do not add the same offset twice.',
                        'Six actual invocations are distinct render calls, not six independent firing actions or authored clips.'])
    (args.out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,actual_invocations=len(actual),actual_F32_components=len(actual)*4,actual_GE_words=len(actual)*2,
                         synthetic_operations=len(synthetic),rejected_controls=len(rejected))))


if __name__=='__main__':main()
