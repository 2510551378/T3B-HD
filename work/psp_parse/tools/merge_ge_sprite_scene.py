"""Merge verified source rectangle quads with the accepted real 3D scene."""
import argparse,hashlib,json,struct
from pathlib import Path
import numpy as np
from PIL import Image


def check(v,msg):
    if not v:raise ValueError(msg)
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def identity(p):return dict(file=str(p.resolve()),sha256=sha(p))
def file(r):
    p=Path(r['file']);check(sha(p)==r['sha256'],'Changed evidence: '+str(p));return p


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('base-inputs','sprite-geometry','out'):p.add_argument('--'+key,required=True,type=Path)
    a=p.parse_args();check(not a.out.exists(),'Never replace merged sprite evidence');a.out.mkdir(parents=True)
    base=read(a.base_inputs);raw=file(base['binary']).read_bytes();g=read(a.sprite_geometry)
    check(g['passed']and g['candidate_coverage_UV_fog_RGBA_Z16_bits_equal_to_upstream'],'Sprite geometry not independently verified')
    sprite=read(file(g['source_inputs']));check(file(sprite['base_inputs'])==a.base_inputs.resolve(),'Sprite and scene pairing differs')
    vertices=np.fromfile(file(g['geometry']),dtype='<f4').reshape(-1,10)
    check(raw[:8]==b'T3BGEF2\0'and struct.unpack_from('<3I',raw,8)==(480,272,12),'Wrong base format')
    at=24;texture_data=[];atlases=list(base['atlases']);bank={t['rgba_sha256']:t['index']for t in atlases}
    for t in base['atlases']:
        w,h=struct.unpack_from('<2I',raw,at);end=at+8+w*h*4;texture_data.append(raw[at:end]);at=end
    for ts,t in sprite['textures'].items():
        if ts in bank:continue
        png=file(t['png']);im=Image.open(png).convert('RGBA');check(hashlib.sha256(im.tobytes()).hexdigest()==ts,'Original sprite texture RGBA differs')
        index=len(atlases);bank[ts]=index;atlases.append(dict(index=index,width=im.width,height=im.height,rgba_sha256=ts,png=t['png']))
        texture_data.append(struct.pack('<2I',im.width,im.height)+im.tobytes())
    frames=[];blobs=[]
    for i,(frame,gf)in enumerate(zip(base['frames'],g['frames'])):
        sid,n=struct.unpack_from('<2I',raw,at);at+=8;check(sid==i and n==len(frame['draws']),'Scene frame identity differs');rows={};blocks={}
        for d in frame['draws']:
            key=d['register_record'],d['register_word'];count=d['vertices'];header=raw[at:at+116];v=np.frombuffer(raw,dtype='<f4',count=count*9,offset=at+116).reshape(count,9);at+=116+count*36
            expanded=np.column_stack([v[:,:5],np.zeros(count,dtype='<f4'),v[:,5:]]).astype('<f4');rows[key]=dict(d,base_vertex_input_sha256=d['vertex_input_sha256'],vertex_input_sha256=hashlib.sha256(expanded.tobytes()).hexdigest());blocks[key]=header+expanded.tobytes()
        source=gf['source'];r={int(k,16):v for k,v in source['registers'].items()};body=next(d for d in frame['draws']if d['category']=='body')
        check(source['capture']==frame['capture'],'Sprite batch is not from same original capture')
        flags=1|16|256|512|4096|(r[0x9b]<<14)|int(r[0xde]==6)<<15|65536
        flags|=int(source['VIEW_payload']!=body['VIEW_payload']or source['PROJECTION_payload']!=body['PROJECTION_payload'])<<7
        first=gf['first_vertex'];count=gf['vertices'];v=vertices[first:first+count];check(count>0 and count%6==0,'No visible sprite quad geometry')
        texture=bank[source['texture_RGBA_sha256']];key=source['record'],source['word'];check(key not in rows,'Sprite overlaps existing geometry observation')
        rgba=[(r[0xcf]>>(8*k))&255 for k in range(3)]+[0]
        blocks[key]=struct.pack('<5I',texture,0,flags,count,(r[0xdc]>>8)&255)+np.eye(4,dtype='<f4').tobytes()+bytes(16)+struct.pack('<4I',*rgba)+v.tobytes()
        rows[key]=dict(owner=0,texture=texture,flags=flags,vertices=count,category='original_rectangle_sprites',register_record=key[0],register_word=key[1],
            WORLD_payload=source['WORLD_payload'],VIEW_payload=source['VIEW_payload'],PROJECTION_payload=source['PROJECTION_payload'],registers=source['registers'],
            texture_RGBA_sha256=source['texture_RGBA_sha256'],vertex_input_sha256=hashlib.sha256(v.tobytes()).hexdigest(),
            source_vertices=source['source_vertices'],source_rectangles=source['source_rectangles'],sprite_geometry_frame=i,
            geometry_space='Captured GE post-transform screen-aligned rectangle quads; recompute raw endpoints for a different camera.',
            capture_camera_dependent=True,per_vertex_flat_fog=True,source_depth_function=r[0xde])
        result=[];chunks=[]
        for ordinal,key in enumerate(sorted(rows)):
            row=rows[key];row['owner']=ordinal+1;block=bytearray(blocks[key]);struct.pack_into('<I',block,4,ordinal)
            result.append(row);chunks.append(bytes(block))
        frames.append(dict(sample=i,capture=frame['capture'],draws=result,excluded_draws=[x for x in frame['excluded_draws']if(x['record'],x['word'])!=(source['record'],source['word'])]));blobs.append(b''.join(chunks))
    check(at==len(raw),'Trailing base geometry')
    binary=a.out/'observed_scene_gpu.bin'
    with binary.open('wb')as output:
        output.write(b'T3BGEF3\0'+struct.pack('<4I',480,272,12,len(atlases)))
        for blob in texture_data:output.write(blob)
        for frame,blob in zip(frames,blobs):output.write(struct.pack('<2I',frame['sample'],len(frame['draws'])));output.write(blob)
    result={**base,'schema':'t3b-scene-with-original-rectangle-sprites/v3','frames':frames,'atlases':atlases,'binary':identity(binary),
        'base_inputs':identity(a.base_inputs),'sprite_geometry':identity(a.sprite_geometry),'producer_sha256':sha(Path(__file__)),
        'vertex_layout':'position3, UV2, sourceFog1, primaryColor4 F32 (40 bytes)',
        'limits':['Original scene remains 3D. Only GE rectangle primitives expand in captured-camera post-transform space; raw endpoints/matrices retained for recomputation.',
                  'Full PSP texture/depth/blend pixel equivalence, lines/HUD/framebuffer postprocess and original timing remain separate.']}
    (a.out/'inputs.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,draws=sum(len(f['draws'])for f in frames),GPU_vertices=sum(d['vertices']for f in frames for d in f['draws']),atlases=len(atlases))))


if __name__=='__main__':main()
