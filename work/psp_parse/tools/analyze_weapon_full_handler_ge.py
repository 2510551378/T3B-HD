"""Independently decode original object records and all inline CPU PRIMs."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from PIL import Image

from analyze_weapon_cpu_ge_correlated import window, high24
from exact_aya_materials import iter_material_draws, decode_texture, material_parameters
from extract_runtime_character import layout, read_ppdmp
from inventory_original_scene import draw_stream


def check(ok, why):
    if not ok:
        raise ValueError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def identity(p):
    return dict(file=str(p.resolve()), sha256=sha(p.read_bytes()))


def checked_file(item):
    p = Path(item['file'])
    check(sha(p.read_bytes()) == item['sha256'], 'Retained evidence changed')
    return p


def object_records(row):
    if row['dispatch']['actualType'] != 155:
        return [], None
    m = row['fullHandler']['metadata']
    segments = [m['object'], m['header'], m['groups']]
    segments += [x['raw'] for x in m['drawHeaders']+m['drawRecords']]
    memory = [(s['address'], window(s, s['address'], s['size'])) for s in segments]
    def load(address, count):
        matches = [b[address-a:address-a+count] for a, b in memory if a <= address and address+count <= a+len(b)]
        check(matches and all(b == matches[0] for b in matches), 'Unretained/contradictory original object memory')
        return matches[0]
    def u32(address):
        return struct.unpack('<I', load(address, 4))[0]
    obj = row['geometrySource']['object']
    header = u32(obj)
    count, groups = u32(header+0x18), u32(header+0x1c)
    check(0 < count <= 16, 'Original group bound')
    minimum = (count-1)*0x44+0x38
    check(m['groups']['address'] == groups and minimum <= m['groups']['size'] <= count*0x44, 'Original group retained span')
    result = []
    for j in range(count):
        group = groups+j*0x44  # Original08b5ee28: addiu s3,s3,0x44.
        headers, address = u32(group+0x1c), u32(group+0x20)
        check(0 < headers <= 64, 'Draw header bound')
        for k in range(headers):
            at = address+k*16
            vt, material, inner, records = struct.unpack('<4I', load(at, 16))
            check(0 < inner <= 64 and len(result)+inner <= 256, 'Inner record bound')
            for q in range(inner):
                p, opaque, n, vertex = struct.unpack('<4I', load(records+q*16, 16))
                result.append(dict(group=j, header=k, record=q, record_address=records+q*16,
                    vtype=vt, primitive=p, count=n, vertex_address=vertex, material_index_raw=material, opaque_word=opaque))
    check(result[0]['record_address'] == row['emit']['entry']['drawRecord']['address'], 'First actual record not original first record')
    return result, dict(group_count=count, original_group_stride=0x44, retained_group_bytes=m['groups']['size'],
                       complete_group_records_retained=m['groups']['size'] == count*0x44)


def decode_commands(row):
    f = row['fullHandler']
    start, end = row['emit']['entry']['dl'], f['end']
    check(start['address'] == end['address'] and 16 <= end['cursor']-start['cursor'] <= 0x20000, 'Noncontiguous DL context/span')
    raw = window(f['commands'], start['cursor'], end['cursor']-start['cursor'])
    first = window(row['emit']['returned']['packet'], start['cursor'], row['emit']['returned']['packet']['size'])
    check(raw.startswith(first), 'Full DL does not start with actually emitted packet')
    words = struct.unpack('<%dI' % (len(raw)//4), raw)
    snapshots = {p['commandWord']:p for p in f['prims']}
    view_packet = window(row['view']['packetAtGeometry'], row['view']['packetAtGeometry']['address'], 52)
    view = [x & 0xffffff for x in struct.unpack('<13I', view_packet)[1:]]
    view_cursor, base, vertex, vt = 12, None, None, None
    previous, fresh, result, changes = None, False, [], {}
    for at, word in enumerate(words):
        cmd, value = word >> 24, word & 0xffffff
        check(cmd not in {2, 8, 9, 10, 11, 12, 14, 15, 0x13, 0x14}, 'Unsupported indexed/control/offset CPU command')
        if cmd == 0x10:
            base = (value & 0xff0000) << 8
        elif cmd == 1:
            check(base is not None, 'VADDR has no observed BASE')
            vertex, fresh = base | value, True
        elif cmd == 0x12:
            vt = value
        elif cmd == 0x3c:
            view_cursor = value & 15
        elif cmd == 0x3d:
            check(view_cursor < 12, 'Out-of-range VIEW write')
            view[view_cursor] = value
            view_cursor = (view_cursor+1) & 15
        elif cmd == 4:
            prim = (value >> 16) & 7
            prim = previous if prim == 7 else prim
            n = value & 65535
            check(fresh and vt in (0x102, 0x11e) and prim == 4 and 3 <= n <= 4096, 'Unsupported actual source strip')
            previous, fresh = prim, False
            check(at in snapshots, 'Actual CPU PRIM lacks callback snapshot')
            snap = snapshots[at]
            stride, _ = layout(vt)
            vertices = window(snap['vertices'], vertex, n*stride)
            check((snap['vtype'], snap['primitive'], snap['count'], snap['vertexAddress']) == (vt, prim, n, vertex), 'Producer fields contradict original command words')
            result.append(dict(command_word=at, vtype=vt, primitive=prim, count=n, vertex_address=vertex,
                vertices=snap['vertices']['raw'], VIEW_payload=list(view), scalar_changes=dict(changes)))
        else:
            changes[cmd] = value
    check(len(result) == len(snapshots) > 0, 'Full CPU PRIM coverage differs')
    expected, metadata = object_records(row)
    if expected:
        check(len(result) == len(expected), 'Actual PRIM count differs from original object')
        for p, e in zip(result, expected):
            check(tuple(p[k] for k in ('vtype','primitive','count','vertex_address')) == tuple(e[k] for k in ('vtype','primitive','count','vertex_address')), 'Actual subdraw differs from original object record')
            p['original_record'] = e
    return result, metadata, dict(byte_count=len(raw), trailing_command_words=words[result[-1]['command_word']+1:])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--correlation', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    check(not args.out.exists(), 'Never replace full-handler evidence')
    args.out.mkdir(parents=True)
    correlation = read(args.correlation)
    check(correlation['passed'] and correlation['matched_observations'] > 0, 'No independently correlated first draw')
    capture = read(checked_file(correlation['capture']))
    check(capture['captureFullHandler'], 'Full handler capture was not enabled')
    module = checked_file(capture['module']).read_bytes()
    facts = {0x08b5ecb4:0x8c9e0000, 0x08b5ed08:0x8fc40018, 0x08b5ed04:0x8fd3001c,
             0x08b5ed2c:0x8e76001c, 0x08b5ed3c:0x8e710020, 0x08b5ee14:0x26310010,
             0x08b5ee28:0x26730044, 0x08b5e370:0x8cb3000c, 0x08b5e378:0x8cb20008,
             0x08b5e394:0x8cb10000, 0x08b5e398:0x8e640000, 0x08b5e39c:0x8e660008, 0x08b5e3a0:0x8e68000c}
    for address, word in facts.items():
        check(struct.unpack_from('<I', module, address-0x08804000)[0] == word, 'Original structure instruction differs')
    gpu = {}
    for frame in correlation['GE_captures']:
        if not any(m['GE_sample'] == frame['sample'] for r in correlation['rows'] for m in r['matching_GE_observations']):
            continue
        commands, push = read_ppdmp(str(checked_file(frame['capture'])))
        states = {(x['register_record'],x['register_word']):x for x in iter_material_draws(commands,push)}
        gpu[frame['sample']] = (list(draw_stream(commands,push)), states, push)
    rows, matches, textures = [], [], {}
    raster = {0x17,0x1c,0x1d,0x1e,0x1f,0x20,0x21,0x22,0x23,0x24,0x25,0x28,0x48,0x49,0x4a,0x4b,0x50,0x55,0x58,0xde,0xdf,0xe7,0xe8,0xe9}
    for row, first in zip(capture['rows'], correlation['rows']):
        prims, metadata, commands = decode_commands(row)
        info = dict(CPU_sample=row['sample'], actual_type=row['dispatch']['actualType'], runtime_geometry_id=row['geometrySource']['runtimeId'],
            original_descriptor_relative_offset=row['descriptorPath']['offset'], definition_index=row['dispatch']['definitionIndex'],
            primitive_count=len(prims), prims=prims, original_metadata=metadata, command_span=commands, GE_matches=[])
        rows.append(info)
        if not first['matching_GE_observations']:
            continue
        anchor = first['matching_GE_observations'][0]
        ds, states, push = gpu[anchor['GE_sample']]
        offset = next(i for i,d in enumerate(ds) if (d['register_record'],d['register_word']) == (anchor['record'],anchor['word']))
        for n, p in enumerate(prims):
            d = ds[offset+n]
            vertices = push[d['vertex']['pointer']:d['vertex']['pointer']+d['vertex']['bytes']]
            check((d['vtype'],d['primitive'],d['count'],d['view']) == (p['vtype'],p['primitive'],p['count'],p['VIEW_payload']), 'Consecutive actual GE PRIM differs from CPU window')
            check(vertices == checked_file(p['vertices']).read_bytes(), 'Actual subdraw vertices differ from GE bytes')
            st = states[(d['register_record'],d['register_word'])]
            regs = st['registers']
            for cmd, value in p['scalar_changes'].items():
                if cmd in raster:
                    check(regs[cmd] == value, 'CPU raster-state change differs from GE')
            tex = st['texture0']
            check(tex is not None and not tex['framebuffer'], 'Unresolved matched framebuffer material')
            rgba, facts = decode_texture(tex['raw'],regs,st['clut'],st['clut_known'])
            digest = facts['rgba_sha256']
            if digest not in textures:
                png = args.out/('original_'+digest[:16]+'.png')
                Image.frombytes('RGBA',(facts['width'],facts['height']),rgba).save(png)
                textures[digest] = dict(facts=facts,png=identity(png))
            clut = args.out/f'CLUT_CPU{row["sample"]:04d}_PRIM{n:02d}.bin'
            clut.write_bytes(st['clut'])
            m = dict(CPU_sample=row['sample'], subdraw=n, runtime_geometry_id=info['runtime_geometry_id'], source_primitive=p,
                GE_sample=anchor['GE_sample'], record=d['register_record'], word=d['register_word'],
                actual_consecutive_GE_PRIM=True, registers={hex(k):v for k,v in regs.items()},
                WORLD_payload=d['world'], VIEW_payload=d['view'], PROJECTION_payload=d['proj'],
                CLUT=identity(clut), texture_RGBA_sha256=digest, material_parameters=material_parameters(regs))
            info['GE_matches'].append(m)
            matches.append(m)
    result = dict(schema='original-full-handler-CPU-object-GE-proof/v1', passed=True,
        first_draw_correlation=identity(args.correlation), capture=identity(checked_file(correlation['capture'])),
        source_structure_words=[dict(address=a,word=w)for a,w in facts.items()], rows=rows, matched_primitives=matches, textures=textures,
        handler_count=len(rows), actual_CPU_primitive_count=sum(x['primitive_count']for x in rows), matched_GE_primitive_count=len(matches),
        production_decoder_inputs_ready=True, default_M1_binding_replaced=False, gameplay_bullet_origin_verified=False, producer=identity(Path(__file__)),
        limits=['Coverage is every inline PRIM from first emitter to callback return; it does not include earlier material setup or arbitrary control-flow/sublist calls.',
                'Initial0x38 group snapshots retain only the used prefix of one0x44 group. Their span is reported, never called a complete group record.',
                'Original per-draw VIEW/PROJECTION/material data are observed. Time evolution and bullet/hit/AI behavior are not reconstructed.',
                'Actual GE command recording and decoded source textures are not final PSP hardware pixel or formal M1 play acceptance.'])
    (args.out/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,handlers=len(rows),CPU_primitives=result['actual_CPU_primitive_count'],GE_matched=len(matches),textures=len(textures))))


if __name__ == '__main__':
    main()
