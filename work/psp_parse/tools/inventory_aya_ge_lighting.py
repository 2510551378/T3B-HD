"""Recover bounded original Aya lighting states from retained PRIM-time records.

Replays recorded GE words and verifies snapshot/geometry identities. Does not
compute final lit vertices or change any runtime material.
"""
import collections
import hashlib
import json
import math
from pathlib import Path
import struct

from exact_aya_materials import CONTEXT_RANGES
from extract_runtime_character import read_ppdmp

ROOT = Path(__file__).resolve().parents[1]
LIGHT_KEYS = sorted(set(range(0x17,0x1C)) | {0x50,0x51} | set(range(0x53,0x59)) | set(range(0x5B,0x9B)))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(value, message):
    if not value:
        raise ValueError(message)


def f24(value):
    result = struct.unpack('<f',struct.pack('<I',value << 8))[0]
    check(math.isfinite(result),'Nonfinite lighting field')
    return result


def rgb(value):
    return [(value >> (8*i)) & 255 for i in range(3)]


def describe(registers, has_color):
    r = registers
    lights = []
    for index in range(4):
        kind = (r[0x5F+index] >> 8) & 3
        computation = r[0x5F+index] & 3
        lights.append({'index':index,'enabled':bool(r[0x18+index]&1),
                       'type':kind,'type_name':{0:'directional',1:'point',2:'spot',3:'unknown'}[kind],
                       'computation':computation,'computation_name':{0:'diffuse',1:'diffuse_and_specular',2:'powered_diffuse'}.get(computation,'unknown'),
                       'position_or_direction':[f24(r[0x63+3*index+j]) for j in range(3)],
                       'spot_direction':[f24(r[0x6F+3*index+j]) for j in range(3)],
                       'attenuation_constant_linear_quadratic':[f24(r[0x7B+3*index+j]) for j in range(3)],
                       'spot_exponent':f24(r[0x87+index]),'spot_cutoff':f24(r[0x8B+index]),
                       'ambient_rgb8':rgb(r[0x8F+3*index]),'diffuse_rgb8':rgb(r[0x90+3*index]),
                       'specular_rgb8':rgb(r[0x91+3*index])})
    return {'lighting_enabled':bool(r[0x17]&1),'shade_mode_raw':r[0x50]&1,
            'reverse_normals':bool(r[0x51]&1),'secondary_specular_color':bool(r[0x5E]&1),
            'vertex_color_present':has_color,'material_update_raw':r[0x53]&7,
            'effective_material_update_with_vertex_color':(r[0x53]&7) if has_color else 0,
            'material_emissive_rgb8':rgb(r[0x54]),'material_ambient_rgb8':rgb(r[0x55]),
            'material_diffuse_rgb8':rgb(r[0x56]),'material_specular_rgb8':rgb(r[0x57]),
            'material_alpha8':r[0x58]&255,'material_specular_exponent':f24(r[0x5B]),
            'global_ambient_rgb8':rgb(r[0x5C]),'global_ambient_alpha8':r[0x5D]&255,'lights':lights}


def main():
    source = ROOT/'out/AYA_NATIVE_GLTF_20261020/raw/input_materials.json'
    provenance = json.loads((ROOT/'out/AYA_NATIVE_GLTF_20261020/provenance.json').read_text(encoding='utf-8'))
    check(sha(source.read_bytes()) == provenance['inputs']['materials']['sha256'],'Frozen material source differs')
    materials = json.loads(source.read_text(encoding='utf-8'))
    variants = {}
    observations = []
    for capture in materials['captures']:
        file = Path(capture['path'])
        check(sha(file.read_bytes()) == capture['sha256'],'Recorded GE capture differs')
        expected = {(row['register_record'],row['register_word']):row for row in materials['observations']
                    if row['capture'] == capture['key']}
        check(len(expected) == 106,'Expected complete unique106 Aya packet observations')
        commands,push = read_ppdmp(str(file))
        registers = {}
        vertex = None
        matched = set()
        for record,(kind,size,pointer) in enumerate(commands):
            check(pointer+size <= len(push),'Recorded region exceeds push buffer')
            data = push[pointer:pointer+size]
            if kind == 0:
                cursor = 17*4
                for lo,hi in CONTEXT_RANGES:
                    for cmd in range(lo,hi+1):
                        word = struct.unpack_from('<I',data,cursor)[0]
                        check(word >> 24 == cmd or (cmd <= 2 and word == 0),'Saved context opcode differs')
                        registers[cmd] = word & 0xFFFFFF
                        cursor += 4
            elif kind == 2:
                vertex = data
            elif kind == 1:
                check(len(data)%4 == 0,'Recorded command words truncated')
                for offset in range(0,len(data),4):
                    word = struct.unpack_from('<I',data,offset)[0]
                    cmd,value = word >> 24,word & 0xFFFFFF
                    registers[cmd] = value
                    key = (record,offset//4)
                    if cmd != 4 or key not in expected:
                        continue
                    row = expected[key]
                    check(vertex is not None and sha(struct.pack('<I',registers[0x12])+vertex) == row['vertex_sha256'],
                          'PRIM geometry identity differs from verified Aya packet')
                    check(((value >> 16)&7,value&65535) == (3,row['vertex_count']),'Aya PRIM topology differs')
                    current = {cmd:registers[cmd] for cmd in LIGHT_KEYS}
                    check(all(current[k] == row['register_payloads'][hex(k)] for k in LIGHT_KEYS),
                          'Lighting replay differs from retained material snapshot')
                    color_type = (registers[0x12] >> 2)&7
                    signature = sha(json.dumps(current,sort_keys=True).encode('utf-8'))
                    if signature not in variants:
                        variants[signature] = {'signature':signature,'raw_payloads':{hex(k):v for k,v in current.items()},
                                               'decoded':describe(current,color_type != 0),'observations':0}
                    variants[signature]['observations'] += 1
                    observations.append({'capture':capture['key'],'packet':row['packet'],'register_record':record,
                                         'register_word':offset//4,'vertex_sha256':row['vertex_sha256'],
                                         'vtype':registers[0x12],'color_type_raw':color_type,'lighting_signature':signature})
                    matched.add(key)
        check(matched == set(expected),'Not all original Aya lighting observations replayed')
    out = ROOT/'out/AYA_GE_LIGHTING_20261020'
    out.mkdir(exist_ok=True)
    report = {'schema':'aya-prim-lighting-inventory/v1','passed':True,'material_source':str(source),
              'material_source_sha256':sha(source.read_bytes()),'observations_checked':len(observations),
              'captures':materials['captures'],'lighting_state_count':len(variants),'states':list(variants.values()),
              'observations':observations,'source_references':[
                  'https://github.com/hrydgard/ppsspp/blob/v1.20.4/GPU/ge_constants.h#L367-L387',
                  'https://github.com/hrydgard/ppsspp/blob/v1.20.4/GPU/Software/Lighting.cpp#L80-L175'],
              'parser_boundary':'Uses established PPDMP record reader and context range table; independently replays GE words and checks every target PRIM against frozen material snapshots.',
              'ue_original_lighting_implemented':False,'final_lit_vertices_verified':False,
              'limits':['Only the recorded106-packet Aya in three retained captures, not the complete game or all60 fire frames.',
                        'Light register state is not proof of final vertex lighting, raster pixels or a faithful UE shader.',
                        'Coordinate transforms, weighted normals, precision, specular computation and blend/depth/culling still require verification.',
                        'Native glTF has no COLOR_0; the existing unlit/white-vertex baseline does not reproduce original GE lighting.']}
    target = out/'lighting_states.json'
    check(not target.exists(),'Refuse to overwrite prior lighting evidence')
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'observations_checked':len(observations),'lighting_state_count':len(variants),
                      'lights_enabled':[[x['enabled'] for x in v['decoded']['lights']] for v in variants.values()]}))


if __name__ == '__main__':
    main()
