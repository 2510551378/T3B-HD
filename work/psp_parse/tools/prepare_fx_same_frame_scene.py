"""Recover same-capture actors/world around CPU-correlated effect observations."""
import argparse
import collections
import hashlib
import json
import struct
from pathlib import Path
import numpy as np
from PIL import Image
from extract_runtime_character import read_ppdmp, layout
from inventory_original_scene import draw_stream
from export_aya_actual_weapon import matrix_draws, WEAPON_SHA
from exact_aya_materials import iter_material_draws, decode_texture, material_parameters

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT/'out/FX_VERTEX_COLOR_GE_20261021/correlation_v3/verification.json'


def check(v, s):
    if not v: raise ValueError(s)
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(b): return hashlib.sha256(b).hexdigest()
def ident(p): return dict(file=str(p.resolve()), sha256=sha(p))
def f24(v): return (np.asarray(v, dtype='<u4') << 8).view('<f4').astype(float)
def write(p, v): p.write_text(json.dumps(v, indent=2), encoding='utf-8')


def known_packets():
    aya_path=ROOT/'out/AYA_NATIVE_GLTF_20261020/raw/input_materials.json'
    other_path=ROOT/'out/ORIGINAL_ACTOR_SOURCE_METADATA.json'
    aya=read(aya_path); other=read(other_path)
    result={p['vertex_sha256']:('body',p['packet']) for p in aya['packets']}
    result.update({p['vertex_sha256']:('other_original_actor',p['draw']) for p in other['packets']})
    check(len(result)==134,'Known packet identity collision')
    result[WEAPON_SHA]=('weapon',0)
    return result,[ident(aya_path),ident(other_path)]


def recover(out):
    check(not out.exists(),'Never overwrite recovered source inputs'); out.mkdir(parents=True)
    known,identities=known_packets(); proof=read(PROOF)
    data=bytearray(b'T3BLIT1\0'+struct.pack('<I',3*135)); rows=[]; frames=[]; first=0
    for b in proof['matched_blocks']:
        sample=b['GE_sample']; cap=Path(b['capture']['file']); check(sha(cap)==b['capture']['sha256'],'Capture changed')
        cmds,push=read_ppdmp(str(cap)); mats={(d['register_record'],d['register_word']):d for d in matrix_draws(cmds,push)}
        states={(d['register_record'],d['register_word']):d for d in iter_material_draws(cmds,push)}
        selected=[]
        for d in draw_stream(cmds,push):
            v=d['vertex']; raw=push[v['pointer']:v['pointer']+v['bytes']]; h=digest(struct.pack('<I',d['vtype'])+raw)
            if h in known: selected.append((d,raw,h))
        cats=collections.Counter(known[h][0] for d,raw,h in selected)
        check(cats==dict(body=106,weapon=1,other_original_actor=28),'Incomplete or duplicate same-frame actor identities: '+str(cats))
        start=len(rows)
        for d,raw,h in selected:
            key=d['register_record'],d['register_word']; m=mats[key]; r=states[key]['registers']; vt=d['vtype']; n=d['count']
            slots=((vt>>14)&7)+1; stride,off=layout(vt)
            check(d['primitive']==3 and len(raw)==stride*n and not(vt&0x800000) and not((vt>>11)&3) and not((vt>>18)&7),'Unsupported actor primitive')
            check(((vt>>2)&7)==0 and ((vt>>9)&3)==2 and ((vt>>7)&3)==2 and ((vt>>5)&3)==1 and vt&3==2,'Unsupported actor layout')
            check(m['world']==d['world'] and m['view']==d['view'] and all(x is not None for x in m['world']+m['bones'][:slots*12]),'Missing effective actor matrices')
            at=len(data); data.extend(struct.pack('<256I',*[r.get(i,0) for i in range(256)]))
            data.extend(f24(m['world']).astype('<f4').tobytes()); data.extend(f24([x or 0 for x in m['bones']]).astype('<f4').tobytes())
            data.extend(struct.pack('<2I',n,slots))
            for i in range(n):
                p=i*stride
                pos=[x/32768 for x in struct.unpack_from('<3h',raw,p+off['pos'][0])]
                normal=[x/128 for x in struct.unpack_from('<3b',raw,p+off['nrm'][0])]
                wt=[x/32768 for x in struct.unpack_from('<%dH'%slots,raw,p+off['wt'][0])]+[0]*(8-slots)
                uv=[x/32768 for x in struct.unpack_from('<2H',raw,p+off['uv'][0])]
                data.extend(struct.pack('<16f',*(pos+normal+wt+uv)))
            category,packet=known[h]
            rows.append(dict(sample=sample,category=category,packet=packet,record=key[0],word=key[1],vertex_sha256=h,
                             vertex_count=n,first_output_vertex=first,binary_byte_offset=at,WORLD_payload=d['world'],VIEW_payload=d['view'],PROJECTION_payload=d['proj']))
            first+=n
        frames.append(dict(sample=sample,capture=b['capture'],first_draw=start,draws=len(selected)))
    check(len(rows)==405,'Incomplete 3-frame actor coverage')
    binary=out/'lighting_inputs.bin'; binary.write_bytes(data)
    result=dict(passed=True,binary=ident(binary),draw_count=len(rows),total_vertices=first,draws=rows,frames=frames,
                provenance=identities,CPU_GE_proof=ident(PROOF),producer=ident(Path(__file__)),original_timing_verified=False)
    write(out/'inputs.json',result); print(json.dumps(dict(passed=True,draws=len(rows),vertices=first)))


def export_scene(inputs_path, comparison_path, out):
    check(not out.exists(),'Never overwrite exported scene'); out.mkdir(parents=True)
    inputs=read(inputs_path); comparison=read(comparison_path); binary=Path(inputs['binary']['file'])
    check(inputs['passed'] and comparison['passed'] and sha(binary)==comparison['inputs_sha256']==inputs['binary']['sha256'],'Skin/light input comparison differs')
    lit_path=comparison_path.parent/'native_outputs.bin'; official=comparison_path.parent/'official_outputs.bin'
    check(lit_path.read_bytes()==official.read_bytes() and sha(official)==comparison['official_output_sha256'],'Production and pinned software reference differ')
    dt=np.dtype([('position','<f4',3),('normal','<f4',3),('color','u1',4),('secondary','u1',3),('pad','u1')])
    lit=np.frombuffer(lit_path.read_bytes(),dtype=dt); skin_input=binary.read_bytes()
    proof=read(PROOF); target={(m['GE_sample'],m['record'],m['word']):m for m in proof['matched_primitives']}
    atlases={}; frames=[]; blocks=[]
    for f in inputs['frames']:
        sample=f['sample']; cap=Path(f['capture']['file']); check(sha(cap)==f['capture']['sha256'],'Capture changed')
        cmds,push=read_ppdmp(str(cap)); states={(d['register_record'],d['register_word']):d for d in iter_material_draws(cmds,push)}
        actors={(d['record'],d['word']):d for d in inputs['draws'] if d['sample']==sample}
        draws=[]; parts=[]; excluded=[]
        for d in draw_stream(cmds,push):
            key=d['register_record'],d['register_word']; st=states[key]; r=st['registers']; tk=(sample,*key)
            if key not in actors and d['vtype']!=0x11f and tk not in target:
                excluded.append(dict(record=key[0],word=key[1],vtype=d['vtype'],primitive=d['primitive'])); continue
            check(r[0x23]==1 and r[0xde]==7 and r[0xd2]==3,'Unsupported source depth contract')
            check(r[0x20]==r[0x25]==r[0x28]==r[0xe8]==r[0xe9]==0,'Unsupported source raster state')
            check(r[0x15]==r[0xd4]==0 and r[0x16]==r[0xd5]==0x43ddf and r[0xd6]==0 and r[0xd7]==65535,'Source viewport/range differs')
            check(r[0xdf] in (0x32,0xa6) and (r[0xdf]!=0xa6 or r[0xe1]==0xffffff),'Unsupported blend')
            check(not(r[0x22]&1) or r[0xdb]==0xff0006,'Unsupported alpha test')
            check(not(r[0x24]&1) or (r[0xdc]==1 and r[0xdd]==0x20201),'Unsupported stencil')
            params=material_parameters(r)
            check(params['texture_enabled'] and params['texture_function']==0 and params['texture_alpha_used'] and params['uv_map_mode']==0 and ((r[0xc2]>>16)&7)==0,'Unsupported texture mode')
            check(params['min_filter_raw'] in (1,7) and params['mag_filter_raw']==1 and r[0x9b] in (0,1),'Unsupported sampler/culling')
            tex=st['texture0']; check(tex is not None and not tex['framebuffer'],'Framebuffer dependency not implemented')
            rgba,facts=decode_texture(tex['raw'],r,st['clut'],st['clut_known']); th=facts['rgba_sha256']
            if th not in atlases:
                png=out/('original_'+th[:16]+'.png'); Image.frombytes('RGBA',(facts['width'],facts['height']),rgba).save(png)
                atlases[th]=dict(index=len(atlases),width=facts['width'],height=facts['height'],rgba=rgba,png=ident(png),rgba_sha256=th)
            raw=push[d['vertex']['pointer']:d['vertex']['pointer']+d['vertex']['bytes']]; vt=d['vtype']; n=d['count']; stride,off=layout(vt)
            W=np.eye(4); W[:,:3]=f24(d['world']).reshape(4,3)
            if key in actors:
                a=actors[key]; check(a['vertex_sha256']==digest(struct.pack('<I',vt)+raw),'Actor geometry mismatch')
                source=lit[a['first_output_vertex']:a['first_output_vertex']+n]; check(not np.any(source['secondary']),'Separate specular not handled')
                world=source['position'].astype(float); origin=(world.min(0)+world.max(0))/2
                pos=(world-origin).astype('<f4'); transform=np.eye(4); transform[3,:3]=origin
                color=source['color'].astype('<f4')/np.float32(255)
                uv=np.array([struct.unpack_from('<2f',skin_input,a['binary_byte_offset']+1464+i*64+56) for i in range(n)],dtype='<f4')
                check(params['uv_scale']==[1.,1.] and params['uv_offset']==[0.,0.],'Actor UV mode differs')
                category=a['category']
            else:
                check(not((vt>>9)&3) and not((vt>>11)&3) and not(vt&0x800000) and not((vt>>18)&7),'Unsupported unweighted geometry')
                pos=np.array([struct.unpack_from('<3h',raw,i*stride+off['pos'][0]) for i in range(n)],dtype='<f4')/np.float32(32768)
                transform=W
                if tk in target:
                    check(vt==0x11e and d['primitive']==4 and n==4 and r[0x17]==0,'Target effect layout differs')
                    uv=np.array([struct.unpack_from('<2H',raw,i*stride) for i in range(n)],dtype='<f4')/np.float32(32768)
                    category='CPU_correlated_effect'
                else:
                    check(vt==0x11f and d['primitive']==3 and r[0x17]==1 and all(r[k]==0 for k in range(0x18,0x1c)) and r[0x53]==7 and r[0x54]==0 and r[0x5c]==0xffffff and r[0x5d]==255,'Unproven unweighted lighting')
                    uv=np.array([struct.unpack_from('<2f',raw,i*stride) for i in range(n)],dtype='<f4'); category='unweighted_world'
                uv=(uv*f24([r[0x48],r[0x49]]).astype('<f4')).astype('<f4')+f24([r[0x4a],r[0x4b]]).astype('<f4')
                color=np.array([list(raw[i*stride+off['col'][0]:i*stride+off['col'][0]+4]) for i in range(n)],dtype='<f4')/np.float32(255)
            order=np.arange(n) if d['primitive']==3 else np.array([i for j in range(n-2) for i in ([j+1,j,j+2] if j&1 else [j,j+1,j+2])])
            vertex=np.column_stack([pos,uv,color]).astype('<f4')[order]
            V=np.eye(4); V[:,:3]=f24(d['view']).reshape(4,3); P=f24(d['proj']).reshape(4,4)
            vp=f24([r[k] for k in (0x42,0x43,0x44)]); center=f24([r[k] for k in (0x45,0x46,0x47)]); offset=np.array([r[k]&65535 for k in (0x4c,0x4d)])/16
            R=np.diag([vp[0]/240,-vp[1]/136,vp[2]/65535,1]); R[3,:3]=[(center[0]-offset[0])/240-1,1-(center[1]-offset[1])/136,center[2]/65535]
            matrix=(transform@V@P@R).astype('<f4'); fog=transform@V[:,2]; fog[3]+=f24([r[0xcd]])[0]; fog=(fog*f24([r[0xce]])[0]).astype('<f4')
            flags=(r[0x21]&1)|((1-(r[0xe7]&1))<<1)|((r[0x1d]&1)<<2)|(((r[0xc9]>>16)&1)<<3)|((r[0x1f]&1)<<4)|((r[0x24]&1)<<5)|((r[0x1c]&1)<<6)
            flags|=(r[0xc7]&1)<<8|((r[0xc7]>>8)&1)<<9|int(r[0xdf]==0xa6)*3072|int(tk in target)*4096|int(not(r[0x22]&1))*8192|(r[0x9b]<<14)
            texture=atlases[th]['index']; ordinal=len(draws); ref=(r[0xdc]>>8)&255; fog_rgb=[(r[0xcf]>>(8*k))&255 for k in range(3)]+[0]
            parts.append(struct.pack('<5I',texture,ordinal,flags,len(vertex),ref)+matrix.tobytes()+fog.tobytes()+struct.pack('<4I',*fog_rgb)+vertex.tobytes())
            draws.append(dict(record=key[0],word=key[1],category=category,owner=ordinal+1,flags=flags,vertices=len(vertex),texture=texture,
                              source_vertex_sha256=digest(struct.pack('<I',vt)+raw),vertex_input_sha256=digest(vertex.tobytes()),texture_RGBA_sha256=th,
                              matrix=matrix.tolist(),fog=fog.tolist(),registers={hex(k):v for k,v in r.items()}))
        check(collections.Counter(d['category'] for d in draws)['CPU_correlated_effect']==8,'Target effect coverage differs')
        frames.append(dict(sample=sample,capture=f['capture'],draws=draws,excluded=excluded)); blocks.append(b''.join(parts))
    payload=bytearray(b'T3BSFC1\0'+struct.pack('<4I',480,272,3,len(atlases)))
    for t in atlases.values(): payload.extend(struct.pack('<2I',t['width'],t['height'])+t['rgba'])
    for f,b in zip(frames,blocks): payload.extend(struct.pack('<2I',f['sample'],len(f['draws']))+b)
    path=out/'scene_gpu.bin'; path.write_bytes(payload)
    result=dict(passed=True,frames=frames,binary=ident(path),atlases=[{k:v for k,v in t.items() if k!='rgba'} for t in atlases.values()],
                skin_inputs=ident(inputs_path),lighting_comparison=ident(comparison_path),production_skin_output=ident(lit_path),CPU_GE_proof=ident(PROOF),producer=ident(Path(__file__)),
                complete_scene=False,original_timing_verified=False,UE_executed=False)
    write(out/'inputs.json',result); print(json.dumps(dict(passed=True,frames=3,atlases=len(atlases),draws=sum(len(f['draws']) for f in frames))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('stage',choices=['recover','export']); p.add_argument('--out',type=Path,required=True)
    p.add_argument('--inputs',type=Path); p.add_argument('--comparison',type=Path); a=p.parse_args()
    if a.stage=='recover': recover(a.out)
    else: export_scene(a.inputs,a.comparison,a.out)
