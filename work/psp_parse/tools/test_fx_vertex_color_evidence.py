"""Corrupt retained evidence without touching original observations; require independent gates."""
import argparse
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
from analyze_fx_node_time import check,identity,read,sha,sidecar


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();check(not args.out.exists(),'Never replace evidence controls');args.out.mkdir(parents=True)
    original=read(args.capture);results=[]
    for name,gate in [('wrong_palette_output','Original palette conversion differs from actual memory'),
                      ('changed_vertex_position','Actual vertex-color patch changed wrong bytes'),
                      ('false_cache_decision','Raw-byte cache decision differs')]:
        folder=args.out/name;folder.mkdir();r=copy.deepcopy(original)
        for filename in ('executed_trace_fx_color_material_emissions.js','process_completed.json'):shutil.copyfile(args.capture.parent/filename,folder/filename)
        row=next(x for x in r['rows']if x.get('enqueued'))
        if name=='false_cache_decision':row['enqueued']=False
        else:
            item=row['paletteReturn']['output']['raw']if name=='wrong_palette_output'else row['vertexPatchReturn']['draws'][0]['raw']
            raw=bytearray(sidecar(item));raw[0 if name=='wrong_palette_output'else 8]^=1
            path=folder/'corrupt_raw.bin';path.write_bytes(raw);item.update(file=str(path.resolve()),bytes=len(raw),sha256=sha(raw))
        path=folder/'fx_color_material_emissions.json';path.write_text(json.dumps(r,indent=2),encoding='utf-8')
        command=[sys.executable,'-X','utf8',str(Path(__file__).with_name('analyze_fx_vertex_color.py')),'--capture',str(path),'--out',str(folder/'rejected_audit')]
        process=subprocess.run(command,capture_output=True);(folder/'stdout.log').write_bytes(process.stdout);(folder/'stderr.log').write_bytes(process.stderr)
        check(process.returncode!=0 and gate in process.stderr.decode('utf-8'),'Corrupt evidence did not fail at intended gate: '+name)
        results.append(dict(case=name,classification='synthetic corrupted evidence',capture=identity(path),expected_gate=gate,exit_code=process.returncode,command=command))
    (args.out/'verification.json').write_text(json.dumps(dict(passed=True,producer=identity(Path(__file__)),source_capture=identity(args.capture),cases=results),indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,rejected_evidence_controls=len(results))))


if __name__=='__main__':main()
