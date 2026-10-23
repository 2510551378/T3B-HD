"""Compare production original-F32 marker composition to actual CPU state bytes."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def identity(p):
    return dict(file=str(p.resolve()), sha256=sha(p))


def checked_file(item):
    p = Path(item['file'])
    check(sha(p) == item['sha256'], 'Retained evidence changed')
    return p


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--correlation', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    check(not args.out.exists(), 'Never replace actual runtime proof')
    args.out.mkdir(parents=True)
    corr = read(args.correlation)
    check(corr['passed'] and corr['matched_observations'] > 0, 'No verified CPU/GE visual effect link')
    capture = read(checked_file(corr['capture']))
    marker = checked_file(corr['original_marker_catalog'])
    catalog = marker.read_bytes()
    worlds, reference = [], []
    for row in capture['rows']:
        pose = row['matrix']['entry']['weaponPose']
        raw = checked_file(pose['sources']['raw']).read_bytes()
        check(catalog[16:] == raw[0x80:0xc0]+raw[0x170:0x1b0]+raw[0x2a0:0x2e0], 'Different marker definitions')
        worlds.append(checked_file(pose['world']['raw']).read_bytes())
        reference.append(checked_file(row['matrix']['entry']['p60']['raw']).read_bytes())
    inputs, expected = args.out/'actual_CPU_WORLD.f32', args.out/'actual_CPU_state60.f32'
    inputs.write_bytes(b''.join(worlds))
    expected.write_bytes(b''.join(reference))
    project = Path(__file__).resolve().parents[2]/'t3b_unreal'
    public, private = project/'Source/T3BRemake/Public', project/'Source/T3BRemake/Private'
    sources = [private/'T3BGELighting.cpp', private/'T3BGESeries.cpp', private/'T3BGEWeaponMarkers.cpp', project/'Tools/ge_weapon_marker_cpu_probe.cpp']
    snapshot = args.out/'executed_source_snapshot'
    snapshot.mkdir()
    inventory = []
    for p in sources+[public/'T3BGELighting.h', public/'T3BGESeries.h', public/'T3BGEWeaponMarkers.h', Path(__file__)]:
        copy = snapshot/p.name
        shutil.copyfile(p, copy)
        inventory.append(dict(**identity(p), retained_copy=str(copy.resolve())))
    exe, output = args.out/'ge_weapon_marker_cpu_probe.exe', args.out/'runtime_source1.f32'
    build = ['C:\\Strawberry\\c\\bin\\g++.exe', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-msse4.1', '-ffp-contract=off', '-I'+str(public), *map(str, sources), '-o', str(exe)]
    compiled = subprocess.run(build, capture_output=True)
    (args.out/'build_stdout.log').write_bytes(compiled.stdout)
    (args.out/'build_stderr.log').write_bytes(compiled.stderr)
    check(compiled.returncode == 0, 'Actual production C++ compilation failed')
    command = [str(exe), str(marker), str(inputs), str(output)]
    process = subprocess.run(command, capture_output=True)
    (args.out/'stdout.log').write_bytes(process.stdout)
    (args.out/'stderr.log').write_bytes(process.stderr)
    check(process.returncode == 0, 'Actual marker runtime failed')
    check(output.read_bytes() == expected.read_bytes(), 'Production marker does not reproduce actual CPU state bits')
    for item in inventory:
        check(sha(Path(item['file'])) == item['sha256'] == sha(Path(item['retained_copy'])), 'Source changed during compilation')
    result = dict(schema='original-source1-production-F32-CPU-proof/v1', passed=True,
        correlation=identity(args.correlation), marker_asset=identity(marker), actual_inputs=identity(inputs), actual_reference=identity(expected),
        actual_executable=identity(exe), actual_output=identity(output), build_command=build, run_command=command, source_inventory=inventory,
        actual_CPU_records=len(worlds), distinct_WORLD_snapshots=len(set(worlds)), F32_components_compared=len(worlds)*16,
        differing_component_bits=0, original_source1_visual_FX_link_observed=True, actual_UE_module_executed=False,
        gameplay_bullet_origin_verified=False, default_M1_binding_replaced=False,
        limits=['Actual captured source1 inputs/default-prefix observed path only. Source2 lacks an actual helper/state output in this run.',
                'Full unquantized CPU WORLD is used here. GE WORLD reconstruction still has F24 loss.',
                'The standalone executable calls production core. Formal UE module, M1 firing behavior and gameplay bullet/hit origin remain unverified.'])
    (args.out/'verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(passed=True, actual_CPU_records=len(worlds), distinct_WORLD_snapshots=len(set(worlds)), F32_components=len(worlds)*16, bit_differences=0)))


if __name__ == '__main__':
    main()
