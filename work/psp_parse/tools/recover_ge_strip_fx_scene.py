"""Add all observed unweighted, depth-tested perspective triangle strips.

Retains source geometry/cameras/materials; purpose and authored FX names unknown.
T3BGEF2 extends our own export flags, not the original PSP format.
"""
import argparse,hashlib,json,struct
from pathlib import Path
import numpy as np
from PIL import Image
from extract_runtime_character import read_ppdmp,layout
from inventory_original_scene import draw_stream
from exact_aya_materials import iter_material_draws,decode_texture,unpack_color,material_parameters


def check(v,msg):
    if not v:raise ValueError(msg)
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(b):return hashlib.sha256(b).hexdigest()
def identity(p):return dict(file=str(p.resolve()),sha256=sha(p))
def f24(v):return (np.asarray(v,dtype='<u4')<<8).view('<f4').astype(float)


def decode_unweighted(raw,vt,count):
    check(not(vt&(1<<23))and not((vt>>9)&3)and not((vt>>11)&3)and not((vt>>18)&7),'Unsupported indexed/weighted/morph/through FX')
    stride,fields=layout(vt);check(len(raw)==stride*count,'Incomplete FX vertex buffer')
    po=(vt>>7)&3;code,den={1:('b',128),2:('h',32768),3:('f',1)}[po]
    positions=np.asarray([struct.unpack_from('<3'+code,raw,i*stride+fields['pos'][0])for i in range(count)],dtype=float)/den
    tc=vt&3;code,den={1:('B',128),2:('H',32768),3:('f',1)}[tc]
    uv=np.asarray([struct.unpack_from('<2'+code,raw,i*stride+fields['uv'][0])for i in range(count)],dtype=float)/den
    co=(vt>>2)&7;colors=None
    if co:
        check(co in (4,5,6,7),'Unknown FX colour storage');n=4 if co==7 else 2
        colors=np.asarray([list(unpack_color(int.from_bytes(raw[i*stride+fields['col'][0]:i*stride+fields['col'][0]+n],'little'),co-4))for i in range(count)],dtype=float)/255
    check(np.isfinite(positions).all()and np.isfinite(uv).all(),'Nonfinite original FX vertices')
    return positions,uv,colors


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base-inputs',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    check(not a.out.exists(),'Never replace FX evidence');a.out.mkdir(parents=True)
    base=read(a.base_inputs);source=Path(base['binary']['file']);check(sha(source)==base['binary']['sha256'],'Base geometry changed')
    raw=source.read_bytes();check(raw[:8]==b'T3BGEF1\0','Expected accepted scene format');w,h,n,nt=struct.unpack_from('<4I',raw,8)
    check((w,h,n)==(480,272,12),'Wrong base extent');at=24;atlas_payload=[]
    for t in base['atlases']:
        tw,th=struct.unpack_from('<2I',raw,at);rgba=raw[at+8:at+8+tw*th*4];at+=8+tw*th*4
        check(digest(rgba)==t['rgba_sha256'],'Base texture changed');atlas_payload.append((tw,th,rgba))
    bank={t['rgba_sha256']:dict(t)for t in base['atlases']};blocks=[];frames=[];excluded=[];cache={}
    origin=np.array(base['fixed_shared_PSP_world_origin']);units=base['metres_per_PSP_world_unit'];scale=units*100
    inverse=np.array([[1/scale,0,0,0],[0,0,1/scale,0],[0,1/scale,0,0],[*origin,1]])
    for sample,old in enumerate(base['frames']):
        sid,draw_count=struct.unpack_from('<2I',raw,at);at+=8;check(sid==sample and draw_count==len(old['draws']),'Base frame mismatch')
        rows={};payload={}
        for row in old['draws']:
            vertex_count=struct.unpack_from('<I',raw,at+12)[0];end=at+116+vertex_count*36
            check(vertex_count==row['vertices'],'Base draw vertex count changed');key=row['register_record'],row['register_word'];rows[key]=dict(row);payload[key]=raw[at:end];at=end
        capture=Path(old['capture']['path']);check(sha(capture)==old['capture']['sha256'],'Original GE capture changed')
        commands,push=read_ppdmp(str(capture));states={(d['register_record'],d['register_word']):d for d in iter_material_draws(commands,push)}
        body=next(d for d in old['draws']if d['category']=='body');main_fb=body['registers']['0x9c'];frame_excluded=[]
        for d in draw_stream(commands,push):
            key=d['register_record'],d['register_word']
            if key in rows:continue
            st=states[key];r=st['registers'];vt=d['vtype'];perspective=d['proj'][-1]==0
            eligible=not(vt&(1<<23))and not((vt>>9)&3)and not((vt>>11)&3)and not((vt>>18)&7)and d['primitive']==4 and bool(r[0x23]&1)and r[0x9c]==main_fb and perspective
            if not eligible:
                frame_excluded.append(dict(record=key[0],word=key[1],vtype=vt,primitive=d['primitive'],vertices=d['count'],
                    depth_test=bool(r[0x23]&1),through=bool(vt&(1<<23)),perspective=perspective));continue
            check(all(x is not None for k in ('world','view','proj')for x in d[k]),'Unobserved FX matrix state')
            check(r[0x17]==0 and r[0x50]==1 and r[0xe7]==1 and r[0x24]==0 and r[0xde]==7,'Unsupported FX lighting/flatshade/depth/stencil')
            check(r[0x20]==r[0x25]==r[0x28]==r[0xe8]==r[0xe9]==0 and r[0x9b]in(0,1)and r[0xd2]==3,'Unsupported FX raster contract')
            check(r[0x15]==r[0xd4]==0 and r[0x16]==r[0xd5]==0x43ddf and r[0xd6]==0 and r[0xd7]==65535,'FX viewport/scissor/range changed')
            params=material_parameters(r)
            check(params['texture_enabled']and params['texture_function']==0 and params['texture_alpha_used']and params['uv_map_mode']==0 and
                np.isfinite(params['uv_scale']+params['uv_offset']).all()and params['min_filter_raw']in(1,7)and params['mag_filter_raw']==1 and
                ((r[0xc2]>>16)&7)==0,'FX UV/sampling/mipmap path not supported')
            check(r[0x21]==1 and r[0xdf]in(0x32,0x76,0xa6)and(r[0xdf]!=0xa6 or r[0xe1]==0xffffff),'Unobserved FX blend contract')
            check(not(r[0x22]&1)or r[0xdb]==0xff0006,'Unobserved FX alpha test')
            tex=st['texture0'];check(tex is not None and not tex['framebuffer'],'FX texture requires framebuffer dependency')
            cachekey=(tex['sha256'],digest(st['clut']),digest(st['clut_known']),tuple(r[k]for k in(0xc2,0xc3,0xc5,0xa8,0xb8)))
            if cachekey not in cache:cache[cachekey]=decode_texture(tex['raw'],r,st['clut'],st['clut_known'])
            rgba,facts=cache[cachekey];ts=facts['rgba_sha256']
            if ts not in bank:
                png=a.out/('original_fx_'+ts[:16]+'.png');Image.frombytes('RGBA',(facts['width'],facts['height']),rgba).save(png)
                bank[ts]=dict(index=len(bank),width=facts['width'],height=facts['height'],rgba_sha256=ts,png=identity(png));atlas_payload.append((facts['width'],facts['height'],rgba))
            v=d['vertex'];original=push[v['pointer']:v['pointer']+v['bytes']];pos,uv,color=decode_unweighted(original,vt,d['count'])
            uv=uv.astype('<f4')*np.array(params['uv_scale'],dtype='<f4')+np.array(params['uv_offset'],dtype='<f4')
            if color is None:color=np.tile(np.array([(r[0x55]>>(8*k))&255 for k in range(3)]+[r[0x58]&255],dtype=float)/255,(d['count'],1))
            world=np.column_stack([pos,np.ones(len(pos))])@f24(d['world']).reshape(3,4,order='F').T
            triangles=[(i+1,i,i+2)if i&1 else(i,i+1,i+2)for i in range(d['count']-2)];order=np.asarray(triangles).flatten()
            # FX may encode placement in VIEW. Preserve source-local precision.
            draw_origin=(world.min(0)+world.max(0))/2
            draw_inverse=inverse.copy();draw_inverse[3,:3]=draw_origin
            vertices=np.column_stack([((world-draw_origin)*units*100)[:,[0,2,1]],uv,color]).astype('<f4')[order]
            view=np.eye(4);view[:,:3]=f24(d['view']).reshape(4,3);proj=f24(d['proj']).reshape(4,4)
            vp=f24([r[k]for k in (0x42,0x43,0x44)]);center=f24([r[k]for k in (0x45,0x46,0x47)]);offset=np.array([r[k]&65535 for k in (0x4c,0x4d)])/16
            remap=np.diag([vp[0]/240,-vp[1]/136,vp[2]/65535,1.]);remap[3,:3]=[(center[0]-offset[0])/240-1,1-(center[1]-offset[1])/136,center[2]/65535]
            matrix=(draw_inverse@view@proj@remap).astype('<f4');fog=draw_inverse@view[:,2];fog[3]+=f24([r[0xcd]])[0];fog=(fog*f24([r[0xce]])[0]).astype('<f4')
            fog_rgb=[(r[0xcf]>>(8*k))&255 for k in range(3)]+[0];different=d['view']!=body['VIEW_payload']or d['proj']!=body['PROJECTION_payload']
            flags=(r[0x21]&1)|((1-(r[0xe7]&1))<<1)|((r[0x1d]&1)<<2)|(int(params['color_double'])<<3)|((r[0x1f]&1)<<4)|((r[0x24]&1)<<5)|((r[0x1c]&1)<<6)|(int(different)<<7)
            flags|=int(params['wrap_u']=='clamp')<<8|int(params['wrap_v']=='clamp')<<9|int(r[0xdf]in(0x76,0xa6))<<10|int(r[0xdf]==0xa6)<<11|4096|int(not(r[0x22]&1))<<13|(r[0x9b]<<14)
            texture=bank[ts]['index'];payload[key]=struct.pack('<5I',texture,0,flags,len(vertices),(r[0xdc]>>8)&255)+matrix.tobytes()+fog.tobytes()+struct.pack('<4I',*fog_rgb)+vertices.tobytes()
            rows[key]=dict(owner=0,texture=texture,flags=flags,vertices=len(vertices),source_vertices=d['count'],vtype=vt,primitive=4,triangle_source_indices=triangles,
                category='unweighted_strip_fx',PSP_world_origin_subtracted=draw_origin.tolist(),register_record=key[0],register_word=key[1],vertex_sha256=digest(struct.pack('<I',vt)+original),vertex_input_sha256=digest(vertices.tobytes()),
                WORLD_payload=d['world'],VIEW_payload=d['view'],PROJECTION_payload=d['proj'],registers={hex(k):v for k,v in r.items()},different_from_main_camera=different,texture_RGBA_sha256=ts,
                material_parameters=params,semantic_name=None,texture_facts=facts)
        frame=[];parts=[]
        for i,key in enumerate(sorted(rows)):
            row=rows[key];row['owner']=i+1;block=bytearray(payload[key]);struct.pack_into('<I',block,4,i);parts.append(bytes(block));frame.append(row)
        frames.append(dict(sample=sample,capture=old['capture'],draws=frame,excluded_draws=frame_excluded));blocks.append(b''.join(parts))
    check(at==len(raw),'Trailing base geometry')
    binary=a.out/'observed_scene_gpu.bin'
    with binary.open('wb')as output:
        output.write(b'T3BGEF2\0'+struct.pack('<4I',480,272,12,len(bank)))
        for tw,th,rgba in atlas_payload:output.write(struct.pack('<2I',tw,th));output.write(rgba)
        for f,blob in zip(frames,blocks):output.write(struct.pack('<2I',f['sample'],len(f['draws'])));output.write(blob)
    result={**base,'schema':'t3b-observed-scene-with-strip-FX/v2','frames':frames,'atlases':list(bank.values()),'binary':identity(binary),
        'base_inputs':identity(a.base_inputs),'producer_sha256':sha(Path(__file__)),'original_timing_verified':False,
        'limits':['All observed unweighted depth-tested perspective triangle strips are included; sprite rectangles, lines, HUD and framebuffer postprocess remain excluded.',
                  'Original FX purpose/attachment semantics unknown; source cameras preserved. Double-source-alpha is a continuous D3D approximation, not complete PSP integer pixel equivalence.']}
    (a.out/'inputs.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    fx=[d for f in frames for d in f['draws']if d['category']=='unweighted_strip_fx']
    print(json.dumps(dict(passed=True,frames=12,added_strip_draws=len(fx),added_expanded_vertices=sum(d['vertices']for d in fx),atlases=len(bank))))


if __name__=='__main__':main()
