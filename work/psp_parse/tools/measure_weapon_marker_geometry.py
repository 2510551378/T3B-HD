"""Measure current M1 mesh-tip estimate against actual original helper outputs.

Uses original-world matrices at each helper return, without fitted hand sockets.
This is an offline geometric comparison, not an M1 render/playback acceptance.
"""
import argparse
import hashlib
import json
import math
import re
import struct
from pathlib import Path

from analyze_weapon_marker_output import audit, check, matrix, sidecar


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def transform(m, point):
    return [sum(m[column*4 + row]*point[column] for column in range(4)) for row in range(4)]


def distance(a, b):
    return math.sqrt(sum((x-y)**2 for x, y in zip(a, b)))


def angle(a, b):
    an, bn = math.sqrt(sum(x*x for x in a)), math.sqrt(sum(x*x for x in b))
    check(an > 0 and bn > 0, 'zero direction')
    cosine = sum(x*y for x, y in zip(a, b)) / (an*bn)
    return math.degrees(math.acos(max(-1, min(1, cosine))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--m1-source', type=Path, required=True)
    parser.add_argument('--weapon-clip', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    checked = audit(args.capture)
    capture = json.loads(args.capture.read_bytes())
    source_bytes = args.m1_source.read_bytes()
    source = source_bytes.decode('utf-8')
    match = re.search(r'SOURCE_WEAPON_TIP\s*=\s*\{([^}]+)\}', source)
    check(match is not None and 'tip.x-=.1f;' in source, 'selected M1 tip/direction implementation changed')
    tip = [f32(float(v.strip().removesuffix('f'))) for v in match[1].split(',')]
    check(len(tip) == 3, 'tip is not a position')
    second = list(tip)
    second[0] = f32(second[0] - f32(0.1))
    clip = args.weapon_clip.read_bytes()
    check(clip[:8] == b'T3BSKN2\0' and len(clip) >= 56, 'wrong source weapon clip')
    units = struct.unpack_from('<f', clip, 44)[0]
    check(math.isfinite(units) and units > 0, 'invalid source units')
    results = []
    for row in capture['rows']:
        check('postSourcesAll' in row and 'preSourcesAll' in row, 'capture lacks all three source records')
        records = sidecar(row['postSourcesAll'])
        pre_records = sidecar(row['preSourcesAll'])
        check(len(records) == len(pre_records) == 3*0x130, 'wrong dense source size')
        check(records[0x130:2*0x130] == sidecar(row['postSource']), 'source1 post record differs from dense snapshot')
        check(pre_records[0x130:2*0x130] == sidecar(row['preSource']), 'source1 pre record differs from dense snapshot')
        parents = [struct.unpack_from('<I', records, i*0x130+0x124)[0] for i in range(3)]
        check(parents == [0, row['postSourceBase'], row['postSourceBase']], 'runtime weapon parent pointers changed')
        # +C0 contains twelve GE BONE command words, not a 16-F32 matrix.
        # GE payloads retain the high 24 bits of each source IEEE F32 value.
        commands = struct.unpack_from('<12I', records, 0xC0)
        check(all(word >> 24 == 0x2B for word in commands), 'source0 +C0 is not GE BONE data')
        root_matrix = struct.unpack_from('<16f', records, 0x40)
        identity = tuple(1.0 if i in (0, 5, 10, 15) else 0.0 for i in range(16))
        check(root_matrix == identity, 'this rifle comparison requires observed source0 +40 identity')
        source80_words = struct.unpack_from('<16I', records, 0x80)
        source80_selected = [source80_words[c*4 + r] for c in range(4) for r in range(3)]
        check(all((word & 0xFFFFFF) == raw >> 8 for word, raw in zip(commands, source80_selected)),
              'GE BONE payload does not match high24 source0 +80 under identity root')
        payload = [struct.unpack('<f', struct.pack('<I', (word & 0xFFFFFF) << 8))[0] for word in commands]
        check(all(math.isfinite(v) for v in payload), 'nonfinite source0 GE skin matrix')
        c0 = [0.0] * 16
        for column in range(4):
            for component in range(3):
                c0[column*4 + component] = payload[column*3 + component]
        c0[15] = 1.0
        world, original = matrix(row['postWorld']), matrix(row['actualOutput'])
        local_tip = transform(c0, tip + [1.0])
        world_tip = transform(world, local_tip)[:3]
        world_second = transform(world, transform(c0, second + [1.0]))[:3]
        estimated_direction = [b-a for a, b in zip(world_tip, world_second)]
        separation = distance(world_tip, original[12:15])
        results.append({'sample': row['sample'], 'entry_ticks': row['entryTicks'],
            'original_helper_origin': list(original[12:15]), 'source0_mesh_tip_world': world_tip,
            'source0_mesh_tip_local_original_units': local_tip[:3],
            'distance_original_units': separation, 'distance_pc_units': separation*units,
            'distance_ue_centimeters': separation*units*100,
            'direction_difference_degrees': angle(estimated_direction, original[8:11]),
            'source0_GE_command_words': list(commands), 'source0_GE_decoded_col_major_3x4': payload,
            'semanticName': None})
    result = {'schema': 'weapon-marker-m1-geometry-comparison/v1', 'passed': True,
        'capture': str(args.capture.resolve()), 'capture_sha256': checked['capture_sha256'],
        'm1_source': str(args.m1_source.resolve()), 'm1_source_sha256': hashlib.sha256(source_bytes).hexdigest(),
        'weapon_clip': str(args.weapon_clip.resolve()), 'weapon_clip_sha256': hashlib.sha256(clip).hexdigest(),
        'tip_as_compiled_f32': tip, 'direction_second_point_f32': second, 'units_per_original_unit': units,
        'rows_checked': len(results),
        'max_distance_original_units': max(r['distance_original_units'] for r in results),
        'max_distance_ue_centimeters': max(r['distance_ue_centimeters'] for r in results),
        'max_direction_difference_degrees': max(r['direction_difference_degrees'] for r in results),
        'rows': results, 'semanticName': None,
        'limits': ['M1 geometric estimate is compared analytically in original-world space using same-stop source0 decoded GE BONE payload and WORLD.',
            'This does not execute M1, its baked Aya-relative matrices, frame interpolation, arbitrary game yaw, or GPU rendering.',
            'Helper source1 is an observed firing-related transform; muzzle/FX identity remains unconfirmed.',
            'No production muzzle/socket/timeline binding is replaced by this measurement.']}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('rows_checked', 'max_distance_ue_centimeters', 'max_direction_difference_degrees')}))


if __name__ == '__main__':
    main()
