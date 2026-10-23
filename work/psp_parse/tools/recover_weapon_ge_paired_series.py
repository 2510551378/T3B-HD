"""Recover the exact weapon PRIM paired with Aya in the SAME retained GE dump.

No socket inference, cross-run alignment or copied actor transformation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from PIL import Image
from exact_aya_materials import decode_texture, initial_registers, iter_material_draws, material_parameters
from extract_runtime_character import layout, read_ppdmp

ROOT = Path(__file__).resolve().parents[1]
GEOMETRY = '168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a'


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def f24(v):
    return struct.unpack('<f', struct.pack('<I', v << 8))[0]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True); a = p.parse_args()
    check(not a.out.exists(), 'Never overwrite paired capture evidence'); a.out.mkdir(parents=True)
    source = ROOT / 'out/AYA_GE_SAMPLE_SERIES_20261020/inputs_v2/inputs.json'
    body = json.loads(source.read_text(encoding='utf-8'))
    check(body['passed'] and body['original_clut_material_bindings_verified'], 'Body recovery failed')
    frames = [f for f in body['frames'] if f['group'] == 'slot0_fire_verified']
    check(len(frames) == 12, 'Expected all12 original same-dump shooting-input samples')
    cap_by_key = {c['key']: c for c in body['captures']}
    observations = []; output_frames = []; captures = []; material_variants = {}
    binary = a.out / 'lighting_inputs.bin'; first = 0
    expected_texture = ROOT.parent / 't3b_unreal/Content/SourceData/textures/rgba_61aae23a2efeb6a31d85abfb.png'
    expected_rgba = Image.open(expected_texture).convert('RGBA').tobytes()
    with binary.open('wb') as output:
        output.write(b'T3BLIT1\0' + struct.pack('<I', 12))
        for frame in frames:
            capture = cap_by_key[frame['capture']]; path = Path(capture['path'])
            check(sha(path.read_bytes()) == capture['sha256'], 'Actual shared GE dump changed')
            commands, push = read_ppdmp(str(path)); selected = []
            for draw in iter_material_draws(commands, push):
                regs = draw['registers']; v = draw['vertices']; vt = regs.get(0x12)
                if vt is None:
                    continue
                vertex = push[v['pointer']:v['pointer'] + v['bytes']]
                if sha(struct.pack('<I', vt) + vertex) != GEOMETRY:
                    continue
                check(draw['count'] == 243 and draw['primitive'] == 3, 'Original weapon topology differs')
                tex = draw['texture0']; check(tex is not None and not tex['framebuffer'], 'No recorded weapon texture')
                rgba, facts = decode_texture(tex['raw'], regs, draw['clut'], draw['clut_known'])
                check(rgba == expected_rgba, 'Recorded weapon RGBA differs from staged original texture')
                params = material_parameters(regs)
                identity = dict(texture_sha256=tex['sha256'], clut_ram_sha256=sha(draw['clut'][:1024]),
                                decode_registers={hex(k): regs[k] for k in (0xc3, 0xb8, 0xa8, 0xc2, 0xc5)},
                                rgba_sha256=facts['rgba_sha256'], parameters=params)
                material_id = sha(json.dumps(identity, sort_keys=True).encode())
                if material_id not in material_variants:
                    png = a.out / ('weapon_' + material_id[:16] + '.png')
                    Image.frombytes('RGBA', (facts['width'], facts['height']), rgba).save(png)
                    material_variants[material_id] = dict(identity, decoded_facts=facts, png=str(png.resolve()), png_sha256=sha(png.read_bytes()))
                selected.append((draw, vertex, dict(regs), material_id))
            check(len(selected) == 1, 'Shared GE frame must contain exactly one true weapon draw')
            draw, vertex, expected, material_id = selected[0]
            target = (draw['register_record'], draw['register_word'])
            matrices = {k: [None] * n for k, n in [('world', 12), ('view', 12), ('projection', 16), ('bones', 96)]}
            cursors = {k: 0 for k in matrices}; regs = {}; found = False
            for record, (kind, size, ptr) in enumerate(commands):
                check(ptr + size <= len(push), 'Invalid recorded extent'); raw = push[ptr:ptr + size]
                if kind == 0:
                    regs = initial_registers(raw)
                elif kind == 1:
                    check(size % 4 == 0, 'Partial GE word')
                    for wi in range(size // 4):
                        word = struct.unpack_from('<I', raw, wi * 4)[0]; cmd, val = word >> 24, word & 0xffffff
                        regs[cmd] = val
                        if cmd in (0x3a, 0x3c, 0x3e, 0x2a):
                            key = {0x3a:'world', 0x3c:'view', 0x3e:'projection', 0x2a:'bones'}[cmd]
                            cursors[key] = val & (127 if key == 'bones' else 15)
                        elif cmd in (0x3b, 0x3d, 0x3f, 0x2b):
                            key = {0x3b:'world', 0x3d:'view', 0x3f:'projection', 0x2b:'bones'}[cmd]
                            i = cursors[key]
                            if i < len(matrices[key]):
                                matrices[key][i] = val
                            cursors[key] = (i + 1) & (127 if key == 'bones' else 15)
                        if cmd != 4 or (record, wi) != target:
                            continue
                        check(not found and regs == expected, 'Weapon material/matrix replay differs'); found = True
                        vt = regs[0x12]; count = val & 65535; slots = ((vt >> 14) & 7) + 1
                        check(vt == 0x522 and slots == 1 and len(vertex) == 243 * 16, 'Original gun format changed')
                        check(all(x is not None for k in ('world', 'view', 'projection') for x in matrices[k])
                              and all(x is not None for x in matrices['bones'][:12]), 'Original weapon matrices missing')
                        paired = body['draws'][frame['first_draw']:frame['first_draw'] + 106]
                        check(all(d['VIEW_payload'] == matrices['view'] and d['PROJECTION_payload'] == matrices['projection']
                                  for d in paired), 'Weapon uses a different original camera; world-space overlay would be invalid')
                        start = output.tell()
                        output.write(struct.pack('<256I', *[regs.get(i, 0) for i in range(256)]))
                        output.write(struct.pack('<12f', *map(f24, matrices['world'])))
                        output.write(struct.pack('<96f', *[f24(x) if x is not None else 0 for x in matrices['bones']]))
                        output.write(struct.pack('<2I', count, slots)); stride, off = layout(vt)
                        for i in range(count):
                            at = i * stride
                            position = [x / 32768 for x in struct.unpack_from('<3h', vertex, at + off['pos'][0])]
                            normal = [x / 128 for x in struct.unpack_from('<3b', vertex, at + off['nrm'][0])]
                            weights = [struct.unpack_from('<H', vertex, at + off['wt'][0])[0] / 32768] + [0] * 7
                            uv = [x / 32768 for x in struct.unpack_from('<2H', vertex, at + off['uv'][0])]
                            output.write(struct.pack('<16f', *(position + normal + weights + uv)))
                        observations.append(dict(capture=frame['capture'], group=frame['group'], sample=frame['sample'], packet=0,
                                                 vertex_sha256=GEOMETRY, vertex_count=count, weight_slots=1, vtype=vt,
                                                 register_record=record, register_word=wi, material_id=material_id,
                                                 binary_byte_offset=start, first_output_vertex=first,
                                                 WORLD_payload=matrices['world'][:], VIEW_payload=matrices['view'][:],
                                                 PROJECTION_payload=matrices['projection'][:],
                                                 body_GE_command_before_weapon=all((d['register_record'], d['register_word']) < target for d in paired),
                                                 same_original_camera_as_all106_body_draws=True))
                        output_frames.append(dict(group=frame['group'], sample=frame['sample'], capture=frame['capture'],
                                                  first_draw=len(observations) - 1, draw_count=1, first_output_vertex=first, vertices=243,
                                                  body_frame_index=body['frames'].index(frame), paired_body_first_vertex=frame['first_output_vertex'],
                                                  original_time_seconds=None, preview_time_seconds=frame['preview_time_seconds']))
                        first += count
            check(found, 'Weapon PRIM not replayed'); captures.append(capture)
    check(len(observations) == 12 and first == 2916 and len(material_variants) == 1, 'Original gun sample coverage changed')
    result = dict(schema='weapon-original-ge-paired-lighting-inputs/v1', passed=True,
                  paired_body_input=dict(file=str(source.resolve()), sha256=sha(source.read_bytes())),
                  binary=dict(file=str(binary.resolve()), bytes=binary.stat().st_size, sha256=sha(binary.read_bytes())),
                  captures=captures, frames=output_frames, draws=observations, draw_count=12, total_vertices=first,
                  materials=material_variants, staged_original_texture=dict(file=str(expected_texture.resolve()), sha256=sha(expected_texture.read_bytes())),
                  original_texture_rgba_bytes_equal=True, same_GE_dump_pairing=True, original_camera_match=True,
                  original_timing_verified=False, anatomical_socket_inferred=False, muzzle_semantics_confirmed=False,
                  producer_sha256=sha(Path(__file__).read_bytes()),
                  limits=['Only12 shared captured GE frames, not a recovered authored gun animation.',
                          'Transforms are actual weapon WORLD/BONE uploads, not a named hand/socket reconstruction.',
                          'Idle series contains no matching weapon draw; never insert a guessed gun there.',
                          'No original GPU pixels or muzzle markers/effects are certified.'])
    (a.out / 'inputs.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, same_dump_samples=12, vertices=2916, same_original_camera=True)))


if __name__ == '__main__':
    main()
