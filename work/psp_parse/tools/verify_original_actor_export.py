"""Independent GE/raw-vertex versus generic actor SourceSkin artifact checks."""
import argparse
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image

from exact_aya_materials import decode_texture, iter_material_draws
from export_aya_actual_weapon import affine, matrix_draws
from extract_runtime_character import layout, read_ppdmp
from recover_original_actor_metadata import identity, sha


def read_asset(path):
    data = path.read_bytes()
    magic, version, bones, packets, vertices, frames, materials, flags, reserved, fps, units, floor, pad = struct.unpack_from('<8s8I4f', data)
    if magic != b'T3BSKN2\0' or version != 2 or not 0 < bones <= 64 or not 2 <= frames <= 4096:
        raise ValueError('binary header outside generic SourceSkin contract')
    expected = 56 + bones * 4 + packets * 16 + vertices * 100 + frames * (4 + bones * 48)
    if len(data) != expected:
        raise ValueError('binary payload length mismatch')
    parents = list(struct.unpack_from('<' + str(bones) + 'i', data, 56))
    records = [struct.unpack_from('<4I', data, 56 + bones * 4 + i * 16) for i in range(packets)]
    at = 56 + bones * 4 + packets * 16
    vs = [struct.unpack_from('<8fI8I8f', data, at + i * 100) for i in range(vertices)]
    at += vertices * 100
    times = np.frombuffer(data, dtype='<f4', count=frames, offset=at)
    matrices = np.frombuffer(data, dtype='<f4', offset=at + frames * 4).reshape(frames, bones, 3, 4)
    return data, parents, records, vs, times, matrices, units, floor


def pose_binary(vs, matrices):
    result = []
    for vertex in vs:
        position = np.asarray(vertex[:3], dtype=np.float32)
        p = np.zeros(3, dtype=np.float32)
        for slot in range(vertex[8]):
            m = matrices[vertex[9 + slot]]
            p += np.float32(vertex[17 + slot]) * (m[:, :3] @ position + m[:, 3])
        result.append(p)
    return np.asarray(result)


def original_ge_positions(draw, push):
    vt = draw['vtype']
    stride, offsets = layout(vt)
    if (vt >> 9) & 3 != 2 or (vt >> 7) & 3 != 2:
        raise ValueError('independent fixture requires original UV/POS/weight16 formats')
    raw, points = push[draw['pointer']:draw['pointer'] + draw['size']], []
    nw = ((vt >> 14) & 7) + 1
    for vertex in range(draw['count']):
        pos = np.asarray(struct.unpack_from('<3h', raw, vertex * stride + offsets['pos'][0]), dtype=float) / 32768
        weights = struct.unpack_from('<' + str(nw) + 'H', raw, vertex * stride + offsets['wt'][0])
        point = np.zeros(3)
        for slot, raw_weight in enumerate(weights):
            if not raw_weight:
                continue
            m = affine(draw['bones'][slot * 12:slot * 12 + 12])
            point += raw_weight / 32768 * (m[:3, :3] @ pos + m[:3, 3])
        points.append(point)
    return np.asarray(points)


def verify(report_path, output_path):
    report = json.loads(report_path.read_text(encoding='utf-8'))
    for description in [*report['inputs'].values(), report['canonical_scale_source'],
                        report['material_report'], report['material_manifest_identity']]:
        if identity(Path(description['path'])) != description:
            raise ValueError('declared actor export input/artifact identity changed')
    data, parents, packets, vertices, times, matrices, units, floor = read_asset(Path(report['output']))
    if sha(data) != report['binary_sha256']:
        raise ValueError('binary identity changed')
    metadata = json.loads(Path(report['inputs']['metadata']['path']).read_text(encoding='utf-8'))
    manifest = json.loads(Path(report['inputs']['aligned_manifest']['path']).read_text(encoding='utf-8'))
    material_report = json.loads(Path(report['material_report']['path']).read_text(encoding='utf-8'))
    if parents != [b['parent'] for b in metadata['bones']] or len(vertices) != metadata['summary']['vertex_count']:
        raise ValueError('source hierarchy/vertex inventory changed during binary packing')
    actual_weights, original_weights = [], []
    for packed, original in zip(vertices, [v for p in metadata['packets'] for v in p['vertices']]):
        count = packed[8]
        if packed[9:9+count] != tuple(i for i, w in original['influences']):
            raise ValueError('original source-index influence order changed')
        actual_weights += list(packed[17:17+count])
        original_weights += [w for i, w in original['influences']]
    if actual_weights != original_weights:
        raise ValueError('original quantized weights were altered')
    source_error, checked_components = 0.0, 0
    for index, frame in enumerate(manifest['frames']):
        raw = Path(frame['sourceBlock']['file']).read_bytes()
        source = np.asarray([[struct.unpack('<f', struct.pack('<I', (word & 0xffffff) << 8))[0]
                              for word in struct.unpack_from('<12I', raw, b * 0x130 + 0xc0)]
                             for b in range(len(parents))], dtype='<f4').reshape(len(parents), 3, 4, order='C')
        # Each original record has column-major payload, while runtime matrices are rows.
        source = np.asarray([s.reshape(12).reshape(3, 4, order='F') for s in source], dtype='<f4')
        source_error = max(source_error, float(np.abs(source - matrices[index]).max()))
        checked_components += int(source.size)
    if source_error != 0:
        raise ValueError('original source matrices changed in binary output')
    checks = []
    for frame_index, frame in enumerate(manifest['frames']):
        if not frame.get('dump'):
            continue
        path = Path(frame['dump']['file'])
        commands, push = read_ppdmp(str(path))
        states = {(x['register_record'], x['register_word']): x for x in iter_material_draws(commands, push)}
        expected_hashes = [p['vertex_sha256'] for p in metadata['packets']]
        selected = [d for d in matrix_draws(commands, push)
                    if d['sha256'] in set(expected_hashes) and d['world'] == frame['actorWorldPayload']]
        if [d['sha256'] for d in selected] != expected_hashes:
            raise ValueError('independent observed GE packet identity/order differs')
        original = np.concatenate([original_ge_positions(d, push) for d in selected])
        packed = pose_binary(vertices, matrices[frame_index])
        error = float(np.abs(original - packed).max())
        if error > .0001:
            raise ValueError(f'independent original GE pose differs from exported skin: {error}')
        for draw, packet in zip(selected, metadata['packets']):
            state = states[(draw['register_record'], draw['register_word'])]
            rgba, facts = decode_texture(state['texture0']['raw'], state['registers'], state['clut'], state['clut_known'])
            resource = next(r for r in material_report['materials'] if r['rgba_sha256'] == facts['rgba_sha256'])
            if Image.open(resource['png']).convert('RGBA').tobytes() != rgba or Image.open(resource['bmp']).convert('RGBA').tobytes() != rgba:
                raise ValueError('PNG/BMP original RGBA/alpha differs from actual GE material')
        checks.append({'frame': frame_index, 'capture': identity(path), 'vertices': len(original),
                       'max_ge_vs_binary_position_error_original_units': error})
    if len(checks) < 2:
        raise ValueError('independent verifier needs two actual GE pose checks')
    result = {'schema': 'original-actor-export-verification/v1', 'passed': True,
              'report': identity(report_path), 'bones': len(parents), 'packets': len(packets), 'vertices': len(vertices),
              'samples': len(times), 'source_matrix_components_checked': checked_components,
              'source_matrix_max_error': source_error, 'original_weight_components_preserved': len(actual_weights),
              'ge_checks': checks, 'original_png_bmp_rgba_alpha_exact': True,
              'pc_units_per_original_unit_f32': units, 'reference_floor_f32': floor,
              'runtime_C_executed': False,
              'limits': ['This validates original GE bytes against the exported binary and RGBA assets; compiled M1 CPU probes remain a separate integration check.']}
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    verify(args.report, args.out)
