"""Ensure new CPU-pose/GE evidence contradictions cannot pass correlation."""
import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('Never replace negative evidence')
    args.out.mkdir(parents=True)
    capture = json.loads(args.capture.read_text(encoding='utf-8'))
    for name in ['executed_trace_weapon_marker_ge_emit.js', 'process_completed.json']:
        shutil.copyfile(args.capture.parent/name, args.out/name)
    cases = []
    for name, diagnostic in [('wrong_world_snapshot', 'WORLD changed between CPU stages'),
                             ('wrong_source_definition', 'Captured original definitions differ'),
                             ('GE_hash_changed', 'GE bytes changed')]:
        bad = copy.deepcopy(capture)
        if name == 'wrong_world_snapshot':
            bad['rows'][4]['matrix']['entry']['weaponPose']['world']['raw'] = bad['rows'][0]['matrix']['entry']['weaponPose']['world']['raw']
        elif name == 'wrong_source_definition':
            item = bad['rows'][4]['matrix']['entry']['weaponPose']['sources']['raw']
            raw = bytearray(Path(item['file']).read_bytes())
            raw[0x170] ^= 1
            raw_file = args.out/'bad_source_definition.bin'
            raw_file.write_bytes(raw)
            for stage in ['matrix', 'emit']:
                bad['rows'][4][stage]['entry']['weaponPose']['sources']['raw'] = dict(file=str(raw_file.resolve()), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        else:
            bad['geCaptures'][0]['raw']['sha256'] = '0'*64
        path = args.out/(name+'.json')
        path.write_text(json.dumps(bad), encoding='utf-8')
        command = [sys.executable, '-X', 'utf8', str(Path(__file__).with_name('analyze_weapon_cpu_ge_correlated.py')),
                   '--capture', str(path), '--out', str(args.out/(name+'_audit'))]
        process = subprocess.run(command, capture_output=True)
        (args.out/(name+'_stdout.log')).write_bytes(process.stdout)
        (args.out/(name+'_stderr.log')).write_bytes(process.stderr)
        if process.returncode == 0 or diagnostic not in process.stderr.decode('utf-8', errors='replace'):
            raise ValueError('Bad evidence not rejected at intended gate: '+name)
        cases.append(dict(case=name, exit_code=process.returncode, expected_diagnostic=diagnostic))
    report = dict(passed=True, capture=str(args.capture.resolve()), synthetic_negative_evidence=True, cases=cases,
                  originals_modified=False, producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (args.out/'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(dict(passed=True, rejected_controls=len(cases))))


if __name__ == '__main__':
    main()
