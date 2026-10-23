"""Recover original marker definitions and measure retained GE FX/line evidence.

CPU and GE captures are independent observations. Byte-identical geometry does
not assert a same-invocation join; view mismatches are retained explicitly.
"""
import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

import numpy as np

from analyze_ge_fx_weapon_anchors import affine, f24
from analyze_weapon_marker_output import audit as audit_marker, sidecar, matrix
from analyze_weapon_ge_emit import audit as audit_emission
from exact_aya_materials import iter_material_draws
from extract_runtime_character import layout, read_ppdmp
from inventory_original_scene import draw_stream


def check(value, reason):
    if not value:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def identity(path):
    return dict(file=str(path.resolve()), sha256=sha(path.read_bytes()))


def stored_matrix(raw, offset=0):
    return np.frombuffer(raw, dtype='<f4', count=16, offset=offset).reshape(4, 4).astype(float)


def recover_markers(path, weight, out):
    checked = audit_marker(path)
    capture = read(path)
    definitions = []
    relations = []
    rows = []
    for row in capture['rows']:
        raw = sidecar(row['postSourcesAll'])
        check(len(raw) == 3 * 0x130, 'Wrong original three-source extent')
        check(raw[0x130:2*0x130] == sidecar(row['postSource']), 'Dense source1 slice differs')
        parents = struct.unpack_from('<I', raw, 0x124)[0], struct.unpack_from('<I', raw, 0x254)[0], struct.unpack_from('<I', raw, 0x384)[0]
        check(parents == (0, row['postSourceBase'], row['postSourceBase']), 'Original source parent pointers differ')
        check(np.array_equal(stored_matrix(raw, 0x40), np.eye(4)), 'Source0 local matrix is not identity')
        # Keep full F32 root skin and source1/source2 matrices. +C0 is GE commands.
        definition = raw[0x80:0xc0] + raw[0x170:0x1b0] + raw[0x2a0:0x2e0]
        definitions.append(definition)
        root = stored_matrix(raw, 0x80)
        weighted = root.copy()
        weighted[:, :3] *= weight
        relation = stored_matrix(raw, 0x170) @ np.linalg.inv(weighted)
        relations.append(relation)
        world = np.array(matrix(row['postWorld'])).reshape(4, 4)
        actual = np.array(matrix(row['actualOutput'])).reshape(4, 4)
        reconstructed = relation @ weighted @ world
        rows.append(dict(sample=row['sample'], source_definition_sha256=sha(definition),
                         helper_reconstruction_max_abs_PSP_units=float(np.max(np.abs(actual-reconstructed)))))
    check(len(rows) == 24 and len(set(definitions)) == 1, 'Observed marker definitions are not constant in all24 snapshots')
    # This is an original F32 source definition, not a fitted socket constant.
    binary = out / 'source_markers.bin'
    binary.write_bytes(b'T3BWMK1\0' + struct.pack('<If', 2, weight) + definitions[0])
    return dict(capture=identity(path), rows=rows, audit_rows=checked['rows_checked'],
                all_24_definition_bytes_equal=True, original_definition_sha256=sha(definitions[0]),
                weighted_raw_mesh_from_marker_row_vector=relations[0].tolist(),
                binary=identity(binary), semanticName=None), relations[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    check(not args.out.exists(), 'Never replace evidence')
    args.out.mkdir(parents=True)
    root = Path(__file__).resolve().parents[1]
    scene_path = root / 'out/GE_STRIP_FX_20261021/inputs_v4/inputs.json'
    weapon_path = root / 'out/WEAPON_GE_PAIRED_20261020/inputs_v1/inputs.json'
    fx_path = root / 'out/GE_STRIP_FX_20261021/weapon_anchor_candidates_v1/candidates.json'
    marker_path = root / 'out/AYA_BONE_GE_ACTIONS/slot0_weapon_marker_output_strafefire_dense24/marker_output.json'
    emission_path = root / 'out/AYA_BONE_GE_ACTIONS/slot0_weapon_ge_emit_fire6_command_alias_v3/marker_ge_emit.json'
    emission_producer = root / 'out/WEAPON_GE_EMIT_STATIC_20261020/trace_weapon_marker_ge_emit_command_alias_v3_offline_validated.js'
    scene, weapon, fx, emission = map(read, (scene_path, weapon_path, fx_path, emission_path))
    raw_file = Path(weapon['binary']['file'])
    raw = raw_file.read_bytes()
    check(sha(raw) == weapon['binary']['sha256'], 'Weapon input bytes changed')
    ep = Path(emission['originalFep']['file'])
    emit_audit = audit_emission(emission_path, ep, emission_producer)
    check(emit_audit['passed'] and emit_audit['rows_checked'] == 6, 'Original emission evidence did not revalidate')
    (args.out / 'emission_reaudit.json').write_text(json.dumps(emit_audit, indent=2), encoding='utf-8')
    first = weapon['draws'][0]['binary_byte_offset']
    weight = float(np.frombuffer(raw, dtype='<f4', count=1, offset=first+1464+6*4)[0])
    check(weight == 32767/32768, 'Original gun weight differs')
    marker, relation = recover_markers(marker_path, weight, args.out)
    line_rows, geometry, frame_markers = [], {}, []
    line_counts = []
    for i, (frame, wf) in enumerate(zip(scene['frames'], weapon['frames'])):
        capture = Path(frame['capture']['path'])
        check(sha(capture.read_bytes()) == frame['capture']['sha256'] == weapon['captures'][i]['sha256'], 'CPU/gun/scene capture identity differs')
        draw = weapon['draws'][wf['first_draw']]
        at = draw['binary_byte_offset']
        vertices = np.frombuffer(raw, dtype='<f4', count=243*16, offset=at+1464).reshape(243, 16)
        check(draw['vtype'] == 0x522 and draw['weight_slots'] == 1 and np.all(vertices[:, 6] == weight), 'Different original gun draw')
        gun = affine(np.frombuffer(raw, dtype='<f4', count=12, offset=at+1072).astype(float)*weight) @ affine(np.frombuffer(raw, dtype='<f4', count=12, offset=at+1024))
        inverse_gun = np.linalg.inv(gun)
        main = next(d for d in frame['draws'] if d['category'] == 'body')
        main_view = affine(f24(main['VIEW_payload']))
        main_fb = main['registers']['0x9c']
        commands, push = read_ppdmp(str(capture))
        states = {(s['register_record'], s['register_word']): s for s in iter_material_draws(commands, push)}
        old = {(s['register_record'], s['register_word']): s for s in frame['draws']}
        count = 0
        marker_world = relation @ gun
        direction = marker_world[2, :3] / np.linalg.norm(marker_world[2, :3])
        frame_markers.append(dict(sample=i, source1_GE_reconstructed_world=marker_world.tolist(),
                                  source1_plusZ_unit_PSP_world=direction.tolist(),
                                  emitter_offset5_PSP_world=(np.array([0, 0, 5, 1.]) @ marker_world)[:3].tolist(),
                                  emitter_offset7_PSP_world=(np.array([0, 0, 7, 1.]) @ marker_world)[:3].tolist()))
        for d in draw_stream(commands, push):
            key = d['register_record'], d['register_word']
            payload = push[d['vertex']['pointer']:d['vertex']['pointer']+d['vertex']['bytes']]
            gkey = d['vtype'], d['primitive'], d['count'], sha(payload)
            geometry.setdefault(gkey, []).append(dict(sample=i, record=key[0], word=key[1],
                VIEW_payload=d['view'], included_in_accepted_FX=key in old and old[key]['category'] == 'unweighted_strip_fx'))
            if d['primitive'] != 2:
                continue
            count += 1
            check(d['vtype'] == 0x19c and d['count'] == 2, 'New unsupported original line format')
            stride, fields = layout(d['vtype'])
            check(stride == 16 and len(payload) == 32, 'Unexpected line payload')
            positions = np.array([struct.unpack_from('<3f', payload, j*stride+fields['pos'][0]) for j in range(2)])
            rgba = [list(struct.unpack_from('<4B', payload, j*stride+fields['col'][0])) for j in range(2)]
            world = np.column_stack([positions, np.ones(2)]) @ affine(f24(d['world'])) @ affine(f24(d['view'])) @ np.linalg.inv(main_view)
            local = world @ inverse_gun
            a, b = local[:, :3]
            anchor = np.array(fx['candidate_raw_weapon_local_mean'])
            vector = b-a
            length = float(np.linalg.norm(vector))
            check(length > 0, 'Degenerate original line')
            t = float(np.clip(np.dot(anchor-a, vector)/np.dot(vector, vector), 0, 1))
            regs = states[key]['registers']
            line_rows.append(dict(sample=i, record=key[0], word=key[1], vtype=d['vtype'],
                source_vertex_sha256=sha(payload), source_vertex_bytes=payload.hex(), source_positions=positions.tolist(),
                source_RGBA=rgba, WORLD_payload=d['world'], VIEW_payload=d['view'], PROJECTION_payload=d['proj'],
                same_main_VIEW=d['view'] == main['VIEW_payload'], same_main_PROJECTION=d['proj'] == main['PROJECTION_payload'],
                same_main_framebuffer=regs[0x9c] == main_fb, registers={hex(k):v for k,v in regs.items()},
                raw_weapon_local_endpoints=local[:, :3].tolist(), raw_weapon_local_unit_direction=(vector/length).tolist(),
                raw_weapon_local_length=length, distance_endpoints_to_FX_candidate=np.linalg.norm(local[:, :3]-anchor, axis=1).tolist(),
                distance_finite_segment_to_FX_candidate=float(np.linalg.norm(a+t*vector-anchor)), semanticName=None))
        line_counts.append(count)
    links = []
    for row, checked in zip(emission['rows'], emit_audit['rows']):
        original = sidecar(row['emit']['entry']['vertices']['raw'])
        key = int(checked['vtype'], 16), checked['primitive'], checked['vertex_count'], sha(original)
        matches = geometry.get(key, [])
        packet = sidecar(row['view']['packetAtGeometry']['raw'])
        words = struct.unpack('<13I', packet)
        check(words[0] == 0x3c000000 and all(w >> 24 == 0x3d for w in words[1:]), 'Original VIEW packet encoding differs')
        view = [w & 0xffffff for w in words[1:]]
        inp = stored_matrix(sidecar(row['matrix']['entry']['input']['raw']))
        local_offset = inp[3, :3]
        links.append(dict(cpu_sample=row['sample'], actual_type=checked['actual_type'], runtime_geometry_id=checked['runtime_geometry_id'],
            FEP_source_record_offset=checked['source_record_offset'], vtype=key[0], vertex_count=key[2], vertex_sha256=key[3],
            original_input_translation=local_offset.tolist(), predicted_offset_raw_weapon_local=(np.r_[local_offset, 1.] @ relation)[:3].tolist(),
            geometry_byte_matches=[dict(**m, same_VIEW_packet=m['VIEW_payload'] == view) for m in matches],
            same_invocation_confirmed=False, semanticName=None))
    prediction = (np.array([0, 0, 5, 1.]) @ relation)[:3]
    errors = np.linalg.norm(np.array(fx['independent_sample_origins'])-prediction, axis=1)
    check(line_counts == [0, 0, 0, 21, 17, 0, 0, 0, 0, 0, 0, 0], 'Retained line inventory changed')
    result = dict(schema='weapon-source-marker-FX-line-evidence/v1', passed=True,
        scene=identity(scene_path), weapon=identity(weapon_path), original_marker=marker, original_emission=identity(emission_path), FX_candidate=identity(fx_path),
        lines=line_rows, line_counts_by_sample=line_counts,
        nearest_line_endpoint_distance_raw_local=min(min(r['distance_endpoints_to_FX_candidate']) for r in line_rows),
        nearest_line_segment_distance_raw_local=min(r['distance_finite_segment_to_FX_candidate'] for r in line_rows),
        CPU_GE_geometry_links=links, reconstructed_marker_frames=frame_markers,
        source_offset5_prediction_raw_weapon_local=prediction.tolist(), FX_prediction_distances_raw_local=errors.tolist(),
        CPU_GE_same_invocation_verified=False, source_marker_semanticName=None, M1_production_binding_replaced=False,
        producer=identity(Path(__file__)),
        limits=['Only this observed rifle and its24 source snapshots establish these static definitions; other weapons/animations are not covered.',
                'Original +5/+7 are PSP marker-local offsets, not centimetres and not gun-normalized coordinates.',
                'GE frame marker poses reconstruct from quantized source0; their actual CPU source1 at the same frame was not captured.',
                'Byte-identical geometry can be reused: type152 four-vertex quad matches many draws. It does not identify a source resource or invocation.',
                'CPU/GE VIEW packets are retained separately; no same-invocation identity is asserted across independent captures.',
                'Line endpoints do not coincide with the FX candidate; this does not rule out older particles emitted there.',
                'No named muzzle, hit/bullet origin, original effect clock or formal UE/M1 binding is confirmed.'])
    (args.out/'verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(passed=True, original_marker_rows=len(marker['rows']), line_draws=len(line_rows),
        CPU_geometry_match_counts=[len(x['geometry_byte_matches']) for x in links],
        offset5_prediction_raw_local=prediction.tolist(), FX_prediction_errors_raw_local=errors.tolist(),
        nearest_line_endpoint=result['nearest_line_endpoint_distance_raw_local'])))


if __name__ == '__main__':
    main()
