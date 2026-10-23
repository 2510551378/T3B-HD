"""Build/evaluate the production GE-series adapter against independent outputs."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def check(ok, message):
    if not ok:
        raise ValueError(message)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--comparison', type=Path, required=True)
    p.add_argument('--compiler', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); check(not a.out.exists(), 'Never overwrite runtime proof'); a.out.mkdir(parents=True)
    m = json.loads(a.inputs.read_text(encoding='utf-8')); c = json.loads(a.comparison.read_text(encoding='utf-8'))
    inputs = Path(m['binary']['file']); check(m['passed'] and c['passed'], 'Input/reference did not pass')
    check(sha(inputs) == m['binary']['sha256'] == c['inputs_sha256'], 'Compared input changed')
    reference = a.comparison.parent / 'official_outputs.bin'
    check(sha(reference) == c['official_output_sha256'], 'Independent reference output changed')
    own = ROOT.parent / 't3b_unreal'; src = own / 'Source/T3BRemake'; exe = a.out / 'ge_series_probe.exe'
    sources = [src / 'Private/T3BGELighting.cpp', src / 'Private/T3BGESeries.cpp', own / 'Tools/ge_series_probe.cpp']
    cmd = [str(a.compiler), '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-msse4.1', '-ffp-contract=off',
           '-I' + str(src / 'Public'), *map(str, sources), '-o', str(exe)]
    build = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    (a.out / 'build_stdout.log').write_text(build.stdout, encoding='utf-8')
    (a.out / 'build_stderr.log').write_text(build.stderr, encoding='utf-8')
    check(build.returncode == 0, 'Production adapter standalone build failed')
    output = a.out / 'runtime_outputs.bin'; uv = a.out / 'runtime_uv.f32'
    command = [str(exe), str(inputs), str(output), str(uv)]
    run = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
    (a.out / 'stdout.log').write_text(run.stdout, encoding='utf-8')
    (a.out / 'stderr.log').write_text(run.stderr, encoding='utf-8')
    check(run.returncode == 0, 'Actual runtime reader/kernel rejected retained samples')
    check(output.read_bytes() == reference.read_bytes(), 'Production adapter differs from independent transform/light output')
    raw = inputs.read_bytes(); expected_uv = bytearray()
    for draw in m['draws']:
        start = draw['binary_byte_offset'] + 1464
        for i in range(draw['vertex_count']):
            expected_uv += raw[start + i * 64 + 56:start + i * 64 + 64]
    check(uv.read_bytes() == expected_uv, 'Original UV bits changed in runtime adapter')
    cases = []
    changes = [('bad_magic', 0, 0), ('zero_draws', 8, 0), ('invalid_slots', 12 + 1460, 9),
               ('nonfinite_position', 12 + 1464, 0x7fc00000), ('negative_weight', 12 + 1464 + 24, 0xbf800000),
               ('changed_geometry', m['draws'][106]['binary_byte_offset'] + 1464, 0x3f800000)]
    for name, offset, word in changes:
        bad = bytearray(raw); struct.pack_into('<I', bad, offset, word)
        file = a.out / (name + '.bin'); file.write_bytes(bad)
        result = subprocess.run([str(exe), str(file), str(a.out / (name + '.out')), str(a.out / (name + '.uv'))],
                                capture_output=True, text=True, encoding='utf-8')
        check(result.returncode != 0, 'Invalid replay input accepted: ' + name)
        cases.append(dict(case=name, file_sha256=sha(file), exit_code=result.returncode, error=result.stderr.strip()))
    for name, bad in [('truncated', raw[:-1]), ('trailing', raw + b'\0')]:
        file = a.out / (name + '.bin'); file.write_bytes(bad)
        result = subprocess.run([str(exe), str(file), str(a.out / (name + '.out')), str(a.out / (name + '.uv'))],
                                capture_output=True, text=True, encoding='utf-8')
        check(result.returncode != 0, 'Invalid extent accepted: ' + name)
        cases.append(dict(case=name, file_sha256=sha(file), exit_code=result.returncode, error=result.stderr.strip()))
    report = dict(schema='aya-ge-series-production-adapter-proof/v1', passed=True,
                  input_manifest=dict(file=str(a.inputs.resolve()), sha256=sha(a.inputs)),
                  input_sha256=sha(inputs), comparison=dict(file=str(a.comparison.resolve()), sha256=sha(a.comparison)),
                  build_command=cmd, run_command=command, build_exit_code=build.returncode, exit_code=run.returncode,
                  compiler_sha256=sha(a.compiler), executable_sha256=sha(exe), sources=[dict(file=str(p), sha256=sha(p))
                  for p in sources + [src / 'Public/T3BGELighting.h', src / 'Public/T3BGESeries.h']],
                  result=json.loads(run.stdout), runtime_output=dict(file=str(output.resolve()), sha256=sha(output)),
                  runtime_uv=dict(file=str(uv.resolve()), sha256=sha(uv)), all_transform_color_bytes_equal=True,
                  all_uv_bytes_equal=True, invalid_input_cases=cases, unreal_formal_module_built=False,
                  original_timing_verified=False, original_hardware_pixels_verified=False)
    (a.out / 'verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, **report['result'], rejected_inputs=len(cases))))


if __name__ == '__main__':
    main()
