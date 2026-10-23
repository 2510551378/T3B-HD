"""Retain original VTYPE119 rectangle endpoints/states before any sprite expansion."""
import argparse,hashlib,json,struct
from pathlib import Path
import numpy as np
from PIL import Image
from extract_runtime_character import read_ppdmp
from inventory_original_scene import draw_stream
from exact_aya_materials import iter_material_draws,decode_texture,unpack_color


def check(v,msg):
    if not v:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def identity(p):return dict(file=str(p.resolve()),sha256=sha(p))
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def f24(v):return (np.array(v,dtype='<u4')<<8).view('<f4')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base-inputs',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    check(not a.out.exists(),'Never replace original sprite observations');a.out.mkdir(parents=True)
    base=read(a.base_inputs);rows=[];textures={};binary=a.out/'source_endpoints.bin';first=0
    with binary.open('wb')as output:
        output.write(b'T3BSPR1\0'+struct.pack('<I',12))
        for i,f in enumerate(base['frames']):
            capture=Path(f['capture']['path']);check(sha(capture)==f['capture']['sha256'],'Original GE capture changed')
            commands,push=read_ppdmp(str(capture));states={(d['register_record'],d['register_word']):d for d in iter_material_draws(commands,push)}
            selected=[d for d in draw_stream(commands,push)if d['vtype']==0x119];check(len(selected)==1,'Expected exactly one original119 rectangle batch')
            d=selected[0];st=states[(d['register_record'],d['register_word'])];r=st['registers'];count=d['count'];v=d['vertex'];raw=push[v['pointer']:v['pointer']+v['bytes']]
            check(d['primitive']==6 and count%2==0 and len(raw)==count*10,'Original sprite topology/extent changed')
            check(all(x is not None for k in ('world','view','proj')for x in d[k]),'Missing explicit sprite matrices')
            check(r[0x17]==r[0x1c]==r[0x1d]==r[0x24]==r[0xe8]==r[0xe9]==0 and r[0x1f]==r[0x21]==r[0x22]==r[0x23]==r[0xe7]==1 and r[0xde]in(6,7),'Unobserved sprite light/cull/fog/depth path')
            check(r[0xdf]==0x32 and r[0xc9]==0x100 and r[0xc7]==0x101 and r[0xc6]==0x107 and r[0xc2]==1 and r[0xdb]==0xff0006 and r[0xc0]==0,'Unobserved original sprite texture/blend state')
            tex=st['texture0'];check(tex is not None and not tex['framebuffer'],'Sprite texture requires framebuffer dependency')
            rgba,facts=decode_texture(tex['raw'],r,st['clut'],st['clut_known']);ts=facts['rgba_sha256']
            if ts not in textures:
                png=a.out/('original_sprite_'+ts[:16]+'.png');Image.frombytes('RGBA',(facts['width'],facts['height']),rgba).save(png);textures[ts]=dict(png=identity(png),facts=facts)
            begin=output.tell();output.write(struct.pack('<256I',*[r.get(k,0)for k in range(256)]))
            for k in ('world','view','proj'):output.write(f24(d[k]).tobytes())
            output.write(struct.pack('<I',count))
            for j in range(count):
                at=j*10;u,v,c,x,y,z=struct.unpack_from('<2BH3h',raw,at)
                output.write(struct.pack('<3f2f4B',x/32768,y/32768,z/32768,u/128,v/128,*unpack_color(c,2)))
            rows.append(dict(sample=i,capture=f['capture'],record=d['register_record'],word=d['register_word'],source_vertices=count,source_rectangles=count//2,
                first_endpoint=first,binary_byte_offset=begin,raw_vertex_sha256=hashlib.sha256(struct.pack('<I',0x119)+raw).hexdigest(),
                WORLD_payload=d['world'],VIEW_payload=d['view'],PROJECTION_payload=d['proj'],registers={hex(k):v for k,v in r.items()},texture_RGBA_sha256=ts))
            first+=count
    result=dict(schema='original-GE-rectangle-endpoints/v1',passed=True,base_inputs=identity(a.base_inputs),binary=identity(binary),draws=rows,textures=textures,
        source_draws=12,source_endpoints=first,source_rectangles=first//2,producer_sha256=sha(Path(__file__)),source_clock_verified=False,
        geometry_expansion_performed=False,limits=['Raw original rectangle endpoint observations only; geometry and rasterization are not yet accepted.'])
    (a.out/'inputs.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,source_endpoints=first,source_rectangles=first//2,textures=len(textures))))


if __name__=='__main__':main()
