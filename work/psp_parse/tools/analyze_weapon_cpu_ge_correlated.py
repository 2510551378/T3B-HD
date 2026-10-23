"""Audit full CPU source1 -> effect VIEW -> retained GE draw/material evidence."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image

from analyze_weapon_ge_emit import audit as audit_emit
from analyze_weapon_marker_output import sidecar
from exact_aya_materials import iter_material_draws, decode_texture, material_parameters
from extract_runtime_character import read_ppdmp
from inventory_original_scene import draw_stream

GUN_SHA = '168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a'


def check(value, why):
    if not value:
        raise ValueError(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def identity(path):
    return dict(file=str(path.resolve()), sha256=sha(path.read_bytes()))


def window(item, address, size):
    check(item['address'] == address and item['size'] == size, 'Snapshot address/extent differs')
    raw = sidecar(item['raw'])
    check(len(raw) == size, 'Snapshot bytes differ')
    return raw


def full(raw):
    check(len(raw) == 64, 'Not a full original F32 matrix')
    m = np.frombuffer(raw, dtype='<f4').reshape(4, 4)
    check(np.isfinite(m).all() and np.array_equal(m[:, 3], [0, 0, 0, 1]), 'Nonfinite/nonaffine original matrix')
    return m


def high24(raw):
    return (np.frombuffer(raw, dtype='<u4').reshape(4, 4)[:, :3].reshape(-1) >> 8).tolist()


def original_f32_product(a, b):
    out = np.zeros((4, 4), dtype='<f4')
    for k in range(4):
        out = (out + (a[:, k:k+1]*b[k:k+1, :]).astype('<f4')).astype('<f4')
    return out.tobytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--expect-matches', type=int, default=4)
    args = parser.parse_args()
    check(not args.out.exists(), 'Never replace independent correlation evidence')
    args.out.mkdir(parents=True)
    capture = read(args.capture)
    producer = args.capture.parent/'executed_trace_weapon_marker_ge_emit.js'
    checked = audit_emit(args.capture, Path(capture['originalFep']['file']), producer)
    (args.out/'CPU_emission_reaudit.json').write_text(json.dumps(checked, indent=2), encoding='utf-8')
    check(capture['capturePose'] and not capture['geFailure'], 'No complete source/GE capture')
    lifecycle = read(args.capture.parent/'process_completed.json')
    check(lifecycle['node_exit_code'] == 0 and lifecycle['owned_emulator_stopped'] and lifecycle['protection_passed'], 'Runner lifecycle/protection failed')
    check(any(c['address'] == 0x08b657f8 and c['size'] == 0xa4 and c['verified'] for c in capture['codeIdentity']['checks']), 'Full live mode0 identity not captured')
    catalog_path = Path(__file__).resolve().parents[1]/'out/WEAPON_SOURCE_FX_LINKS_20261021/recovery_v1/source_markers.bin'
    catalog = catalog_path.read_bytes()
    check(len(catalog) == 208, 'Wrong original marker catalog')
    bank, summaries = {}, []
    for c in capture['geCaptures']:
        path = Path(c['raw']['file'])
        check(sha(path.read_bytes()) == c['raw']['sha256'], 'GE bytes changed')
        commands, push = read_ppdmp(str(path))
        draws = list(draw_stream(commands, push))
        states = {(s['register_record'], s['register_word']): s for s in iter_material_draws(commands, push)}
        guns = []
        for ordinal, d in enumerate(draws):
            v = d['vertex']
            vertices = push[v['pointer']:v['pointer']+v['bytes']]
            if sha(struct.pack('<I', d['vtype'])+vertices) == GUN_SHA:
                guns.append((ordinal, d))
        summaries.append(dict(sample=c['sample'], capture=identity(path), all_draws=len(draws), rifle_draws=len(guns)))
        for ordinal, d in enumerate(draws):
            v = d['vertex']
            vertices = push[v['pointer']:v['pointer']+v['bytes']]
            key = d['vtype'], d['primitive'], d['count'], sha(vertices), tuple(d['view'])
            preceding = [(o, gun) for o, gun in guns if o < ordinal]
            gun = preceding[-1][1] if preceding else None
            state = states[(d['register_record'], d['register_word'])]
            bank.setdefault(key, []).append((c, d, gun, state, vertices))
    rows, matched, textures = [], [], {}
    for row in capture['rows']:
        at_matrix, at_emit = row['matrix']['entry']['weaponPose'], row['emit']['entry']['weaponPose']
        source = window(at_matrix['sources'], row['weapon']['sourceBase'], 3*0x130)
        world = window(at_matrix['world'], row['weapon']['actor']+0x220, 64)
        check(source == window(at_emit['sources'], row['weapon']['sourceBase'], 3*0x130), 'Source records changed between CPU stages')
        check(world == window(at_emit['world'], row['weapon']['actor']+0x220, 64), 'WORLD changed between CPU stages')
        parents = [struct.unpack_from('<I', source, n*0x130+0x124)[0] for n in range(3)]
        check(parents == [0, row['weapon']['sourceBase'], row['weapon']['sourceBase']], 'Source parents differ')
        check(catalog[16:] == source[0x80:0xc0]+source[0x170:0x1b0]+source[0x2a0:0x2e0], 'Captured original definitions differ from recovered catalog')
        p60_raw = window(row['matrix']['entry']['p60'], row['P']+0x60, 64)
        prediction = original_f32_product(full(source[0x170:0x1b0]), full(world))
        check(prediction == p60_raw, 'Original source1 WORLD composition does not reproduce actual state+60 bits')
        view_raw = window(row['view']['packetAtGeometry'], row['view']['packetAtGeometry']['address'], 52)
        words = struct.unpack('<13I', view_raw)
        check(words[0] == 0x3c000000 and all(w >> 24 == 0x3d for w in words[1:]), 'Unexpected CPU VIEW command packet')
        emitted = row['emit']['entry']
        g = emitted['gpr']
        vertices = sidecar(emitted['vertices']['raw'])
        key = g[5], g[4], g[6], sha(vertices), tuple(w & 0xffffff for w in words[1:])
        candidates = bank.get(key, [])
        global_view = window(row['view']['entry']['globalMatrix'], row['view']['entry']['globalMatrix']['address'], 64)
        exact = []
        for c, fx, gun, st, gpu_vertices in candidates:
            if gun is None or gun['world'] != high24(world) or gun['view'] != high24(global_view):
                continue
            check(gpu_vertices == vertices, 'Digest-matched vertices differ')
            # Retain exact CLUT/material binding of this actual GE observation.
            tex, regs = st['texture0'], st['registers']
            check(tex is not None and not tex['framebuffer'], 'Matched FX needs unresolved framebuffer texture')
            rgba, facts = decode_texture(tex['raw'], regs, st['clut'], st['clut_known'])
            digest = facts['rgba_sha256']
            if digest not in textures:
                png = args.out/('original_'+digest[:16]+'.png')
                Image.frombytes('RGBA', (facts['width'], facts['height']), rgba).save(png)
                textures[digest] = dict(facts=facts, png=identity(png))
            prefix = args.out/f'CPU{row["sample"]:04d}_GE{c["sample"]:04d}_{fx["register_record"]}'
            vertex_file, clut_file = Path(str(prefix)+'_vertices.bin'), Path(str(prefix)+'_CLUT.bin')
            vertex_file.write_bytes(gpu_vertices)
            clut_file.write_bytes(st['clut'])
            exact.append(dict(GE_sample=c['sample'], GE_capture=c['raw'], record=fx['register_record'], word=fx['register_word'],
                rifle_record=gun['register_record'], rifle_word=gun['register_word'],
                vertices=identity(vertex_file), CLUT=identity(clut_file), CLUT_known_sha256=sha(st['clut_known']),
                texture_RGBA_sha256=digest, texture_facts=facts, material_parameters=material_parameters(regs),
                registers={hex(k):v for k,v in regs.items()}, WORLD_payload=fx['world'], VIEW_payload=fx['view'], PROJECTION_payload=fx['proj'],
                exact_vertex_bytes=True, exact_full_VIEW_packet_payload=True, exact_rifle_WORLD_high24=True, exact_main_VIEW_high24=True))
        check(len(exact) <= 1, 'Ambiguous content join; cannot identify one observation')
        info = dict(CPU_sample=row['sample'], source1_state60_reconstruction_bit_exact=True,
            actual_type=row['dispatch']['actualType'], runtime_geometry_id=row['geometrySource']['runtimeId'],
            original_FEP_record_offset=checked['rows'][row['sample']]['source_record_offset'],
            definition_index=row['dispatch']['definitionIndex'], CPU_entry_ticks=row['entryTicks'], CPU_emit_ticks=emitted['ticks'],
            matching_GE_observations=exact, semanticName=None)
        rows.append(info)
        if exact:
            matched.append(row['sample'])
    check(len(matched) == args.expect_matches, 'Unexpected correlation coverage')
    result = dict(schema='weapon-CPU-GE-exact-content-correlation/v1', passed=True,
        capture=identity(args.capture), executed_producer=identity(producer), original_marker_catalog=identity(catalog_path),
        CPU_rows=len(rows), GE_captures=summaries, unique_matched_CPU_rows=matched, matched_observations=len(matched), rows=rows,
        textures=textures, original_source1_to_visual_effect_GE_observed=bool(matched), gameplay_bullet_origin_verified=False,
        named_muzzle_verified=False, default_M1_binding_replaced=False, producer=identity(Path(__file__)),
        limits=['Exact-content join within one bounded run: raw vertices, full VIEW payload, rifle WORLD and main VIEW all match. Recorder does not retain CPU command PC, so this is not a universal invocation identifier.',
                'Matched rows may share one GE frame/pose; count does not imply distinct poses or shots.',
                'The source1->state60 multiply agrees with actual retained CPU bits for these inputs; no universal VFPU prefix/JIT equivalence is claimed.',
                'Source1 drives the observed visual effects; original bullet/raycast/collision/damage consumer and authored effect clock remain unknown.',
                'Decoded materials belong to the specific matched draw/definition. Geometry ID alone is not a globally unique material binding.'])
    (args.out/'verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(passed=True, CPU_rows=len(rows), GE_captures=len(summaries), matched_CPU_rows=matched,
                         distinct_matched_GE_frames=len({m['GE_sample']for r in rows for m in r['matching_GE_observations']}), textures=len(textures))))


if __name__ == '__main__':
    main()
