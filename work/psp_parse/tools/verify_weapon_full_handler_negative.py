"""Reject missing/tampered companion draws without altering actual captures."""
import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--correlation',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():
        raise ValueError('Never replace negative evidence')
    args.out.mkdir(parents=True)
    first=json.loads(args.correlation.read_text(encoding='utf-8'))
    capture=json.loads(Path(first['capture']['file']).read_text(encoding='utf-8'))
    cases=[]
    for name,message in [('missing_companion','Actual CPU PRIM lacks callback snapshot'),
                         ('wrong_source_record','Actual subdraw differs from original object record'),
                         ('wrong_producer_count','Producer fields contradict original command words')]:
        c=copy.deepcopy(capture)
        handler=c['rows'][6]['fullHandler']
        if name=='missing_companion':
            handler['prims'].pop()
        elif name=='wrong_producer_count':
            handler['prims'][1]['count']+=1
        else:
            item=handler['metadata']['drawRecords'][0]['raw']['raw']
            b=bytearray(Path(item['file']).read_bytes())
            b[16+8]^=1
            p=args.out/'bad_original_draw_record.bin';p.write_bytes(b)
            item.update(file=str(p.resolve()),bytes=len(b),sha256=digest(p))
        p=args.out/(name+'_capture.json');p.write_text(json.dumps(c),encoding='utf-8')
        corr=copy.deepcopy(first)
        corr['capture']=dict(file=str(p.resolve()),sha256=digest(p))
        path=args.out/(name+'_correlation.json');path.write_text(json.dumps(corr),encoding='utf-8')
        command=[sys.executable,'-X','utf8',str(Path(__file__).with_name('analyze_weapon_full_handler_ge.py')),'--correlation',str(path),'--out',str(args.out/(name+'_audit'))]
        process=subprocess.run(command,capture_output=True)
        (args.out/(name+'_stdout.log')).write_bytes(process.stdout)
        (args.out/(name+'_stderr.log')).write_bytes(process.stderr)
        if process.returncode==0 or message not in process.stderr.decode('utf-8',errors='replace'):
            raise ValueError('Bad companion evidence not rejected at required gate: '+name)
        cases.append(dict(case=name,exit_code=process.returncode,expected_diagnostic=message))
    report=dict(passed=True,synthetic_negative_evidence=True,cases=cases,originals_modified=False,producer_sha256=digest(Path(__file__)))
    (args.out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,rejected_controls=len(cases))))


if __name__=='__main__':
    main()
