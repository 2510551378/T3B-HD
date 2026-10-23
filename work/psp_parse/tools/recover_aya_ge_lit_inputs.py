"""Retain exact recorded Aya PRIM inputs for world/normal/lighting replay.

Does not guess a light for another action/time or claim recorded lit outputs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from exact_aya_materials import CONTEXT_RANGES
from extract_runtime_character import read_ppdmp,layout

ROOT=Path(__file__).resolve().parents[1]
SOURCE_SHA='ab1084ee816fce3a146b25be36f80cab8960089466c6725e2f3680b114d5ed93'


def check(ok,message):
    if not ok:raise ValueError(message)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def float24(word):return struct.unpack('<f',struct.pack('<I',word<<8))[0]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    check(not a.out.exists(),'Never replace retained lighting input evidence');a.out.mkdir(parents=True)
    source=ROOT/'out/AYA_NATIVE_GLTF_20261020/raw/input_materials.json'
    check(sha(source.read_bytes())==SOURCE_SHA,'Frozen original material observations changed')
    materials=json.loads(source.read_text(encoding='utf-8'));payload=bytearray(b'T3BLIT1\0'+struct.pack('<I',318));draws=[]
    first=0
    for capture in materials['captures']:
        path=Path(capture['path']);check(sha(path.read_bytes())==capture['sha256'],'PPDMP identity changed')
        expected={(r['register_record'],r['register_word']):r for r in materials['observations'] if r['capture']==capture['key']}
        commands,push=read_ppdmp(str(path));registers={};vertices=None
        matrices={k:[None]*n for k,n in [('world',12),('view',12),('projection',16),('bones',96)]}
        cursors={k:0 for k in matrices};found=set()
        for record,(kind,size,ptr) in enumerate(commands):
            check(ptr+size<=len(push),'PPDMP push extent differs');raw=push[ptr:ptr+size]
            if kind==0:
                at=17*4
                for lo,hi in CONTEXT_RANGES:
                    for cmd in range(lo,hi+1):
                        word=struct.unpack_from('<I',raw,at)[0];at+=4
                        check(word>>24==cmd or(cmd<=2 and word==0),'Saved GE context opcode differs')
                        registers[cmd]=word&0xFFFFFF
            elif kind==2:vertices=raw
            elif kind==1:
                check(size%4==0,'Truncated GE command')
                for word_index in range(size//4):
                    word=struct.unpack_from('<I',raw,word_index*4)[0];cmd,val=word>>24,word&0xFFFFFF
                    registers[cmd]=val
                    if cmd in (0x3A,0x3C,0x3E,0x2A):
                        key={0x3A:'world',0x3C:'view',0x3E:'projection',0x2A:'bones'}[cmd]
                        cursors[key]=val&(127 if key=='bones' else 15)
                    elif cmd in (0x3B,0x3D,0x3F,0x2B):
                        key={0x3B:'world',0x3D:'view',0x3F:'projection',0x2B:'bones'}[cmd];i=cursors[key]
                        if i<len(matrices[key]):matrices[key][i]=val
                        cursors[key]=(i+1)&(127 if key=='bones' else 15)
                    target=(record,word_index)
                    if cmd!=4 or target not in expected:continue
                    e=expected[target];vt=registers[0x12];count=val&0xFFFF
                    check(sha(struct.pack('<I',vt)+vertices)==e['vertex_sha256'],'Target Aya geometry identity differs')
                    check(count==e['vertex_count'] and ((val>>16)&7)==3,'Only original Aya triangle PRIMs supported')
                    check(all(registers[int(k,16)]==v for k,v in e['register_payloads'].items()),'PRIM state differs from verified snapshot')
                    check(not(vt&(1<<23)) and ((vt>>11)&3)==0 and ((vt>>18)&7)==0 and
                          ((vt>>2)&7)==0 and ((vt>>9)&3)==2 and ((vt>>7)&3)==2 and
                          ((vt>>5)&3)==1 and (vt&3)==2,'Unsupported original vertex format')
                    check((registers[0x17]&1)==1 and (registers[0x1D]&1)==1 and
                          (registers[0x9B]&1)==0 and (registers[0xC0]&3)==0,
                          'Lighting/culling/directUV path differs')
                    slots=((vt>>14)&7)+1;stride,off=layout(vt)
                    check(len(vertices)==count*stride,'Original vertex extent differs')
                    check(all(v is not None for v in matrices['world']) and
                          all(v is not None for v in matrices['bones'][:slots*12]),'Missing original matrix words')
                    binary_start=len(payload)
                    payload+=struct.pack('<256I',*[registers.get(i,0)for i in range(256)])
                    payload+=struct.pack('<12f',*[float24(v)for v in matrices['world']])
                    payload+=struct.pack('<96f',*[float24(v)if v is not None else 0 for v in matrices['bones']])
                    payload+=struct.pack('<2I',count,slots)
                    for i in range(count):
                        at=i*stride
                        position=[v/32768 for v in struct.unpack_from('<3h',vertices,at+off['pos'][0])]
                        normal=[v/128 for v in struct.unpack_from('<3b',vertices,at+off['nrm'][0])]
                        weights=[v/32768 for v in struct.unpack_from('<'+'H'*slots,vertices,at+off['wt'][0])]+[0]*(8-slots)
                        uv=[v/32768 for v in struct.unpack_from('<2H',vertices,at+off['uv'][0])]
                        payload+=struct.pack('<16f',*(position+normal+weights+uv))
                    draws.append(dict(capture=capture['key'],packet=e['packet'],register_record=record,register_word=word_index,
                                      vertex_sha256=e['vertex_sha256'],vertex_count=count,weight_slots=slots,vtype=vt,
                                      first_output_vertex=first,binary_byte_offset=binary_start,
                                      WORLD_payload=matrices['world'][:],VIEW_payload=matrices['view'][:],
                                      PROJECTION_payload=matrices['projection'][:]))
                    first+=count;found.add(target)
        check(found==set(expected),'Incomplete original Aya observation coverage')
    check(len(draws)==318 and first==10368,'Complete recorded Aya inventory differs')
    binary=a.out/'lighting_inputs.bin';binary.write_bytes(payload)
    manifest=dict(schema='aya-original-ge-lighting-inputs/v1',passed=True,source_material_sha256=SOURCE_SHA,
                  captures=materials['captures'],binary=dict(file=str(binary.resolve()),bytes=len(payload),sha256=sha(payload)),
                  draws=draws,total_vertices=first,draw_count=len(draws),
                  binary_format='T3BLIT1 Ndraw; each:256regU32,12WORLDf32,96BONEf32,countU32,weightCountU32,count*(pos3,normal3,weights8,uv2)f32',
                  recorded_final_lighting_outputs_available=False,colors_are_future_reconstructions=True,
                  limits=['Only three actual retained poses; not a 60-frame dynamic light timeline.',
                          'A matching software-lighting reference is not original hardware/GPU pixel evidence.'])
    (a.out/'inputs.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'draws':len(draws),'vertices':first,'bytes':len(payload)}))


if __name__=='__main__':main()
