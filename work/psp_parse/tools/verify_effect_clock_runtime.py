"""Run the production clock core against actual write effects and synthetic opcode fixtures."""
import argparse
import json
import shutil
import struct
import subprocess
from pathlib import Path

from analyze_fx_node_time import bits, check, identity, number, read, replay_wrap


def packet(ops):
    return b'T3BCLK1\0'+struct.pack('<I',len(ops))+b''.join(
        struct.pack('<5I',o['kind'],o['a_bits'],o['b_bits'],o['x'],o['y']&0xffffffff)for o in ops)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    check(not args.out.exists(),'Never replace clock execution evidence')
    args.out.mkdir(parents=True)
    proof=read(args.proof)
    check(proof['passed'] and proof['completed_observed_store_effects']==8,'No verified original clock observations')
    for key in ('capture','executed_producer','module','FEP','producer'):
        check(identity(Path(proof[key]['file']))==proof[key],'Proof source changed: '+key)
    actual=proof['operations']
    check(len(actual)==9,'Expected eight effects and one actual dispatch observation')
    module=Path(proof['module']['file']).read_bytes()
    synthetic=[]
    # Invoke the independent interpreter of actual original instructions. These
    # are numeric fixtures, not additional runtime poses or lifecycle evidence.
    for t,start,end in ((2.25,0,2),(3.25,1,3),(17.75,3,7),(-2.25,0,2),
                        (0.25,0,2),(16777218.0,0,2),(-2147483648.0,0,2),
                        (65535.5,65533,65535),(2147483520.0,0,65535)):
        expected,trace=replay_wrap(module,bits(t),start,end)
        synthetic.append(dict(kind=1,a_bits=bits(t),b_bits=0,x=start,y=end,
                              expected_bits=expected,reference='original opcode interpreter',instruction_trace=trace))
    for t,has,start in ((2.25,1,-3),(2.25,1,32767),(-0.0,0,0),(-0.0,1,0)):
        expected=bits(number(bits(t))-start)if has else bits(t)
        synthetic.append(dict(kind=2,a_bits=bits(t),b_bits=0,x=has,y=start,
                              expected_bits=expected,reference='signed start F32 arithmetic; null record preserves bits'))
    project=Path(__file__).resolve().parents[2]/'t3b_unreal'
    public,private=project/'Source/T3BRemake/Public',project/'Source/T3BRemake/Private'
    sources=[private/'T3BGEEffectClock.cpp',project/'Tools/ge_effect_clock_probe.cpp']
    snapshot=args.out/'executed_source_snapshot';snapshot.mkdir()
    inventory=[]
    for p in sources+[public/'T3BGEEffectClock.h',Path(__file__),Path(__file__).with_name('analyze_fx_node_time.py')]:
        retained=snapshot/p.name;shutil.copyfile(p,retained)
        inventory.append(dict(**identity(p),retained_copy=str(retained.resolve())))
    exe=args.out/'ge_effect_clock_probe.exe'
    build=['C:\\Strawberry\\c\\bin\\g++.exe','-std=c++17','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off',
           '-I'+str(public),*map(str,sources),'-o',str(exe)]
    process=subprocess.run(build,capture_output=True)
    (args.out/'build_stdout.log').write_bytes(process.stdout)
    (args.out/'build_stderr.log').write_bytes(process.stderr)
    check(process.returncode==0,'Production clock build failed')
    results=[]
    for name,ops in (('actual',actual),('synthetic',synthetic)):
        inputs,expected,output=(args.out/(name+s)for s in ('_inputs.bin','_expected.bin','_output.bin'))
        inputs.write_bytes(packet(ops))
        expected.write_bytes(b''.join(struct.pack('<I',o['expected_bits'])for o in ops))
        command=[str(exe),str(inputs),str(output)]
        process=subprocess.run(command,capture_output=True)
        (args.out/(name+'_stdout.log')).write_bytes(process.stdout)
        (args.out/(name+'_stderr.log')).write_bytes(process.stderr)
        check(process.returncode==0,'Production clock execution failed: '+name)
        check(output.read_bytes()==expected.read_bytes(),'Clock bits differ from independent reference: '+name)
        results.append(dict(classification=name,operations=len(ops),inputs=identity(inputs),reference=identity(expected),
                            output=identity(output),command=command,all_F32_bits_equal=True))
    invalid_interval=dict(kind=1,a_bits=bits(2),b_bits=0,x=2,y=2)
    unsupported=dict(kind=99,a_bits=0,b_bits=0,x=0,y=0)
    nonfinite=dict(kind=0,a_bits=0x7f800000,b_bits=0,x=0,y=0)
    out_of_domain=dict(kind=1,a_bits=bits(2147483648.0),b_bits=0,x=0,y=2)
    negatives=[]
    cases=[('truncated',packet(actual)[:-1]),('trailing',packet(actual)+b'\0'),
           ('invalid_interval',packet([invalid_interval])),('unsupported',packet([unsupported])),
           ('nonfinite',packet([nonfinite])),('outside_trunc_domain',packet([out_of_domain]))]
    for name,raw in cases:
        p=args.out/('negative_'+name+'.bin');p.write_bytes(raw)
        process=subprocess.run([str(exe),str(p),str(args.out/('negative_'+name+'.output'))],capture_output=True)
        check(process.returncode!=0,'Invalid clock input accepted: '+name)
        negatives.append(dict(case=name,exit_code=process.returncode,diagnostic=process.stderr.decode('utf-8',errors='replace').strip()))
    for item in inventory:
        check(identity(Path(item['file']))['sha256']==item['sha256']==identity(Path(item['retained_copy']))['sha256'],
              'Executed clock source changed')
    report=dict(schema='production-original-effect-clock-proof/v1',passed=True,proof=identity(args.proof),
                actual_executable=identity(exe),build_command=build,source_inventory=inventory,runs=results,
                actual_observed_store_effects=8,actual_render_dispatch_observations=1,
                synthetic_fixtures=synthetic,negative_controls=negatives,
                full_FX_lifecycle_verified=False,seconds_to_source_units_verified=False,
                actual_UE_module_executed=False,default_M1_binding_replaced=False,
                limits=['Wrap begins after the original boundary callbacks; their side effects are not ported.',
                        'Actual samples use delta1 and integer times0/1/2; fractional and extreme cases are explicitly synthetic.',
                        'This standalone production core execution does not prove formal UE module loading or playable M1.'])
    (args.out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,actual_operations=len(actual),synthetic_operations=len(synthetic),
                          rejected_controls=len(negatives),all_F32_bits_equal=True)))


if __name__=='__main__':main()
