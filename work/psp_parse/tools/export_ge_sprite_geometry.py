"""Validate raw source and independent upstream reference before quad generation."""
import argparse,hashlib,json,struct
from pathlib import Path
import numpy as np
from extract_runtime_character import read_ppdmp
from inventory_original_scene import draw_stream
from exact_aya_materials import iter_material_draws,unpack_color
import ge_sprite_geometry as kernel


def check(v,msg):
    if not v:raise ValueError(msg)
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def identity(p):return dict(file=str(p.resolve()),sha256=sha(p))
def file(r):
    p=Path(r['file']);check(sha(p)==r['sha256'],'Changed evidence: '+str(p));return p


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('inputs','reference','out'):p.add_argument('--'+key,required=True,type=Path)
    a=p.parse_args();check(not a.out.exists(),'Never replace sprite geometry proof');a.out.mkdir(parents=True)
    m=read(a.inputs);reference=read(a.reference);check(reference['passed']and file(reference['inputs'])==a.inputs.resolve(),'Wrong upstream reference pairing')
    raw=file(m['binary']).read_bytes();check(file(reference['input_binary']).read_bytes()==raw,'Reference endpoints differ')
    for row in reference['sources']+reference['generated_functions']+reference['compatibility_headers']:[file(row)]
    file(reference['driver'])
    endpoints=np.fromfile(file(reference['outputs']['endpoints']),dtype=kernel.ENDPOINT);parts=np.fromfile(file(reference['outputs']['parts']),dtype=kernel.PART)
    pixels=np.fromfile(file(reference['outputs']['candidate_pixels']),dtype=kernel.PIXEL)
    check(raw[:8]==b'T3BSPR1\0'and struct.unpack_from('<I',raw,8)[0]==12,'Wrong original source format')
    at=12;ep_at=part_at=pixel_at=0;frame_rows=[];quads=[];orientations={};split_pairs=0
    for row in m['draws']:
        sample=row['sample'];path=Path(row['capture']['path']);check(sha(path)==row['capture']['sha256'],'Original PPDMP changed')
        commands,push=read_ppdmp(str(path));state=next(d for d in iter_material_draws(commands,push)if(d['register_record'],d['register_word'])==(row['record'],row['word']))
        draw=next(d for d in draw_stream(commands,push)if(d['register_record'],d['register_word'])==(row['record'],row['word']))
        r=state['registers'];count=draw['count'];v=draw['vertex'];vr=push[v['pointer']:v['pointer']+v['bytes']]
        expected=struct.pack('<256I',*[r.get(i,0)for i in range(256)])
        for k in ('world','view','proj'):expected+=kernel.f24(draw[k]).tobytes()
        expected+=struct.pack('<I',count)
        for i in range(count):
            u,v,c,x,y,z=struct.unpack_from('<2BH3h',vr,i*10);expected+=struct.pack('<3f2f4B',x/32768,y/32768,z/32768,u/128,v/128,*unpack_color(c,2))
        check(raw[at:at+len(expected)]==expected,'Evaluated sprite input does not match original raw state/positions/UV/colour')
        regs=np.frombuffer(raw,dtype='<u4',count=256,offset=at);world=np.frombuffer(raw,dtype='<f4',count=12,offset=at+1024)
        view=np.frombuffer(raw,dtype='<f4',count=12,offset=at+1072);proj=np.frombuffer(raw,dtype='<f4',count=16,offset=at+1120)
        source=np.frombuffer(raw,dtype=kernel.SOURCE,count=count,offset=at+1188);at+=len(expected)
        model,uv=kernel.transform(regs,world,view,proj,source);official=endpoints[ep_at:ep_at+count];ep_at+=count
        check(model['clip'].tobytes()==official['clip'].tobytes(),'Clip transforms differ from unchanged upstream Math3D arithmetic')
        check(model['fog'].tobytes()==official['fog'].tobytes()and model['outside'].tobytes()==official['outside'].tobytes(),'Fog/range transforms differ from unchanged upstream')
        valid=~model['outside'].astype(bool)
        check(model['xy'][valid].tobytes()==official['xy'][valid].tobytes()and model['z'][valid].tobytes()==official['z'][valid].tobytes(),'Valid endpoint screen rounding/Z16 differs from upstream')
        frame_parts=[];frame_vertices=[];pair_counts={}
        for part in kernel.split(model,uv,source['color'],sample):
            part['id']=part_at+1;candidate,plane=kernel.raster(part);off=parts[part_at]
            check(off['sample']==sample and off['pair']==part['pair']and off['id']==part['id']and np.array_equal(off['xy'],part['xy'])and off['z']==part['z']and off['color']==part['color'],'Original clip/fog split/flat colour/depth differs')
            check(off['uv'].tobytes()==part['uv'].tobytes()and off['fog'].tobytes()==np.asarray(part['fog'],dtype='<f4').tobytes(),'Split UV/fog differs from upstream ProcessRect')
            check(off['first']==pixel_at and off['pixels']==len(candidate),'Candidate coverage count/stream differs')
            output=np.asarray(candidate,dtype=kernel.PIXEL)
            check(output.tobytes()==pixels[pixel_at:pixel_at+len(candidate)].tobytes(),'Coverage/UV/fog/colour/depth differs from unchanged DrawRectangle')
            first_vertex=sum(len(q)for q in frame_vertices)
            if plane is not None:
                geometry=kernel.quad(part,plane);frame_vertices.append(geometry)
                x0,y0,x1,y1=part['xy'];orientation=str((x0<x1,y0<y1));orientations[orientation]=orientations.get(orientation,0)+1
            frame_parts.append(dict(id=part['id'],source_pair=part['pair'],first_vertex=first_vertex,vertices=0 if plane is None else 6,
                first_reference_pixel=pixel_at,reference_pixels=len(candidate),screen_fixed_xy=part['xy'],flat_depth_u16=part['z'],flat_fog=float(part['fog']),
                flat_color_RGBA_u32=part['color'],uv=part['uv'].tolist(),coverage_bounds=None if plane is None else plane['bounds']))
            pair_counts[part['pair']]=pair_counts.get(part['pair'],0)+1;part_at+=1;pixel_at+=len(candidate)
        values=np.concatenate(frame_vertices)if frame_vertices else np.empty((0,10),dtype='<f4');quads.append(values)
        frame_rows.append(dict(sample=sample,source=row,parts=frame_parts,emitted_quad_parts=len(frame_vertices),vertices=len(values),first_vertex=sum(len(q)for q in quads[:-1]),
            clipped_source_pairs=count//2-len(pair_counts),fog_split_pairs=sum(n==2 for n in pair_counts.values())))
        split_pairs+=frame_rows[-1]['fog_split_pairs']
    check(at==len(raw)and ep_at==len(endpoints)and part_at==len(parts)and pixel_at==len(pixels),'Incomplete source/reference stream')
    binary=a.out/'sprite_quad_vertices.f32';binary.write_bytes(np.concatenate(quads).tobytes())
    result=dict(schema='source-rectangle-geometry-reference-proof/v1',passed=True,source_inputs=identity(a.inputs),reference=identity(a.reference),geometry=identity(binary),
        frames=frame_rows,source_endpoints=ep_at,source_rectangles=m['source_rectangles'],reference_parts=part_at,candidate_pixels=pixel_at,
        generated_quad_vertices=sum(len(q)for q in quads),visible_part_orientations=orientations,fog_split_source_pairs=split_pairs,
        model=identity(Path(kernel.__file__)),producer_sha256=sha(Path(__file__)),
        endpoint_clip_and_fog_bits_equal_to_upstream=True,valid_endpoint_screen_xy_z16_equal_to_upstream=True,
        candidate_coverage_UV_fog_RGBA_Z16_bits_equal_to_upstream=True,capture_camera_dependent=True,original_clock_verified=False,
        limits=['Generated quads reproduce captured-camera screen-aligned rectangle geometry. Retain source endpoints/matrices to recompute for a different runtime camera.',
            'Reference candidate pixels precede texture/alpha/depth/blend. GPU raster/UV interpolation and complete PSP pixel equivalence remain separate.'])
    (a.out/'geometry.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k]for k in ('passed','source_rectangles','reference_parts','candidate_pixels','generated_quad_vertices','fog_split_source_pairs')}))


if __name__=='__main__':main()
