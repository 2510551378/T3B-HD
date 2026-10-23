"""Validate and export a selected original actor to generic M1 T3BSKN2.

Matches asynchronous GE dumps to source samples by every effective palette
component plus actor WORLD. Uses canonical Aya scene units, original source
weights, and original decoded RGBA. Does not modify capture/canonical tools.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image

from exact_aya_materials import decode_texture, iter_material_draws, material_parameters, write_rgba_bmp
from export_aya_actual_weapon import matrix_draws
from export_aya_source_skin import decode_ge, pose_vertices, resolve_output_model
from extract_runtime_character import read_ppdmp
from recover_original_actor_metadata import identity, sha


SELECTED = [0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14]


def relative_input(root, value):
    path = Path(value)
    if path.is_file():
        return path.resolve()
    return (root / path.name).resolve()


def validate_sources(metadata, manifest, manifest_path, cpu_hz):
    count, expected_group = metadata['summary']['bone_count'], metadata['summary']['ordered_geometry_sha256']
    if not metadata['summary'].get('expected_identity_verified'):
        raise ValueError('metadata lacks explicit ordered-geometry identity selection')
    if manifest.get('geometryGroup') != expected_group or not 2 <= len(manifest['frames']) <= 4096:
        raise ValueError('manifest actor identity/sample count mismatch')
    matrices, blocks, exact, max_steps, max_error, max_scaled = [], [], 0, 0, 0.0, 0.0
    parents = [b['parent'] for b in metadata['bones']]
    for number, frame in enumerate(manifest['frames']):
        if frame['frame'] != number or frame.get('geometryGroup') != expected_group:
            raise ValueError('frame ordering/geometry identity changed')
        rows = {r['index']: r for r in frame['records']}
        if len(rows) != count or set(rows) != set(range(count)) or len(frame['records']) != count:
            raise ValueError('incomplete/duplicate source-index sample')
        block_path = relative_input(manifest_path.parent, frame['sourceBlock']['file'])
        raw = block_path.read_bytes()
        if len(raw) != count * 0x130:
            raise ValueError('incomplete original source block')
        blocks.append(identity(block_path))
        current = []
        for index in range(count):
            words = np.frombuffer(raw[index * 0x130:(index + 1) * 0x130], dtype='<u4')
            parent = 0 if parents[index] < 0 else frame['sourceBase'] + parents[index] * 0x130
            if int(words[0x124 // 4]) != parent:
                raise ValueError(f'frame {number} source {index}: parent pointer changed')
            payload = words[48:60]
            if payload.tolist() != rows[index]['matrix'] or not np.all(payload >> 24 == 0x2b):
                raise ValueError('manifest source payload differs from original record bytes')
            if words[32:48].tolist() != metadata['bones'][index]['matrix_80_words']:
                raise ValueError('source inverse-bind candidate bytes changed within selected clip')
            left = words[16:32].view('<f4').reshape(4, 4, order='F')
            right = words[32:48].view('<f4').reshape(4, 4, order='F')
            product = (left @ right)[:3].flatten(order='F').astype('<f4')
            decoded = decode_ge(payload)
            if not np.isfinite(product).all() or not np.isfinite(decoded).all():
                raise ValueError('nonfinite source pose')
            packed = product.view('<u4') >> 8
            actual = payload & 0xffffff
            exact += int(np.sum(packed == actual))
            max_steps = max(max_steps, int(np.abs(packed.astype(np.int64) - actual.astype(np.int64)).max()))
            error = np.abs(product - decoded.flatten(order='F'))
            # Near-zero cancellation makes integer float24 bit distance unstable.
            # This is the existing dense Aya F32-dot/float24 truncation bound.
            terms = (np.abs(left[:3].astype(np.float64)) @ np.abs(right.astype(np.float64))).flatten(order='F')
            bound = 8 * np.finfo(np.float32).eps * terms + np.abs(decoded.flatten(order='F')) / 32768 + np.finfo(np.float32).tiny
            scaled = float((error / bound).max())
            if scaled > 1:
                raise ValueError(f'frame {number} source {index}: record40*80 exceeds verified arithmetic bound {scaled}')
            max_error, max_scaled = max(max_error, float(error.max())), max(max_scaled, scaled)
            current.append(decoded)
        words = frame['actorWorldWords']
        if len(words) != 16 or [(words[i] >> 8) & 0xffffff for i in SELECTED] != frame['actorWorldPayload']:
            raise ValueError('recorded actor WORLD input/payload mismatch')
        matrices.append(current)
    ticks = [f['ticks'] for f in manifest['frames']]
    if not np.isfinite(cpu_hz) or cpu_hz <= 0 or any(b <= a for a, b in zip(ticks, ticks[1:])):
        raise ValueError('invalid saved clock/nonmonotonic original sample ticks')
    times = np.asarray([(tick - ticks[0]) / cpu_hz for tick in ticks], dtype='<f4')
    if not np.isfinite(times).all() or not np.all(np.diff(times) > 0):
        raise ValueError('F32 original sample times not strictly increasing')
    matrices = np.asarray(matrices, dtype='<f4')
    return matrices, times, {'parent_pointer_checks': count * len(ticks), 'source_blocks': blocks,
        'matrix40_times_80': {'convention': 'column-major original 4x4 product -> column-major GE 3x4',
            'exact_float24_components': exact, 'total_components': int(matrices.size),
            'max_float24_bit_steps': max_steps, 'max_absolute_error': max_error, 'max_error_over_roundoff_bound': max_scaled},
        'changed_adjacent_samples_per_source': np.any(matrices[1:] != matrices[:-1], axis=(2, 3)).sum(0).tolist()}


def selected_draw_groups(capture, metadata):
    commands, push = read_ppdmp(str(capture))
    packets = metadata['packets']
    hashes = [p['vertex_sha256'] for p in packets]
    grouped = defaultdict(list)
    for draw in matrix_draws(commands, push):
        if draw['sha256'] in set(hashes):
            if None in draw['world'] + draw['view']:
                raise ValueError('selected actor draw lacks explicit WORLD/VIEW')
            grouped[(tuple(draw['world']), tuple(draw['view']))].append(draw)
    groups = []
    for draws in grouped.values():
        if [d['sha256'] for d in draws] != hashes:
            continue
        if any(d['primitive'] != 3 or d['count'] != p['vertex_count'] or d['vtype'] != p['vtype']
               or d['size'] != p['vertex_count'] * p['stride'] for p, d in zip(packets, draws)):
            raise ValueError('actor geometry identity matched but PRIM/count/stride differs')
        groups.append(draws)
    if not groups:
        raise ValueError('GE dump lacks the complete ordered selected actor mesh')
    return commands, push, groups


def effective_palette_matches(draws, packets, frame):
    if draws[0]['world'] != frame['actorWorldPayload']:
        return False, 0
    source = {r['index']: [word & 0xffffff for word in r['matrix']] for r in frame['records']}
    components = 0
    for packet, draw in zip(packets, draws):
        for slot in packet['active_palette_indices']:
            actual = draw['bones'][slot * 12:slot * 12 + 12]
            if actual != source[packet['palette_state'][str(slot)]]:
                return False, components
            components += 12
    return True, components


def align_ge(manifest, metadata, manifest_path, aligned_path):
    aligned = json.loads(json.dumps(manifest))
    for frame in aligned['frames']:
        frame['dump'] = None
    candidates = list(manifest.get('unassignedGEDumps', []))
    if not candidates:
        candidates = [f['dump'] for f in manifest['frames'] if f.get('dump')]
    matches, retained = [], []
    for recorded in candidates:
        path = relative_input(manifest_path.parent, recorded['file'])
        commands, push, groups = selected_draw_groups(path, metadata)
        possibilities = []
        for group_index, draws in enumerate(groups):
            for index, frame in enumerate(manifest['frames']):
                passed, components = effective_palette_matches(draws, metadata['packets'], frame)
                if passed:
                    possibilities.append((index, group_index, components))
        if len(possibilities) != 1:
            raise ValueError(f'GE/source frame alignment not unique ({len(possibilities)}) for {path}')
        index, group_index, components = possibilities[0]
        if aligned['frames'][index]['dump'] is not None:
            raise ValueError('multiple GE dumps assigned to same source sample')
        draws = groups[group_index]
        aligned['frames'][index]['dump'] = {'file': str(path), 'bytes': path.stat().st_size}
        matches.append({'capture': identity(path), 'actual_source_frame': index,
                        'requested_at_sample': recorded.get('requestedAtSample'),
                        'received_after_samples': recorded.get('receivedAfterSamples'),
                        'exact_effective_palette_components': components, 'world_components': 12,
                        'actor_packet_count': len(draws), 'geometry_group_sha256': metadata['summary']['ordered_geometry_sha256'],
                        'vertex_records': [d['vertex_record'] for d in draws]})
        retained.append((index, path, commands, push, draws))
    if len(matches) < 2:
        raise ValueError('export requires at least two independently aligned GE cross-checks')
    aligned['geAlignment'] = {'schema': 'original-actor-ge-alignment/v1', 'passed': True,
        'input_manifest': identity(manifest_path), 'matches': matches,
        'criterion': 'unique source sample matching every active draw-palette payload and all 12 actor WORLD payloads'}
    aligned_path.parent.mkdir(parents=True, exist_ok=True)
    aligned_path.write_text(json.dumps(aligned, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return aligned, retained


def export_materials(retained, metadata, runtime_root, material_relative):
    destination = resolve_output_model(runtime_root, material_relative)
    if any(c.isspace() for c in Path(material_relative).as_posix()):
        raise ValueError('SourceSkin material manifest paths cannot contain whitespace')
    resources, packet_materials, observations = {}, {}, []
    for frame_index, path, commands, push, draws in retained:
        states = {(d['register_record'], d['register_word']): d for d in iter_material_draws(commands, push)}
        for packet, draw in zip(metadata['packets'], draws):
            state = states[(draw['register_record'], draw['register_word'])]
            texture, registers = state['texture0'], state['registers']
            if texture is None or texture['framebuffer']:
                raise ValueError('selected actor material lacks ordinary original TEXTURE0 bytes')
            rgba, facts = decode_texture(texture['raw'], registers, state['clut'], state['clut_known'])
            params = material_parameters(registers)
            if (not params['texture_enabled'] or params['uv_map_mode'] != 0 or params['uv_through_mode']
                    or params['uv_storage_type'] != 2 or params['texture_function'] != 0
                    or not params['texture_alpha_used'] or params['alpha_test_function'] != 6
                    or params['alpha_test_mask'] != 255 or params['min_filter_raw'] != 1 or params['mag_filter_raw'] != 1
                    or [params['blend_src_factor'], params['blend_dst_factor'], params['blend_equation']] != [2, 3, 0]):
                raise ValueError('original actor GE material not representable by current generic SourceSkin interface')
            key_data = {'texture_sha256': texture['sha256'], 'clut_ram_sha256': sha(state['clut'][:1024]),
                        'rgba_sha256': facts['rgba_sha256'], 'parameters': params}
            key = sha(json.dumps(key_data, sort_keys=True).encode())
            previous = packet_materials.setdefault(packet['draw'], key)
            if previous != key:
                raise ValueError('actor packet material changed across independent GE validations')
            if key not in resources:
                resources[key] = {'material_id': key, **key_data, **facts, '_rgba': rgba,
                                  '_texture': texture['raw'], '_clut': state['clut'][:1024]}
            observations.append({'frame': frame_index, 'packet': packet['draw'], 'vertex_sha256': packet['vertex_sha256'],
                                 'material_id': key, 'capture': str(path), 'vertex_record': draw['vertex_record'],
                                 'register_record': draw['register_record'], 'register_word': draw['register_word'],
                                 'texture_record': texture['record'], 'clut_records': state['clut_records']})
    if len(packet_materials) != len(metadata['packets']) or not 1 <= len(resources) <= 16:
        raise ValueError('missing actor material packet bindings/runtime material count exceeded')
    keys = sorted(resources)
    indices = {key: i for i, key in enumerate(keys)}
    flags_by_material = {1 | (2 if r['parameters']['color_double'] else 0)
                         | (4 if r['parameters']['alpha_blend_enabled'] else 0)
                         | (8 if r['parameters']['alpha_test_enabled'] else 0) for r in resources.values()}
    if len(flags_by_material) != 1:
        raise ValueError('per-material GE blend/double/alpha-enable differs; generic runtime flags are asset-wide')
    destination.mkdir(parents=True, exist_ok=True)
    manifest_lines = [f'T3BMAT1 {len(keys)}']
    for key in keys:
        r, index = resources[key], indices[key]
        stem = 'original_actor_' + key[:16]
        png, bmp = destination / (stem + '.png'), destination / (stem + '.bmp')
        Image.frombytes('RGBA', (r['width'], r['height']), r['_rgba']).save(png)
        write_rgba_bmp(bmp, r['width'], r['height'], r['_rgba'])
        (destination / (stem + '.texture.bin')).write_bytes(r.pop('_texture'))
        (destination / (stem + '.clut.bin')).write_bytes(r.pop('_clut'))
        r.pop('_rgba')
        r.update(runtime_material_index=index, png=str(png), bmp=str(bmp), bmp_sha256=sha(bmp.read_bytes()),
                 bmp_encoding='BITMAPV4HEADER BGRA32 BI_BITFIELDS with explicit RGBA masks')
        p = r['parameters']
        values = [index, (Path(material_relative) / bmp.name).as_posix(), p['alpha_test_ref'], int(p['alpha_blend_enabled']),
                  *p['uv_scale'], *p['uv_offset'], int(p['wrap_u'] == 'clamp'), int(p['wrap_v'] == 'clamp')]
        manifest_lines.append(' '.join(map(str, values)))
    manifest_path = destination / 'original_actor_materials.txt'
    manifest_path.write_text('\n'.join(manifest_lines) + '\n', encoding='utf-8')
    report = {'schema': 'original-actor-runtime-materials/v1', 'materials': [resources[k] for k in keys],
              'packets': [{'packet': p['draw'], 'vertex_sha256': p['vertex_sha256'],
                           'runtime_material_index': indices[packet_materials[p['draw']]]} for p in metadata['packets']],
              'observations': observations, 'material_manifest': str(manifest_path)}
    (destination / 'materials.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report, next(iter(flags_by_material))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['metadata', 'manifest', 'timing', 'canonical-aya-report', 'runtime-root', 'report']:
        ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--aligned-manifest', type=Path)
    ap.add_argument('--output-model', type=Path, default=Path('assets/models/original_actor_source.bin'))
    ap.add_argument('--material-directory', type=Path, default=Path('assets/materials/original_actor'))
    ap.add_argument('--floor-policy', choices=['first-pose-min', 'canonical', 'zero', 'explicit'], default='first-pose-min')
    ap.add_argument('--floor', type=float)
    args = ap.parse_args()
    protected = [args.metadata, args.manifest, args.timing, args.canonical_aya_report]
    if any(args.report.resolve() == p.resolve() for p in protected):
        raise ValueError('export report must not overwrite any original input')
    metadata = json.loads(args.metadata.read_text(encoding='utf-8'))
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    timing = json.loads(args.timing.read_text(encoding='utf-8'))
    canonical = json.loads(args.canonical_aya_report.read_text(encoding='utf-8'))
    if metadata['schema'] != 'original-actor-skeleton-draw-metadata/v1' or canonical['schema'] != 'aya-source-skin-export/v2':
        raise ValueError('unexpected metadata/canonical Aya scale report schema')
    units = float(canonical['pc_units_per_original_unit'])
    if not np.isfinite(units) or units <= 0:
        raise ValueError('invalid canonical Aya scene scale')
    matrices, times, validation = validate_sources(metadata, manifest, args.manifest, timing['cpu_hz'])
    aligned_path = args.aligned_manifest or args.manifest.with_name('manifest_aligned.json')
    if aligned_path.resolve() in [p.resolve() for p in protected]:
        raise ValueError('aligned manifest must not overwrite an original input')
    aligned, retained = align_ge(manifest, metadata, args.manifest, aligned_path)
    packets, count = metadata['packets'], metadata['summary']['bone_count']
    vertices = [v for p in packets for v in p['vertices']]
    reference = pose_vertices(vertices, matrices[0])
    actual_floor = float(reference[:, 1].min())
    if args.floor_policy == 'explicit':
        if args.floor is None:
            raise ValueError('explicit floor policy requires --floor')
        floor = args.floor
    else:
        if args.floor is not None:
            raise ValueError('--floor requires explicit floor policy')
        floor = {'first-pose-min': actual_floor, 'canonical': canonical['reference_floor'], 'zero': 0}[args.floor_policy]
    if not np.isfinite(floor):
        raise ValueError('nonfinite actor floor')
    materials, flags = export_materials(retained, metadata, args.runtime_root, args.material_directory)
    material_by_packet = {p['packet']: p['runtime_material_index'] for p in materials['packets']}
    content = bytearray(struct.pack('<8s8I4f', b'T3BSKN2\0', 2, count, len(packets), len(vertices), len(times),
                                    len(materials['materials']), flags, 0, 0, units, floor, 0))
    content.extend(struct.pack('<' + str(count) + 'i', *[b['parent'] for b in metadata['bones']]))
    first = 0
    for packet in packets:
        if packet['vertex_count'] % 3 or packet['vtype'] & 3 != 2 or (packet['vtype'] >> 7) & 3 != 2 or (packet['vtype'] >> 5) & 3 != 1:
            raise ValueError('verified actor requires triangle lists, UV16, POS16, NORMAL8')
        content.extend(struct.pack('<4I', first, packet['vertex_count'], material_by_packet[packet['draw']], 3))
        first += packet['vertex_count']
    for vertex in vertices:
        inf = vertex['influences']
        ids = [i for i, w in inf] + [0] * (8 - len(inf))
        weights = [w for i, w in inf] + [0] * (8 - len(inf))
        content.extend(struct.pack('<8fI8I8f', *[v / 32768 for v in vertex['position_raw']],
                                   *[v / 32768 for v in vertex['uv_raw']], *[v / 128 for v in vertex['normal_raw']],
                                   len(inf), *ids, *weights))
    content.extend(times.tobytes());content.extend(matrices.tobytes())
    expected = 56 + count * 4 + len(packets) * 16 + len(vertices) * 100 + len(times) * (4 + count * 48)
    if len(content) != expected:
        raise ValueError('generic SourceSkin binary byte count mismatch')
    output = resolve_output_model(args.runtime_root, args.output_model)
    if output == Path(canonical['output']).resolve():
        raise ValueError('actor export must not overwrite the canonical Aya model')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    reference_obj = output.with_name(output.stem + '_reference.obj')
    lines = ['# Original source-weighted actor pose in original units; PC scale/floor declared by binary.']
    lines += ['v %.9g %.9g %.9g' % tuple(p) for p in reference]
    lines += ['vt %.9g %.9g' % tuple(v / 32768 for v in vertex['uv_raw']) for vertex in vertices]
    lines += [f'f {i+1}/{i+1} {i+2}/{i+2} {i+3}/{i+3}' for i in range(0, len(vertices), 3)]
    reference_obj.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    intervals = np.diff([f['ticks'] for f in manifest['frames']]) / timing['cpu_hz']
    report = {'schema': 'original-actor-source-skin-export/v1', 'passed': True, 'output': str(output),
        'binary_sha256': sha(content), 'binary_bytes': len(content), 'reference_obj': str(reference_obj),
        'ordered_geometry_sha256': metadata['summary']['ordered_geometry_sha256'],
        'bones': count, 'packets': len(packets), 'vertices': len(vertices), 'triangles': len(vertices) // 3,
        'samples': len(times), 'sample_times_seconds': times.tolist(), 'saved_cpu_hz': timing['cpu_hz'],
        'duration_seconds': float(times[-1]), 'median_interval_seconds': float(np.median(intervals)),
        'min_interval_seconds': float(intervals.min()), 'max_interval_seconds': float(intervals.max()),
        'pc_units_per_original_unit': units, 'canonical_scale_source': identity(args.canonical_aya_report),
        'reference_floor': floor, 'actual_reference_floor': actual_floor, 'floor_policy': args.floor_policy,
        'weights_renormalized': False, 'source_weight_sum_range': metadata['summary']['vertex_weight_sum_range'],
        'reference_bbox_original_units': [reference.min(0).tolist(), reference.max(0).tolist()],
        'reference_bbox_pc': [(reference.min(0) - [0, floor, 0]) * units, (reference.max(0) - [0, floor, 0]) * units],
        'materials': len(materials['materials']), 'material_manifest': materials['material_manifest'],
        'material_manifest_identity': identity(Path(materials['material_manifest'])),
        'material_report': identity(Path(materials['material_manifest']).with_name('materials.json')),
        'ge_alignment': aligned['geAlignment'], 'source_validation': validation,
        'inputs': {name: identity(path) for name, path in [('metadata', args.metadata), ('manifest', args.manifest),
                   ('aligned_manifest', aligned_path), ('timing', args.timing)]},
        'limitations': ['An actor-specific original capture, not a recovered complete original animation library.',
                       'No species or anatomical names are inferred; original source indices and hierarchy are preserved.',
                       'Only independently aligned GE samples prove draw-palette binding; other poses retain captured original records and arithmetic validation.',
                       'Actor WORLD is used for exact source/GE alignment but not baked into local skin matrices; M1 supplies actor placement/yaw.',
                       'Original texture pixels/alpha are preserved; current M1 lighting/culling remain presentation choices.',
                       'Original sample times are retained and final sample holds; interpolation is a PC presentation choice.']}
    report['reference_bbox_pc'] = [p.tolist() for p in report['reference_bbox_pc']]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['passed', 'output', 'bones', 'packets', 'vertices', 'triangles', 'samples', 'duration_seconds', 'material_manifest']}))


if __name__ == '__main__':
    main()
