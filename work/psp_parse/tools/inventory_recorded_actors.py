"""Inventory observed weighted actors by PRIM-time state, without naming anatomy.

An observed WORLD group is an extraction candidate, not proof of a complete
source actor, skeleton, enemy species, or FEP resource identity. Writes only
the explicitly selected inventory output directory.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image, ImageDraw

from exact_aya_materials import decode_texture, iter_material_draws, material_parameters
from export_aya_actual_weapon import WEAPON_SHA, affine, matrix_draws
from extract_runtime_character import decode_uv, layout, read_ppdmp


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bbox(points):
    return [points.min(axis=0).tolist(), points.max(axis=0).tolist()]


def skin_draw(draw, push):
    vt, count = draw['vtype'], draw['count']
    if draw['primitive'] != 3 or count % 3 or vt & ((3 << 11) | (7 << 18) | (1 << 23)):
        raise ValueError('only nonindexed, unmorphed, nonthrough triangle lists supported')
    stride, offsets = layout(vt)
    raw = push[draw['pointer']:draw['pointer'] + draw['size']]
    if len(raw) != count * stride:
        raise ValueError('record size differs from PRIM count * vertex stride')
    nw, wt, po = ((vt >> 14) & 7) + 1, (vt >> 9) & 3, (vt >> 7) & 3
    if not wt or not po:
        raise ValueError('weighted positions required')
    width, code, denominator = {1: (1, 'B', 128), 2: (2, 'H', 32768), 3: (4, 'f', 1)}[wt]
    position_code, position_scale = {1: ('b', 128), 2: ('h', 32768), 3: ('f', 1)}[po]
    positions = np.asarray([struct.unpack_from('<3' + position_code, raw, v * stride + offsets['pos'][0])
                            for v in range(count)], dtype=float) / position_scale
    weights = np.asarray([[struct.unpack_from('<' + code, raw, v * stride + offsets['wt'][0] + slot * width)[0]
                           for slot in range(nw)] for v in range(count)], dtype=float) / denominator
    if not np.isfinite(weights).all() or np.any(weights < 0):
        raise ValueError('nonfinite/negative source weight')
    posed = np.zeros((count, 3), dtype=float)
    influences = []
    for slot in range(nw):
        if not np.any(weights[:, slot] > 0):
            continue
        words = draw['bones'][slot * 12:slot * 12 + 12]
        if any(x is None for x in words):
            raise ValueError('active BONE matrix lacks explicit recorded GE provenance')
        matrix = affine(words)
        posed += weights[:, slot, None] * (positions @ matrix[:3, :3].T + matrix[:3, 3])
        influences.append({'palette_index': slot, 'payload': words,
                           'payload_sha256': sha(struct.pack('<12I', *words)),
                           'positive_vertex_count': int(np.sum(weights[:, slot] > 0)),
                           'weight_sum': float(weights[:, slot].sum())})
    world, view = affine(draw['world']), affine(draw['view'])
    world_points = posed @ world[:3, :3].T + world[:3, 3]
    camera_points = world_points @ view[:3, :3].T + view[:3, 3]
    return posed, world_points, camera_points, {
        'stride': stride, 'weight_components': nw, 'active_palette': influences,
        'weight_sum_range': [float(weights.sum(axis=1).min()), float(weights.sum(axis=1).max())],
        'raw_normalized_bbox': bbox(positions), 'posed_local_bbox': bbox(posed),
        'world_bbox': bbox(world_points), 'camera_bbox': bbox(camera_points),
        'vertices': count, 'triangles': count // 3,
    }


def write_projection(path, points):
    # Inspection projection, not an interpretation of the enemy's identity.
    image = Image.new('RGB', (1200, 520), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    for col, (horizontal, vertical, label) in enumerate([(0, 1, 'local X/Y'), (2, 1, 'local Z/Y')]):
        xy = points[:, [horizontal, vertical]]
        lo, hi = xy.min(0), xy.max(0)
        scale = min(540 / max(hi[0] - lo[0], 1e-9), 440 / max(hi[1] - lo[1], 1e-9))
        transformed = (xy - (lo + hi) / 2) * scale
        transformed[:, 0] += col * 600 + 300
        transformed[:, 1] = 270 - transformed[:, 1]
        for start in range(0, len(points), 3):
            tri = [tuple(p) for p in transformed[start:start + 3]]
            draw.polygon(tri, fill=(100, 115, 130), outline=(45, 55, 65))
        draw.text((col * 600 + 24, 18), label, fill='black')
    image.save(path)


def inventory(captures, metadata_path, out, world_traces=(), texture_index=None):
    out.mkdir(parents=True, exist_ok=True)
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    excluded = {p['vertex_sha256']: 'exact_Aya_packet' for p in metadata['packets']}
    excluded[WEAPON_SHA] = 'exact_original_weapon'
    trace_inputs = [(path, json.loads(path.read_text(encoding='utf-8'))) for path in world_traces]
    texture_candidates = None if texture_index is None else json.loads(texture_index.read_text(encoding='utf-8'))['textures']
    result = {'schema': 'recorded-actor-inventory/v1', 'metadata': str(metadata_path.resolve()),
              'metadata_sha256': sha(metadata_path.read_bytes()), 'captures': [],
              'world_trace_inputs': [{'path': str(p.resolve()), 'sha256': sha(p.read_bytes())} for p in world_traces],
              'legacy_texture_index': None if texture_index is None else {'path': str(texture_index.resolve()), 'sha256': sha(texture_index.read_bytes()),
                  'matching_scope': 'truncated SHA1 index is candidate lookup only; absence is not proof of absence from ISO'},
              'limitations': ['Grouping by exact WORLD/VIEW only identifies observed render instances, not source skeleton identity.',
                              'A complete recorded triangle set does not prove unseen/culled parts, LODs or the complete original asset.',
                              'Exact GE palette matrices and weights permit same-frame skin replay; source bone indices, parents and continuous animations remain unresolved.',
                              'Twisted identity is a visual/gameplay hypothesis until compared with in-game evidence; no species name is inferred.',
                              'Runtime texture/CLUT decode does not identify an original pack/FEP resource.']}
    for capture in captures:
        commands, push = read_ppdmp(str(capture))
        materials = {(d['register_record'], d['register_word']): d for d in iter_material_draws(commands, push)}
        groups, rejected, exclusions = defaultdict(list), [], Counter()
        for d in matrix_draws(commands, push):
            if d['sha256'] in excluded:
                exclusions[excluded[d['sha256']]] += 1
                continue
            if not (d['vtype'] >> 9) & 3:
                continue
            if any(v is None for v in d['world'] + d['view']):
                rejected.append({'vertex_record': d['vertex_record'], 'reason': 'missing explicit WORLD/VIEW'})
                continue
            groups[(tuple(d['world']), tuple(d['view']))].append(d)
        summary = {'path': str(capture.resolve()), 'sha256': sha(capture.read_bytes()),
                   'excluded': dict(exclusions), 'groups': [], 'rejected': rejected}
        for number, ((world, view), draws) in enumerate(groups.items()):
            identity = sha(b''.join(bytes.fromhex(d['sha256']) for d in draws))
            group = {'index': number, 'ordered_geometry_sha256': identity,
                     'world_payload': world, 'view_payload': view,
                     'world_matrix_rows': affine(world)[:3].tolist(), 'view_matrix_rows': affine(view)[:3].tolist(),
                     'vtypes': dict(Counter(hex(d['vtype']) for d in draws)),
                     'draws': [], 'materials': {}, 'unresolved': [], 'exact_world_trace_matches': []}
            for trace_path, trace in trace_inputs:
                for row in trace['worlds']:
                    values = row.get('sourceMatrix', [])
                    payload = row.get('worldPayload')
                    if payload is None and len(values) == 16:
                        payload = [(values[i] >> 8) & 0xffffff for i in [0,1,2,4,5,6,8,9,10,12,13,14]]
                    if payload != list(world):
                        continue
                    gpr = row.get('gpr', [None] * 32)
                    group['exact_world_trace_matches'].append({'trace': str(trace_path.resolve()), 'index': row['index'],
                        'kind': row['kind'], 'matrix_pointer': row.get('matrixPointer'), 'object_register_s1': gpr[17],
                        'saved_caller_callsite': None if 'savedCallerRa' not in row else row['savedCallerRa'] - 8,
                        'scope': 'exact WORLD payload cross-capture correlation; pointer is not a persistent resource ID'})
            posed_all, world_all, camera_all, uv_all = [], [], [], []
            for d in draws:
                entry = {k: d[k] for k in ['vertex_record', 'register_record', 'register_word', 'sha256', 'vtype', 'primitive', 'count']}
                try:
                    posed, wp, cp, facts = skin_draw(d, push)
                    entry.update(facts)
                    posed_all.append(posed);world_all.append(wp);camera_all.append(cp)
                    stride, offsets = layout(d['vtype'])
                    raw = push[d['pointer']:d['pointer'] + d['size']]
                    uv_all.extend(decode_uv(raw, vertex * stride + offsets['uv'][0], d['vtype'] & 3)
                                  if 'uv' in offsets else (0.0, 0.0) for vertex in range(d['count']))
                    material = materials[(d['register_record'], d['register_word'])]
                    texture, registers = material['texture0'], material['registers']
                    if texture is None or texture['framebuffer']:
                        raise ValueError('no ordinary recorded texture bytes')
                    material_identity = sha(bytes.fromhex(texture['sha256']) + material['clut'][:1024]
                                            + json.dumps(material_parameters(registers), sort_keys=True).encode())
                    entry['material_id'] = material_identity
                    if material_identity not in group['materials']:
                        rgba, texture_facts = decode_texture(texture['raw'], registers, material['clut'], material['clut_known'])
                        filename = out / f'candidate_{identity[:12]}_{material_identity[:12]}.png'
                        Image.frombytes('RGBA', (texture_facts['width'], texture_facts['height']), rgba).save(filename)
                        group['materials'][material_identity] = {
                            'texture_sha256': texture['sha256'], 'texture_sha1_12': hashlib.sha1(texture['raw']).hexdigest()[:12],
                            'clut_ram_sha256': sha(material['clut'][:1024]), 'clut_records': material['clut_records'],
                            'texture_record': texture['record'], 'texture_guest_address': (registers[0xa0] & 0xfffff0) | ((registers[0xa8] << 8) & 0x0f000000),
                            'clut_guest_address': (registers[0xb0] & 0xfffff0) | ((registers[0xb1] << 8) & 0x0f000000),
                            'png': str(filename.resolve()), 'parameters': material_parameters(registers), **texture_facts}
                        group['materials'][material_identity]['legacy_pack_texture_candidates'] = None if texture_candidates is None else [
                            item for item in texture_candidates if item['pixel_sha1'] == hashlib.sha1(texture['raw']).hexdigest()[:12]]
                except (ValueError, KeyError) as error:
                    entry['unresolved'] = str(error)
                    group['unresolved'].append({'vertex_record': d['vertex_record'], 'reason': str(error)})
                group['draws'].append(entry)
            group['draw_count'] = len(draws)
            group['vertex_count'] = sum(d['count'] for d in draws)
            group['triangle_count'] = sum(d['count'] // 3 for d in draws if d['primitive'] == 3)
            group['active_matrix_payload_count'] = len({p['payload_sha256'] for d in group['draws'] for p in d.get('active_palette', [])})
            if posed_all:
                posed, wp, cp = map(np.concatenate, [posed_all, world_all, camera_all])
                group.update(posed_local_bbox=bbox(posed), world_bbox=bbox(wp), camera_bbox=bbox(cp))
                stem = f'{capture.parent.name}_candidate_{identity[:12]}'
                obj = out / (stem + '_pose.obj')
                mtl = out / (stem + '_pose.mtl')
                lines = ['# Exact observed GE skin pose; source skeleton and identity unresolved.', 'mtllib ' + mtl.name]
                lines += ['v %.9g %.9g %.9g' % tuple(p) for p in posed]
                lines += ['vt %.9g %.9g' % tuple(uv) for uv in uv_all]
                at = 0
                for entry in group['draws']:
                    if 'vertices' not in entry:
                        continue
                    if 'material_id' in entry:
                        lines.append('usemtl material_' + entry['material_id'][:16])
                    for i in range(at, at + entry['vertices'], 3):
                        lines.append('f %d/%d %d/%d %d/%d' % (i+1, i+1, i+2, i+2, i+3, i+3))
                    at += entry['vertices']
                mtl.write_text('\n'.join('newmtl material_' + key[:16] + '\nKd 1 1 1\nd 1\nmap_Kd ' + Path(material['png']).name + '\n'
                                         for key, material in group['materials'].items()), encoding='utf-8')
                obj.write_text('\n'.join(lines) + '\n', encoding='utf-8')
                projection = out / (stem + '_projection.png')
                write_projection(projection, posed)
                group.update(posed_obj=str(obj.resolve()), material_mtl=str(mtl.resolve()),
                             obj_uv_convention='original normalized PSP UV, no artificial V flip; MTL is an inspection approximation of GE shader state',
                             projection=str(projection.resolve()))
            summary['groups'].append(group)
        result['captures'].append(summary)
    identities = defaultdict(list)
    for capture in result['captures']:
        for g in capture['groups']:
            identities[g['ordered_geometry_sha256']].append({'capture': capture['path'], 'draw_count': g['draw_count'],
                                                            'vertices': g['vertex_count'], 'triangles': g['triangle_count']})
    result['cross_capture_geometry_groups'] = dict(identities)
    (out / 'inventory.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    md = ['# Recorded original actor candidate inventory', '',
          'This is a raw GE extraction inventory; no enemy species or complete source skeleton is asserted.', '']
    for capture in result['captures']:
        md += [f'## {Path(capture["path"]).parent.name}', '', f'Input SHA256: `{capture["sha256"]}`', '',
               f'Excluded exact known geometry: `{capture["excluded"]}`', '']
        for g in capture['groups']:
            md += [f'Candidate geometry group `{g["ordered_geometry_sha256"]}`', '',
                   f'- Draws: {g["draw_count"]}; vertices: {g["vertex_count"]}; triangles: {g["triangle_count"]}.',
                   f'- VTYPEs: `{g["vtypes"]}`.', f'- Posed local bbox: `{g.get("posed_local_bbox")}`.',
                   f'- World bbox: `{g.get("world_bbox")}`.',
                   f'- Distinct active GE matrix payloads: {g["active_matrix_payload_count"]}; this is not a source bone count.',
                   f'- Material groups: {len(g["materials"])}; unresolved draws: {len(g["unresolved"])}.',
                   f'- Exact posed inspection OBJ: `{g.get("posed_obj")}`.',
                   f'- Projection: `{g.get("projection")}`.', '']
            for material in g['materials'].values():
                md += [f'- Original material: {material["width"]}x{material["height"]} {material["format"]}, swizzled={material["swizzled"]}, palette={material["clut_format"]}.',
                       f'- TEXTURE0 SHA256: `{material["texture_sha256"]}`.',
                       f'- CLUT RAM SHA256: `{material["clut_ram_sha256"]}`.',
                       f'- Decoded RGBA SHA256: `{material["rgba_sha256"]}`; nonopaque texels={material["alpha_nonopaque_pixels"]}.',
                       f'- Original texture PNG: `{material["png"]}`.',
                       f'- Legacy pack candidate lookup: `{material["legacy_pack_texture_candidates"]}`; this is a partial index, not a complete ISO exclusion.', '']
            for match in g['exact_world_trace_matches']:
                md += [f'- Existing WORLD trace match: record {match["index"]}, matrix pointer `{match["matrix_pointer"]:#x}`, '
                       f'object s1 `{match["object_register_s1"]:#x}`, caller `{match["saved_caller_callsite"]:#x}`. '
                       'This is a cross-capture WORLD correlation; object pointers are not persistent identities.', '']
    md += ['## Limits', ''] + ['- ' + text for text in result['limitations']]
    (out / 'inventory.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(out.resolve()), 'capture_count': len(captures),
                      'geometry_groups': len(identities), 'groups': [g for g in identities.values()]}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, action='append', required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--world-trace', type=Path, action='append', default=[])
    parser.add_argument('--legacy-texture-index', type=Path)
    args = parser.parse_args()
    inventory(args.capture, args.metadata, args.out, args.world_trace, args.legacy_texture_index)
