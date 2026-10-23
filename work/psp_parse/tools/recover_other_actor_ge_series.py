"""Recover the known 11-bone creature from the same 12 Aya/gun GE captures.

Anatomical names, authored clock and gameplay identity remain unconfirmed.
"""
import argparse,hashlib,json,struct
from pathlib import Path
from PIL import Image
from extract_runtime_character import read_ppdmp,layout
from inventory_original_scene import draw_stream
from export_aya_actual_weapon import matrix_draws
from exact_aya_materials import iter_material_draws,decode_texture,material_parameters


def check(v,msg):
    if not v:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def identity(p):return dict(file=str(p.resolve()),sha256=sha(p))
def f24(v):return struct.unpack('<f',struct.pack('<I',v<<8))[0]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    check(not a.out.exists(),'Never replace retained actor evidence');a.out.mkdir(parents=True)
    root=Path(__file__).resolve().parents[1]
    meta_path=root/'out/ORIGINAL_ACTOR_SOURCE_METADATA.json';meta=read(meta_path)
    source=root/'out/WEAPON_GE_PAIRED_20261020/inputs_v1/inputs.json';paired=read(source)
    check(meta['summary']['expected_identity_verified']and meta['summary']['bone_count']==11,'Unverified actor metadata')
    packets=meta['packets'];expected=[p['vertex_sha256']for p in packets]
    check(len(packets)==28 and sum(p['vertex_count']for p in packets)==1800,'Actor metadata coverage changed')
    body_path=Path(paired['paired_body_input']['file']);check(sha(body_path)==paired['paired_body_input']['sha256'],'Body source changed');body=read(body_path)
    draws=[];frames=[];materials={};first=0;binary=a.out/'lighting_inputs.bin'
    with binary.open('wb')as output:
        output.write(b'T3BLIT1\0'+struct.pack('<I',12*28))
        for sample,capture in enumerate(paired['captures']):
            path=Path(capture['path']);check(sha(path)==capture['sha256'],'Original GE capture changed')
            commands,push=read_ppdmp(str(path))
            matrix={(d['register_record'],d['register_word']):d for d in matrix_draws(commands,push)}
            cameras={(d['register_record'],d['register_word']):d for d in draw_stream(commands,push)}
            selected=[]
            for d in iter_material_draws(commands,push):
                vt=d['registers'][0x12];v=d['vertices'];raw=push[v['pointer']:v['pointer']+v['bytes']]
                h=digest(struct.pack('<I',vt)+raw)
                if h in set(expected):selected.append((d,raw,h))
            check([s[2]for s in selected]==expected,'Same capture lacks exact ordered28 actor draws')
            wf=paired['frames'][sample];bf=body['frames'][wf['body_frame_index']];main=body['draws'][bf['first_draw']]
            source_bones={};bone_observations=[];start_draw=len(draws);frame_first=first
            for packet,(d,raw,h)in zip(packets,selected):
                r=d['registers'];vt=r[0x12];key=d['register_record'],d['register_word'];m=matrix[key];camera=cameras[key]
                count=d['count'];slots=((vt>>14)&7)+1;stride,off=layout(vt)
                check(d['primitive']==3 and count==packet['vertex_count']and stride==packet['stride']and vt==packet['vtype']and len(raw)==count*stride,'Original actor format changed')
                check(m['world']==camera['world']and m['view']==camera['view']==main['VIEW_payload']and camera['proj']==main['PROJECTION_payload'],'Actor/Aya camera mismatch')
                check(all(x is not None for x in m['world']+m['bones'][:slots*12]),'Actor lacks explicit effective matrices')
                for slot in packet['active_palette_indices']:
                    source_index=packet['palette_state'][str(slot)];payload=m['bones'][slot*12:slot*12+12]
                    check(source_index not in source_bones or source_bones[source_index]==payload,'Same source bone has inconsistent effective GE matrices in a frame')
                    source_bones[source_index]=payload;bone_observations.append(dict(packet=packet['draw'],slot=slot,source_index=source_index,GE_payload=payload))
                tex=d['texture0'];check(tex is not None and not tex['framebuffer'],'Actor lacks original texture RAM')
                rgba,facts=decode_texture(tex['raw'],r,d['clut'],d['clut_known']);material_id=facts['rgba_sha256']
                if material_id not in materials:
                    png=a.out/('actor_'+material_id[:16]+'.png');Image.frombytes('RGBA',(facts['width'],facts['height']),rgba).save(png)
                    materials[material_id]=dict(png=identity(png),rgba_sha256=material_id,width=facts['width'],height=facts['height'])
                at=output.tell();output.write(struct.pack('<256I',*[r.get(i,0)for i in range(256)]))
                output.write(struct.pack('<12f',*map(f24,m['world'])))
                output.write(struct.pack('<96f',*[f24(x)if x is not None else 0 for x in m['bones']]))
                output.write(struct.pack('<2I',count,slots))
                for i,original in enumerate(packet['vertices']):
                    base=i*stride
                    pos=list(struct.unpack_from('<3h',raw,base+off['pos'][0]));normal=list(struct.unpack_from('<3b',raw,base+off['nrm'][0]))
                    weights=list(struct.unpack_from('<'+'H'*slots,raw,base+off['wt'][0]));uv=list(struct.unpack_from('<2H',raw,base+off['uv'][0]))
                    check(pos==original['position_raw']and normal==original['normal_raw']and weights==original['weights_raw']and uv==original['uv_raw'],'Serialized source metadata disagrees with same-frame vertex bytes')
                    values=[x/32768 for x in pos]+[x/128 for x in normal]+[x/32768 for x in weights]+[0]*(8-slots)+[x/32768 for x in uv]
                    output.write(struct.pack('<16f',*values))
                draws.append(dict(sample=sample,packet=packet['draw'],capture=capture['key'],register_record=key[0],register_word=key[1],
                    vertex_sha256=h,vertex_count=count,weight_slots=slots,vtype=vt,binary_byte_offset=at,first_output_vertex=first,
                    WORLD_payload=m['world'],VIEW_payload=m['view'],PROJECTION_payload=camera['proj'],BONE_payload=m['bones'],
                    material_id=material_id,material_parameters=material_parameters(r),register_payloads={hex(k):v for k,v in r.items()}))
                first+=count
            check(set(source_bones)==set(range(11)),'Effective GE draws do not cover all11 source bones')
            check(len({tuple(d['WORLD_payload'])for d in draws[start_draw:]})==1,'Actor WORLD changes within frame')
            frames.append(dict(sample=sample,capture=capture['key'],first_draw=start_draw,draw_count=28,first_output_vertex=frame_first,vertices=1800,
                source_bones={str(k):v for k,v in sorted(source_bones.items())},source_bone_observations=bone_observations,original_time_seconds=None))
    check(len(frames)==12 and first==21600,'Incomplete actor series')
    changed=[sum(frames[i]['source_bones'][str(k)]!=frames[i-1]['source_bones'][str(k)]for i in range(1,12))for k in range(11)]
    result=dict(schema='other-actor-same-capture-GE-series/v1',passed=True,binary=identity(binary),metadata=identity(meta_path),paired_weapon_input=identity(source),
        captures=paired['captures'],frames=frames,draws=draws,draw_count=len(draws),total_vertices=first,materials=materials,source_bone_parent_indices=[b['parent']for b in meta['bones']],
        source_bone_changed_adjacent_samples=changed,same_GE_dump_pairing=True,original_timing_verified=False,semantic_enemy_name=None,
        producer_sha256=sha(Path(__file__)),limits=['Known original creature mesh and11 source indices; anatomical names and specific enemy name are not established.',
        'GE effective skin matrices are recovered; source CPU local animation timing and authored clips remain separate.'])
    (a.out/'inputs.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,samples=12,draws=len(draws),vertices=first,source_bones=11,materials=len(materials),changed=changed)))


if __name__=='__main__':main()
