"""Corrupt color or camera anchors while preserving sidecar hashes; require exact join rejection."""
import argparse
import copy
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from analyze_fx_node_time import bits,check,identity,number,read,sha,sidecar


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--proof',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();check(not args.out.exists(),'Never replace GE join controls');args.out.mkdir(parents=True)
    original=read(args.proof);capture=read(Path(original['capture']['file']));results=[]
    for name,gate in [('wrong_after_color','Unexpected matched CPU-row coverage'),('wrong_rifle_WORLD','Unexpected matched CPU-row coverage'),
                      ('wrong_VIEW_input','Actual VIEW packet differs from original writer input')]:
        folder=args.out/name;folder.mkdir();proof=copy.deepcopy(original);r=copy.deepcopy(capture);row=r['rows'][1]
        def replace(item,data,filename):
            path=folder/filename;path.write_bytes(data);item.update(file=str(path.resolve()),bytes=len(data),sha256=sha(data))
        if name=='wrong_after_color':
            op=next(o for o in proof['operations']if o['row']==1);item=op['draws'][0]['vertices_after']['raw'];raw=bytearray(sidecar(item));raw[4]^=1;replace(item,raw,'wrong_color.bin')
        elif name=='wrong_rifle_WORLD':
            item=row['viewEntry']['weaponPose']['world']['raw'];raw=bytearray(sidecar(item));value=struct.unpack_from('<f',raw,48)[0];struct.pack_into('<f',raw,48,value+1)
            replace(item,raw,'wrong_WORLD.bin');row['modulated']['weaponPose']['world']['raw']=copy.deepcopy(item)
        else:
            item=row['viewEntry']['input']['raw'];raw=bytearray(sidecar(item));w=struct.unpack_from('<I',raw,48)[0];struct.pack_into('<I',raw,48,w^0x100);replace(item,raw,'wrong_VIEW.bin')
        if name!='wrong_after_color':
            path=folder/'synthetic_capture.json';path.write_text(json.dumps(r,indent=2),encoding='utf-8');proof['capture']=identity(path)
        proof_path=folder/'synthetic_CPU_proof.json';proof_path.write_text(json.dumps(proof,indent=2),encoding='utf-8')
        command=[sys.executable,'-X','utf8',str(Path(__file__).with_name('analyze_fx_vertex_color_GE.py')),'--proof',str(proof_path),'--expect-matched-rows','3','--out',str(folder/'rejected_correlation')]
        result=subprocess.run(command,capture_output=True);(folder/'stdout.log').write_bytes(result.stdout);(folder/'stderr.log').write_bytes(result.stderr)
        check(result.returncode!=0 and gate in result.stderr.decode('utf-8'),'Wrong evidence accepted/not rejected at intended gate: '+name)
        results.append(dict(case=name,classification='synthetic corrupted join evidence',expected_gate=gate,exit_code=result.returncode,command=command))
    (args.out/'verification.json').write_text(json.dumps(dict(passed=True,source=identity(args.proof),producer=identity(Path(__file__)),cases=results),indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,rejected_join_controls=len(results))))


if __name__=='__main__':main()
