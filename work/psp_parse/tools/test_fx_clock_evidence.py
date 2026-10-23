"""Synthetic corrupt-evidence controls for the actual FX clock auditor."""
import argparse
import copy
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from analyze_fx_node_time import bits, check, identity, read, sha


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();check(not args.out.exists(),'Never replace counterexample evidence')
    args.out.mkdir(parents=True)
    source=read(args.capture);results=[]
    for name,gate in [('changed_next_field','Actual subsequent field differs from original store'),
                      ('changed_effective_delta','Original clock arithmetic differs from actual store source'),
                      ('changed_live_interval','Live loop range differs from original asset')]:
        root=args.out/name;root.mkdir();r=copy.deepcopy(source)
        for filename in ('executed_trace_fx_node_time_writes.js','process_completed.json'):
            shutil.copyfile(args.capture.parent/filename,root/filename)
        def replace(item,raw,filename):
            retained=root/filename;retained.write_bytes(raw)
            item.update(file=str(retained.resolve()),bytes=len(raw),sha256=sha(raw))
        if name=='changed_next_field':
            b=r['rows'][1]['before'];raw=bytearray(Path(b['node']['file']).read_bytes())
            struct.pack_into('<I',raw,0x30,bits(3));replace(b['node'],raw,'changed_node.bin');b['timeBits']=bits(3)
            r['rows'][0]['nextObservation']['before']=copy.deepcopy(b)
        elif name=='changed_effective_delta':
            row=r['rows'][0];item=row['allRegisters'];reg=read(Path(item['file']))
            next(c for c in reg['categories']if c['name']=='FPU')['uintValues'][22]=bits(2)
            replace(item,json.dumps(reg).encode('utf-8'),'changed_registers.json')
            item=row['before']['state'];raw=bytearray(Path(item['file']).read_bytes())
            struct.pack_into('<I',raw,0x130,bits(2));replace(item,raw,'changed_state.bin')
        else:
            item=r['rows'][0]['before']['descriptor'];raw=bytearray(Path(item['file']).read_bytes())
            struct.pack_into('<H',raw,0xc,1);replace(item,raw,'changed_descriptor.bin')
        capture=root/'fx_node_time_writes.json';capture.write_text(json.dumps(r,indent=2),encoding='utf-8')
        command=[sys.executable,'-X','utf8',str(Path(__file__).with_name('analyze_fx_node_time.py')),
                 '--capture',str(capture),'--out',str(root/'rejected_audit')]
        result=subprocess.run(command,capture_output=True)
        (root/'stdout.log').write_bytes(result.stdout);(root/'stderr.log').write_bytes(result.stderr)
        check(result.returncode!=0 and gate in result.stderr.decode('utf-8'),'Did not reject at expected gate: '+name)
        results.append(dict(case=name,classification='synthetic corrupted evidence',expected_gate=gate,
                            exit_code=result.returncode,capture=identity(capture),command=command))
    report=dict(passed=True,producer=identity(Path(__file__)),source_capture=identity(args.capture),cases=results)
    (args.out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,independent_gates_rejected=len(results))))


if __name__=='__main__':main()
