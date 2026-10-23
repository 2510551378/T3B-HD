"""Recover complete PRIM-time Aya lighting inputs from retained GE sample series.

Dump order is observed. CPU-breakpoint ticks do not timestamp the later GE dump;
30fps preview spacing is explicitly a presentation choice, never original timing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from exact_aya_materials import (decode_texture, initial_registers, iter_material_draws,
                                 material_parameters)
from extract_runtime_character import layout, read_ppdmp

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ('idle_long', 'manifest.json', 'a4774003b6a6a21c895f1b03029670af95f2b7dc30c029c97d60e2dd207a81f8', 60),
    ('slot0_fire_verified', 'manifest_runtime.json', '466c9c3a95b6d14cb7cbbee25936955b8459a0d325bc18e4dea0e04cb974875a', 12),
]
MATERIAL_SHA = 'ab1084ee816fce3a146b25be36f80cab8960089466c6725e2f3680b114d5ed93'


def check(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def f24(value):
    return struct.unpack('<f', struct.pack('<I', value << 8))[0]


def recover(out):
    check(not out.exists(), 'Never replace retained GE evidence')
    out.mkdir(parents=True)
    material_file = ROOT / 'out/AYA_NATIVE_GLTF_20261020/raw/input_materials.json'
    check(sha(material_file.read_bytes()) == MATERIAL_SHA, 'Frozen material source changed')
    materials = json.loads(material_file.read_text(encoding='utf-8'))
    packets = {p['vertex_sha256']: p for p in materials['packets']}
    check(len(packets) == 106, 'Original packet geometry must have unique identities')
    states = {}; decoded_materials = {}; draws = []; frames = []; captures = []; sources = []
    first = 0
    binary = out / 'lighting_inputs.bin'
    with binary.open('wb') as dest:
        dest.write(b'T3BLIT1\0' + struct.pack('<I', 106 * 72))
        for group, filename, digest, frame_count in SOURCES:
            source = ROOT / 'out/AYA_BONE_GE_ACTIONS' / group / filename
            check(sha(source.read_bytes()) == digest, 'Retained manifest changed')
            manifest = json.loads(source.read_text(encoding='utf-8'))
            check(len(manifest['frames']) == frame_count, 'Series length changed')
            sources.append(dict(group=group, path=str(source), sha256=digest, samples=frame_count))
            for sample, frame in enumerate(manifest['frames']):
                capture = Path(frame['dump']['file'])
                raw_dump = capture.read_bytes()
                check(len(raw_dump) == frame['dump']['bytes'], 'Dump extent changed')
                key = group + '/' + capture.name
                captures.append(dict(key=key, path=str(capture), sha256=sha(raw_dump)))
                commands, push = read_ppdmp(str(capture))
                targets = {}
                packet_order = []
                for draw in iter_material_draws(commands, push):
                    regs = draw['registers']; v = draw['vertices']
                    vt = regs.get(0x12)
                    if vt is None:
                        continue
                    vertex = push[v['pointer']:v['pointer'] + v['bytes']]
                    geometry = sha(struct.pack('<I', vt) + vertex)
                    if geometry not in packets:
                        continue
                    packet = packets[geometry]
                    check(draw['primitive'] == 3 and draw['count'] == packet['vertex_count'],
                          'Matched geometry has different primitive/count')
                    tex = draw['texture0']
                    check(tex is not None and not tex['framebuffer'], 'Aya texture backing unavailable')
                    params = material_parameters(regs)
                    stable = {k: v for k, v in params.items() if k not in
                              ('uv_storage_type', 'uv_raw_denominator', 'uv_formula')}
                    # Include every decode dependency, not only raw RAM hashes:
                    # the same CLUT bytes with a different CLUTFORMAT are distinct.
                    material_key = (tex['sha256'], sha(draw['clut'][:1024]),
                                    sha(json.dumps(stable, sort_keys=True).encode()),
                                    tuple(regs[k] for k in (0xc3, 0xb8, 0xa8, 0xc2, 0xc5)),
                                    sha(draw['clut_known']))
                    if material_key not in decoded_materials:
                        _, facts = decode_texture(tex['raw'], regs, draw['clut'], draw['clut_known'])
                        identity = dict(texture_sha256=tex['sha256'], clut_ram_sha256=material_key[1],
                                        format=facts['format_id'], clut_format=facts['clut_format_id'],
                                        clut_shift=facts['clut_shift'], clut_mask=facts['clut_mask'],
                                        clut_start=facts['clut_start'], rgba_sha256=facts['rgba_sha256'],
                                        parameters=stable)
                        decoded_materials[material_key] = sha(json.dumps(identity, sort_keys=True).encode())
                    material_id = decoded_materials[material_key]
                    check(packet['material_ids'] == [material_id], 'Original CLUT/texture/render material changed')
                    target = (draw['register_record'], draw['register_word'])
                    check(target not in targets, 'Duplicate target command')
                    targets[target] = (packet, vertex, dict(regs), material_id)
                    packet_order.append(packet['packet'])
                check(packet_order == list(range(106)), 'Incomplete/reordered/duplicated original Aya PRIMs')
                matrices = {k: [None] * n for k, n in [('world', 12), ('view', 12), ('projection', 16), ('bones', 96)]}
                cursors = {k: 0 for k in matrices}; regs = {}; found = set()
                frame_start = len(draws); vertex_start = first
                for record, (kind, size, ptr) in enumerate(commands):
                    check(ptr + size <= len(push), 'PPDMP push extent invalid')
                    raw = push[ptr:ptr + size]
                    if kind == 0:
                        regs = initial_registers(raw)
                    elif kind == 1:
                        check(size % 4 == 0, 'Truncated GE command')
                        for wi in range(size // 4):
                            word = struct.unpack_from('<I', raw, wi * 4)[0]
                            cmd, value = word >> 24, word & 0xffffff
                            regs[cmd] = value
                            if cmd in (0x3a, 0x3c, 0x3e, 0x2a):
                                k = {0x3a: 'world', 0x3c: 'view', 0x3e: 'projection', 0x2a: 'bones'}[cmd]
                                cursors[k] = value & (127 if k == 'bones' else 15)
                            elif cmd in (0x3b, 0x3d, 0x3f, 0x2b):
                                k = {0x3b: 'world', 0x3d: 'view', 0x3f: 'projection', 0x2b: 'bones'}[cmd]
                                i = cursors[k]
                                if i < len(matrices[k]):
                                    matrices[k][i] = value
                                cursors[k] = (i + 1) & (127 if k == 'bones' else 15)
                            target = (record, wi)
                            if cmd != 4 or target not in targets:
                                continue
                            packet, vertices, expected, material_id = targets[target]
                            check(regs == expected, 'Independent material/matrix replay register states differ')
                            vt = regs[0x12]; slots = ((vt >> 14) & 7) + 1
                            count = value & 0xffff; stride, off = layout(vt)
                            check(not vt & (1 << 23) and ((vt >> 11) & 3) == 0 and ((vt >> 18) & 7) == 0
                                  and ((vt >> 2) & 7) == 0 and ((vt >> 9) & 3) == 2 and ((vt >> 7) & 3) == 2
                                  and ((vt >> 5) & 3) == 1 and (vt & 3) == 2, 'Unsupported original vertex format')
                            check(len(vertices) == count * stride, 'Vertex byte extent invalid')
                            check(all(v is not None for k in ('world', 'view', 'projection') for v in matrices[k])
                                  and all(v is not None for v in matrices['bones'][:slots * 12]), 'Missing uploaded matrices')
                            byte_offset = dest.tell()
                            dest.write(struct.pack('<256I', *[regs.get(i, 0) for i in range(256)]))
                            dest.write(struct.pack('<12f', *map(f24, matrices['world'])))
                            dest.write(struct.pack('<96f', *[f24(v) if v is not None else 0 for v in matrices['bones']]))
                            dest.write(struct.pack('<2I', count, slots))
                            for i in range(count):
                                at = i * stride
                                p = [v / 32768 for v in struct.unpack_from('<3h', vertices, at + off['pos'][0])]
                                n = [v / 128 for v in struct.unpack_from('<3b', vertices, at + off['nrm'][0])]
                                w = [v / 32768 for v in struct.unpack_from('<' + 'H' * slots, vertices, at + off['wt'][0])]
                                uv = [v / 32768 for v in struct.unpack_from('<2H', vertices, at + off['uv'][0])]
                                dest.write(struct.pack('<16f', *(p + n + w + [0] * (8 - slots) + uv)))
                            # Keep every PRIM's light signature; no assumption of per-frame constancy.
                            light_keys = list(range(0x17, 0x1c)) + [0x50, 0x51] + list(range(0x53, 0x59)) + list(range(0x5b, 0x9b))
                            light_payloads = {hex(k): regs[k] for k in light_keys}
                            light_hash = sha(json.dumps(light_payloads, sort_keys=True).encode())
                            states.setdefault(light_hash, light_payloads)
                            draws.append(dict(capture=key, group=group, sample=sample, packet=packet['packet'],
                                              vertex_sha256=packet['vertex_sha256'], material_id=material_id,
                                              register_record=record, register_word=wi, vertex_count=count, vtype=vt,
                                              weight_slots=slots, binary_byte_offset=byte_offset, first_output_vertex=first,
                                              lighting_signature=light_hash, WORLD_payload=matrices['world'][:],
                                              VIEW_payload=matrices['view'][:], PROJECTION_payload=matrices['projection'][:]))
                            first += count; found.add(target)
                check(found == set(targets) and first - vertex_start == 3456, 'Incomplete original Aya series frame')
                frames.append(dict(group=group, sample=sample, capture=key, first_draw=frame_start, draw_count=106,
                                   first_output_vertex=vertex_start, vertices=3456,
                                   preceding_cpu_capture_ticks=frame['ticks'], cpu_to_ge_atomicity_verified=False,
                                   preview_time_seconds=sample / 30, original_time_seconds=None))
                print(json.dumps(dict(group=group, sample=sample, draws=106)), flush=True)
    check(len(draws) == 7632 and first == 248832, 'Incomplete72-sample evidence')
    result = dict(schema='aya-original-ge-lighting-inputs/v2', passed=True, source_material_sha256=MATERIAL_SHA,
                  source_manifests=sources, captures=captures, frames=frames, draws=draws,
                  binary=dict(file=str(binary.resolve()), bytes=binary.stat().st_size, sha256=sha(binary.read_bytes())),
                  draw_count=len(draws), total_vertices=first, lighting_states=states,
                  decoded_original_materials=len(decoded_materials), original_clut_material_bindings_verified=True,
                  preview_fps=30, original_timing_verified=False, existing_source_bone_timeline_replaced=False,
                  recorded_final_lighting_outputs_available=False, colors_are_future_reconstructions=True,
                  limits=['Samples retain GE dump order, not an authored complete original animation.',
                          'CPU-breakpoint ticks precede asynchronous dumps; no precise CPU/GE clock binding claimed.',
                          'Preview uses uniform30fps by choice; existing60-sample source-bone/weapon clips are untouched.',
                          'Software light reconstruction is not original GPU pixels or full PSP rasterization.'])
    (out / 'inputs.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, samples=72, draws=len(draws), vertices=first, light_states=len(states))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    recover(parser.parse_args().out)
