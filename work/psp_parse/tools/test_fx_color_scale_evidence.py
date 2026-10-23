"""Synthetic bad-evidence controls for original color/percent-scale return-memory auditing."""
import argparse
import copy
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from analyze_fx_node_time import bits,check,identity,read,sha,sidecar


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();check(not args.out.exists(),'Never replace corruption controls');args.out.mkdir(parents=True)
    original=read(args.capture);results=[]
    for name,gate in [('color_before_base','Original color/scale opcode replay differs from actual return memory'),
                      ('scale_return_W','Original color/scale opcode replay differs from actual return memory'),
                      ('nested_wrong_RA','Wrong nested color ABI')]:
        folder=args.out/name;folder.mkdir();r=copy.deepcopy(original)
        for filename in ('executed_trace_fx_property_callbacks.js','process_completed.json'):
            shutil.copyfile(args.capture.parent/filename,folder/filename)
        def replace(item,raw,name):
            path=folder/name;path.write_bytes(raw);item.update(file=str(path.resolve()),bytes=len(raw),sha256=sha(raw))
        if name=='color_before_base':
            row=next(x for x in r['rows']if x['type']==16);pw=row['entry']['before']['parameterWindow'];offset=row['parameterAddress']-pw['address']
            raw=bytearray(sidecar(pw['raw']));struct.pack_into('<I',raw,offset+0x10,bits(129));replace(pw['raw'],raw,'bad_color_state.bin')
        elif name=='scale_return_W':
            row=next(x for x in r['rows']if x['type']==7);pw=row['return']['after']['parameterWindow'];offset=row['parameterAddress']-pw['address']
            raw=bytearray(sidecar(pw['raw']));struct.pack_into('<I',raw,offset+0x1c,bits(1));replace(pw['raw'],raw,'bad_scale_return.bin')
        else:
            row=next(x for x in r['rows']if x['type']==16);item=row['nested']['entry']['allRegisters'];regs=json.loads(sidecar(item))
            next(c['uintValues']for c in regs['categories']if c['name']=='GPR')[31]=0x08b68cec
            replace(item,json.dumps(regs).encode('utf-8'),'bad_nested_registers.json')
        path=folder/'fx_property_callbacks.json';path.write_text(json.dumps(r,indent=2),encoding='utf-8')
        command=[sys.executable,'-X','utf8',str(Path(__file__).with_name('analyze_fx_color_scale.py')),'--capture',str(path),'--out',str(folder/'rejected_audit')]
        process=subprocess.run(command,capture_output=True)
        (folder/'stdout.log').write_bytes(process.stdout);(folder/'stderr.log').write_bytes(process.stderr)
        check(process.returncode!=0 and gate in process.stderr.decode('utf-8'),'Corrupt evidence did not fail at intended gate: '+name)
        results.append(dict(case=name,classification='synthetic corrupted evidence',capture=identity(path),expected_gate=gate,exit_code=process.returncode,command=command))
    (args.out/'verification.json').write_text(json.dumps(dict(passed=True,cases=results,producer=identity(Path(__file__)),source_capture=identity(args.capture)),indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,rejected_evidence_controls=len(results))))


if __name__=='__main__':main()
