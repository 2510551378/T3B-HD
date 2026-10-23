"""Retain the accepted isolated-effect GPU proof and audit protected source files."""
import datetime
import hashlib
import json
import shutil
from pathlib import Path


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[3]
    project = root / 'work/t3b_unreal'
    run = project / 'Validation/fx_palette_gpu_runs/96c007b73ee04d5cb5055ad87d887f3a'
    out = root / 'work/psp_parse/out/FX_PALETTE_GPU_20261021'
    out.mkdir(exist_ok=False)
    proof = json.loads((run / 'independent_verification.json').read_text(encoding='utf-8'))
    assert proof['passed'] and proof['captures'] == 13
    baseline = root / 'work/psp_parse/out/FX_VERTEX_COLOR_GE_20261021/source_protection.json'
    old = json.loads(baseline.read_text(encoding='utf-8'))
    report = {'checked_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'baseline': {'file': str(baseline), 'sha256': sha(baseline)}}
    for group in ('original_files', 'packages'):
        report[group] = []
        for row in old[group]:
            p = Path(row['file'])
            digest = sha(p)
            report[group].append(dict(file=str(p), sha256=digest,
                                      expected_sha256=row['sha256'], unchanged=digest == row['sha256']))
        assert all(r['unchanged'] for r in report[group]), group
    (out / 'source_protection.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    frozen = out / 'current_tool_snapshots'
    frozen.mkdir()
    rows = []
    for name in ('ge_effect_palette_gpu.cpp', 'run_fx_palette_gpu.py', 'verify_fx_palette_gpu.py',
                 'checkpoint_fx_palette_gpu.py'):
        p = project / 'Tools' / name
        dest = frozen / name
        shutil.copyfile(p, dest)
        rows.append(dict(source=str(p), file=str(dest), sha256=sha(dest)))
    shutil.copyfile(project / 'Tools/verify_fx_palette_gpu.py', run / 'verifier_audit/verify_accepted.py')
    record = dict(passed=True, run=str(run), proof_file=str(run / 'independent_verification.json'),
                  proof_sha256=sha(run / 'independent_verification.json'), tools=rows,
                  original_files_unchanged=len(report['original_files']), packages_unchanged=len(report['packages']),
                  UE_module_executed=False, default_M1_changed=False)
    (out / 'checkpoint.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
