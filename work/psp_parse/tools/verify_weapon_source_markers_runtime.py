"""Execute production C++ marker replay against independently read source bytes."""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np


def check(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(path):
    return dict(file=str(path.resolve()), sha256=sha(path))


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def checked_file(item):
    path = Path(item['file'])
    check(sha(path) == item['sha256'], 'Retained input changed')
    return path


def expand(values):
    result = np.eye(4)
    result[:, :3] = np.array(values).reshape(4, 3)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recovery', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    check(not args.out.exists(), 'Never replace actual runtime evidence')
    args.out.mkdir(parents=True)
    recovery = read(args.recovery)
    check(recovery['passed'] and not recovery['CPU_GE_same_invocation_verified'], 'Wrong evidence scope')
    weapon_path = checked_file(recovery['weapon'])
    weapon = read(weapon_path)
    input_path = checked_file(weapon['binary'])
    marker_path = checked_file(recovery['original_marker']['binary'])
    marker = marker_path.read_bytes()
    check(len(marker) == 208 and marker[:8] == b'T3BWMK1\0', 'Wrong marker format')
    count, weight = struct.unpack_from('<If', marker, 8)
    check(count == 2 and weight == 32767/32768, 'Wrong original marker/weight')
    # Source definitions independently checked against24 actual post-call windows.
    capture_path = checked_file(recovery['original_marker']['capture'])
    capture = read(capture_path)
    for row in capture['rows']:
        record = checked_file(row['postSourcesAll']).read_bytes()
        check(marker[16:] == record[0x80:0xc0]+record[0x170:0x1b0]+record[0x2a0:0x2e0], 'Runtime definitions differ from source bytes')
    locals = [np.frombuffer(marker, dtype='<f4', count=16, offset=80+64*j).reshape(4, 4).astype(float) for j in range(2)]
    project = Path(__file__).resolve().parents[2] / 't3b_unreal'
    public, private = project/'Source/T3BRemake/Public', project/'Source/T3BRemake/Private'
    sources = [private/'T3BGELighting.cpp', private/'T3BGESeries.cpp', private/'T3BGEWeaponMarkers.cpp', project/'Tools/ge_weapon_marker_probe.cpp']
    snapshot = args.out/'executed_source_snapshot'
    snapshot.mkdir()
    source_inventory = []
    for source in sources+[public/'T3BGELighting.h', public/'T3BGESeries.h', public/'T3BGEWeaponMarkers.h', Path(__file__)]:
        copy = snapshot/source.name
        shutil.copyfile(source, copy)
        source_inventory.append(dict(**identity(source), retained_copy=str(copy.resolve())))
    exe, output = args.out/'ge_weapon_marker_probe.exe', args.out/'runtime_markers.f64'
    build = ['C:\\Strawberry\\c\\bin\\g++.exe', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-msse4.1', '-ffp-contract=off', '-I'+str(public), *map(str, sources), '-o', str(exe)]
    process = subprocess.run(build, capture_output=True)
    (args.out/'build_stdout.log').write_bytes(process.stdout)
    (args.out/'build_stderr.log').write_bytes(process.stderr)
    check(process.returncode == 0, 'Production C++ build failed; logs retained')
    command = [str(exe), str(input_path), str(marker_path), str(output)]
    process = subprocess.run(command, capture_output=True)
    (args.out/'stdout.log').write_bytes(process.stdout)
    (args.out/'stderr.log').write_bytes(process.stderr)
    check(process.returncode == 0, 'Actual marker probe failed')
    actual = np.fromfile(output, dtype='<f8').reshape(12, 2, 19)
    binary = input_path.read_bytes()
    expected, rows = [], []
    for i, frame in enumerate(weapon['frames']):
        draw = weapon['draws'][frame['first_draw']]
        at = draw['binary_byte_offset']
        world = expand(np.frombuffer(binary, dtype='<f4', count=12, offset=at+1024))
        markers = []
        for local in locals:
            m = local @ world
            direction = m[2, :3] / np.linalg.norm(m[2, :3])
            markers.append(np.r_[m.reshape(-1), direction])
        expected.append(markers)
        rows.append(dict(sample=i, marker_matrices_and_unit_plusZ_F64=np.array(markers).tolist()))
    expected = np.array(expected)
    max_error = float(np.max(np.abs(actual-expected)))
    check(max_error <= 1e-9, 'C++/independent F64 marker reconstruction differs')
    controls = []
    mutations = [('truncated', marker[:-1]), ('trailing', marker+b'\0'), ('wrong_magic', b'BADMAGIC'+marker[8:]),
                 ('wrong_weight', marker[:12]+struct.pack('<f', 1.)+marker[16:]),
                 ('wrong_root_bind', marker[:16]+bytes(12)+marker[28:])]
    for name, data in mutations:
        bad = args.out/('negative_'+name+'.bin')
        bad.write_bytes(data)
        process = subprocess.run([str(exe), str(input_path), str(bad), str(args.out/('negative_'+name+'.output'))], capture_output=True)
        check(process.returncode != 0, 'Malformed marker evidence accepted: '+name)
        controls.append(dict(case=name, exit_code=process.returncode, diagnostic=process.stderr.decode('utf-8', errors='replace').strip()))
    for item in source_inventory:
        check(sha(Path(item['file'])) == item['sha256'] == sha(Path(item['retained_copy'])), 'Source changed during actual compilation')
    result = dict(schema='weapon-source-marker-production-replay/v2', passed=True,
        recovery=identity(args.recovery), weapon=identity(weapon_path), source_marker=identity(marker_path),
        source_inventory=source_inventory,
        actual_executable=identity(exe), actual_output=identity(output),
        build_command=build, run_command=command, samples=12, markers_per_sample=2,
        max_matrix_or_direction_abs_error_F64=max_error, numeric_limit_F64=1e-9,
        negative_controls=controls, rows=rows, actual_UE_module_executed=False, default_M1_binding_replaced=False,
        original_CPU_source1_same_GE_frame_verified=False,
        limits=['Standalone compilation executes production engine-independent marker core; official UE module/build is still unavailable.',
                'Comparison establishes C++/NumPy reconstruction agreement, not bit equality to unquantized CPU markers or full VFPU arithmetic.',
                'Original source1/2 full F32 local matrices compose directly with current GE WORLD. Root BONE high24 is an identity gate, not a pose round-trip.',
                'Same-frame actual unquantized CPU WORLD/marker capture and effect-instance identity remain outstanding.',
                'No marker is named muzzle and no gameplay hit/shot origin or event timing is inferred.'])
    (args.out/'verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(passed=True, samples=12, markers=24, max_abs_F64=max_error, rejected_controls=len(controls))))


if __name__ == '__main__':
    main()
