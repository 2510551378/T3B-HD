"""Recover an explicitly selected original actor's source hierarchy and palettes.

Uses the same observed ULJM05798 metadata contract as Aya, with a variable
source count. Species and anatomical names are deliberately not inferred.
No source file or capture is modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

from recover_aya_skeleton_metadata import Memory, packed_words, vertex_layout


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identity(path):
    return {'path': str(path.resolve()), 'sha256': sha(path.read_bytes())}


def load_snapshot(path):
    snap = json.loads(path.read_text(encoding='utf-8'))
    required = ['metadata', 'sourceBase', 'descriptors', 'drawTable', 'header',
                'descriptorWords', 'drawWords', 'records']
    if any(key not in snap for key in required):
        raise ValueError('snapshot lacks the explicitly captured metadata/source segments')
    if snap.get('schema') not in ['original-actor-metadata-snapshot/v1', 'actor-metadata-snapshot/v1',
                                  'aya-metadata-snapshot/v1']:
        raise ValueError('unsupported snapshot schema')
    count = struct.unpack_from('<h', packed_words(snap['header']), 6)[0]
    rows = {row['index']: row for row in snap['records']}
    if len(rows) != len(snap['records']) or set(rows) != set(range(count)):
        raise ValueError('snapshot must contain each source record exactly once')
    segments = [(snap['metadata'], packed_words(snap['header'])),
                (snap['descriptors'], packed_words(snap['descriptorWords'])),
                (snap['drawTable'], packed_words(snap['drawWords']))]
    for row in rows.values():
        if len(row['words']) != 0x130 // 4:
            raise ValueError('source record must contain all 0x130 original bytes')
        segments.append((snap['sourceBase'] + row['index'] * 0x130, packed_words(row['words'])))
    return snap, Memory(segments)


def recover(mem, metadata, source_base, expected_bones=None, expected_packets=None, expected_group=None):
    count = mem.unpack('<h', metadata + 6)[0]
    if not 1 <= count <= 64 or expected_bones is not None and count != expected_bones:
        raise ValueError(f'actor source bone count {count} outside selected/runtime contract')
    descriptors = mem.unpack('<I', metadata + 0x18)[0]
    table = mem.unpack('<I', metadata + 0x34)[0]
    descriptor_bytes = mem.read(descriptors, count * 16)
    bones = []
    for index in range(count):
        raw = struct.unpack_from('<8h', descriptor_bytes, index * 16)
        parent = raw[7]
        if not -1 <= parent < count or parent == index:
            raise ValueError(f'bone {index}: invalid descriptor parent {parent}')
        address = source_base + index * 0x130
        actual = mem.unpack('<I', address + 0x124)[0]
        expected = 0 if parent < 0 else source_base + parent * 0x130
        if actual != expected:
            raise ValueError(f'bone {index}: runtime parent pointer differs from descriptor')
        bones.append({'index': index, 'parent': parent, 'children': [],
                      'descriptor_address': descriptors + index * 16, 'descriptor_signed16': list(raw),
                      'record_address': address, 'runtime_parent_pointer': actual,
                      'matrix_40_words': list(mem.unpack('<16I', address + 0x40)),
                      'matrix_80_words': list(mem.unpack('<16I', address + 0x80)),
                      'ge_command_words': list(mem.unpack('<12I', address + 0xc0)),
                      'flags_128': mem.unpack('<I', address + 0x128)[0]})
    for bone in bones:
        seen, parent = {bone['index']}, bone['parent']
        while parent >= 0:
            if parent in seen:
                raise ValueError('descriptor parent cycle')
            seen.add(parent)
            parent = bones[parent]['parent']
        if bone['parent'] >= 0:
            bones[bone['parent']]['children'].append(bone['index'])
    draw_count = mem.unpack('<h', table)[0]
    if not 0 < draw_count <= 4096 or expected_packets is not None and draw_count != expected_packets:
        raise ValueError(f'actor packet count {draw_count} differs from selection/runtime contract')
    packets, palette, active_sources = [], {}, set()
    cursor, sums = table + 4, []
    for draw in range(draw_count):
        nv, transform, flag4, updates, halfwords, flag7, vt = mem.unpack('<Hh4BI', cursor)
        if not nv or nv % 3 or updates > 8 or vt & (1 << 23):
            raise ValueError(f'draw {draw}: expected nonthrough triangle-list packet')
        stride, fields = vertex_layout(vt)
        if stride != halfwords * 2 or 'position' not in fields or 'weights' not in fields:
            raise ValueError(f'draw {draw}: stride/weighted position contract mismatch')
        at, palette_updates = cursor + 12, []
        for _ in range(updates):
            slot, source = mem.unpack('<hh', at);at += 4
            if not 0 <= slot < 8 or not 0 <= source < count:
                raise ValueError('invalid explicit palette update')
            palette[slot] = source
            palette_updates.append({'palette_index': slot, 'source_index': source})
        raw = mem.read(at, nv * stride)
        vertices, active_slots = [], set()
        nw = ((vt >> 14) & 7) + 1
        for vertex_index in range(nv):
            base = vertex_index * stride
            offset, kind = fields['weights']
            code, denominator = {1: ('B', 128), 2: ('H', 32768), 3: ('f', 1)}[kind]
            weights = struct.unpack_from('<' + str(nw) + code, raw, base + offset)
            if any(not math.isfinite(w) or w < 0 for w in weights) or not any(weights):
                raise ValueError('negative/nonfinite/all-zero original vertex weights')
            total = sum(weights) / denominator
            if not .95 <= total <= 1.01:
                raise ValueError('original weights outside current SourceSkin loader bounds')
            sums.append(total)
            influences = []
            for slot, weight in enumerate(weights):
                if weight == 0:
                    continue
                if slot not in palette:
                    raise ValueError('active palette slot has no explicit source index')
                source = palette[slot]
                influences.append([source, weight / denominator])
                active_sources.add(source);active_slots.add(slot)
            vertex = {'influences': influences, 'weight_storage_type': kind,
                      'weights_raw': list(weights), 'weight_denominator': denominator}
            for name in ['position', 'normal', 'uv']:
                if name not in fields:
                    continue
                offset, storage = fields[name]
                code = ({1: 'B', 2: 'H', 3: 'f'} if name == 'uv' else {1: 'b', 2: 'h', 3: 'f'})[storage]
                components = 2 if name == 'uv' else 3
                values = list(struct.unpack_from('<' + str(components) + code, raw, base + offset))
                if not all(math.isfinite(v) for v in values):
                    raise ValueError('nonfinite original vertex component')
                vertex[name + '_raw'] = values
            vertices.append(vertex)
        packets.append({'draw': draw, 'address': cursor, 'relative_offset': cursor - table,
                        'vertex_address': at, 'vertex_count': nv, 'stride': stride, 'vtype': vt,
                        'transform_index_raw': transform, 'flags_raw': [flag4, flag7],
                        'palette_updates': palette_updates, 'palette_state': {str(k): v for k, v in sorted(palette.items())},
                        'active_palette_indices': sorted(active_slots),
                        'vertex_sha256': sha(struct.pack('<I', vt) + raw), 'vertices': vertices})
        cursor = (at + len(raw) + 3) & ~3
    group = sha(b''.join(bytes.fromhex(p['vertex_sha256']) for p in packets))
    if expected_group is not None and group.lower() != expected_group.lower():
        raise ValueError(f'ordered geometry identity mismatch: {group}')
    active = sorted(active_sources)
    summary = {'bone_count': count, 'parent_pointer_matches': count,
               'roots': [b['index'] for b in bones if b['parent'] == -1],
               'draw_count': draw_count, 'vertex_count': sum(p['vertex_count'] for p in packets),
               'triangle_count': sum(p['vertex_count'] // 3 for p in packets),
               'draw_table_bytes': cursor - table, 'ordered_geometry_sha256': group,
               'expected_identity_verified': expected_group is not None,
               'active_source_indices': active, 'not_directly_weighted_indices': sorted(set(range(count)) - active_sources),
               'vertex_weight_sum_range': [min(sums), max(sums)],
               'descriptor_sha256': sha(descriptor_bytes), 'draw_table_sha256': sha(mem.read(table, cursor - table))}
    return {'schema': 'original-actor-skeleton-draw-metadata/v1', 'metadata_address': metadata,
            'source_base': source_base, 'descriptor_table': descriptors, 'draw_table': table,
            'summary': summary, 'bones': bones, 'packets': packets,
            'limitations': ['Actor selection requires ordered geometry identity, not bone count or address alone.',
                            'No species or anatomical names are assigned.',
                            'Descriptor quaternion/translation fields remain original signed16; their convention is not inferred.',
                            'Parent pointers and source palettes are parsed; raw weights are preserved without normalization.',
                            'A source snapshot is not assumed atomic unless the capture declares its completed source pass.']}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--snapshot', type=Path, required=True)
    ap.add_argument('--expected-bones', type=int)
    ap.add_argument('--expected-packets', type=int)
    ap.add_argument('--expected-geometry-sha256')
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    snap, memory = load_snapshot(args.snapshot)
    result = recover(memory, snap['metadata'], snap['sourceBase'], args.expected_bones,
                     args.expected_packets, args.expected_geometry_sha256)
    result['input'] = identity(args.snapshot)
    result['capture'] = {k: snap[k] for k in ['schema', 'object', 'ticks', 'boneIndex', 'completedSourcePass'] if k in snap}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    md = ['# Original actor hierarchy and explicit skin palettes', '', '```json',
          json.dumps(result['summary'], ensure_ascii=False, indent=2), '```', '',
          '| Source index | Parent index | Children |', '|---:|---:|---|']
    md += [f'| {b["index"]} | {b["parent"]} | {b["children"]} |' for b in result['bones']]
    md += [''] + ['- ' + x for x in result['limitations']]
    args.out.with_suffix('.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    print(json.dumps({'out': str(args.out.resolve()), 'summary': result['summary']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
