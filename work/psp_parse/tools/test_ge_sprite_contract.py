"""Upstream-backed synthetic tests for rectangle orientation/fog/flat attributes."""
import argparse,hashlib,json,struct,subprocess,sys
from pathlib import Path
import numpy as np
import ge_sprite_geometry as kernel


def check(v,msg):
    if not v:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def identity(p):return dict(file=str(p.resolve()),sha256=sha(p))
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def word(f):return int(np.asarray(f,dtype='<f4').view('<u4'))>>8


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    check(not a.out.exists(),'Never replace synthetic contract evidence');a.out.mkdir(parents=True)
    root=Path(__file__).resolve().parents[1];source=read(root/'out/GE_RECT_SPRITES_20261021/source_inputs_v1/inputs.json');prototype={int(k,16):v for k,v in source['draws'][0]['registers'].items()}
    descriptions=['TL_BR_split_fog','BL_TR_rotated_split_fog','TR_BL_rotated_split_fog','BR_TL_split_fog','fog_difference_below_halfstep','equal_fog_flat_second_colour',
        'outside_Z_range','zero_width','zero_height','outside_GE_screen_range','depth_equal_GEQUAL_pass','depth_equal_GREATER_reject','outside_drawing_viewport_clipped']
    cases=[];payload=bytearray(b'T3BSPR1\0'+struct.pack('<I',len(descriptions)));color_a=0xff0000ff;color_b=0x8811ff00
    for i,name in enumerate(descriptions):
        r=dict(prototype);r[4]=(6<<16)|2;r[0xde]=6 if i==11 else 7;r[0xcf]=68|(112<<8)|(142<<16)
        for k,f in ((0x42,240.),(0x43,-136.),(0x44,32767.5),(0x45,2048.),(0x46,2048.),(0x47,32767.5),(0xcd,0.),(0xce,1.)):
            r[k]=word(f)
        r[0x4c]=1808*16;r[0x4d]=1912*16
        points=np.array([[-.5,.5,0.],[.5,-.5,.5]],dtype='<f4');world=np.eye(4,dtype='<f4')[:,:3].flatten();view=world.copy();proj=np.eye(4,dtype='<f4')
        if i==1:points[:,1]*=-1
        if i==2:points[:,0]*=-1
        if i==3:points[:,:2]*=-1
        if i==4:points[:,2]=[.25,8208/32768]
        if i==5:points[:,2]=.5
        if i==6:points[:,2]=[-.75,.75];proj[2,2]=2
        if i==7:points[:,0]=.25
        if i==8:points[:,1]=.25
        if i==9:proj[0,0]=32
        if i==12:proj[0,0]=16
        if i in(10,11):points[:,2]=-1
        v=np.empty(2,dtype=kernel.SOURCE);v['pos']=points;v['uv']=[[0,0],[1,1]];v['color']=[color_a,color_b]
        payload+=struct.pack('<256I',*[r.get(k,0)for k in range(256)])+world.tobytes()+view.tobytes()+proj.tobytes()+struct.pack('<I',2)+v.tobytes()
        cases.append(dict(case=i,name=name,r=r,world=world,view=view,proj=proj.flatten(),vertices=v))
    binary=a.out/'synthetic_endpoints.bin';binary.write_bytes(payload);manifest=a.out/'inputs.json';manifest.write_text(json.dumps(dict(passed=True,synthetic=True,binary=identity(binary),cases=descriptions),indent=2),encoding='utf-8')
    ref=a.out/'reference';command=[sys.executable,str(root/'tools/build_ge_sprite_reference.py'),'--inputs',str(manifest),'--compiler',str(a.compiler),'--out',str(ref)]
    run=subprocess.run(command,capture_output=True,encoding='utf-8');(a.out/'builder_stdout.log').write_text(run.stdout,encoding='utf-8');(a.out/'builder_stderr.log').write_text(run.stderr,encoding='utf-8');check(run.returncode==0,'Synthetic upstream reference failed')
    rp=read(ref/'reference.json');endpoints=np.fromfile(rp['outputs']['endpoints']['file'],dtype=kernel.ENDPOINT);parts=np.fromfile(rp['outputs']['parts']['file'],dtype=kernel.PART);pixels=np.fromfile(rp['outputs']['candidate_pixels']['file'],dtype=kernel.PIXEL)
    ep_at=part_at=pixel_at=0;rows=[];control=bytearray(b'T3BSCT1\0'+struct.pack('<I',len(descriptions)));geometry=[]
    for c in cases:
        e,uv=kernel.transform(c['r'],c['world'],c['view'],c['proj'],c['vertices']);official=endpoints[ep_at:ep_at+2];ep_at+=2
        check(e['clip'].tobytes()==official['clip'].tobytes()and e['fog'].tobytes()==official['fog'].tobytes()and e['outside'].tobytes()==official['outside'].tobytes(),'Synthetic endpoint transform/fog/range mismatch')
        valid=~e['outside'].astype(bool);check(e['xy'][valid].tobytes()==official['xy'][valid].tobytes()and e['z'][valid].tobytes()==official['z'][valid].tobytes(),'Synthetic valid screen/Z mismatch')
        quads=[];case_first=pixel_at;case_parts=0
        for part in kernel.split(e,uv,c['vertices']['color'],c['case']):
            part['id']=part_at+1;candidate,plane=kernel.raster(part);record=parts[part_at]
            check(record['sample']==c['case']and np.array_equal(record['xy'],part['xy'])and record['color']==color_b and record['z']==part['z'],'Synthetic flat colour/depth/fog-split geometry mismatch')
            check(record['uv'].tobytes()==part['uv'].tobytes()and record['fog'].tobytes()==np.asarray(part['fog'],dtype='<f4').tobytes(),'Synthetic rotated UV/fog mismatch')
            check(record['first']==pixel_at and record['pixels']==len(candidate)and np.asarray(candidate,dtype=kernel.PIXEL).tobytes()==pixels[pixel_at:pixel_at+len(candidate)].tobytes(),'Synthetic candidate coverage/UV/fog mismatch')
            if plane is not None:quads.append(kernel.quad(part,plane))
            pixel_at+=len(candidate);part_at+=1;case_parts+=1
        values=np.concatenate(quads)if quads else np.empty((0,10),dtype='<f4');control+=struct.pack('<2I',32768 if c['r'][0xde]==6 else 0,len(values))+values.tobytes()
        geometry.append(values);rows.append(dict(case=c['case'],name=c['name'],parts=case_parts,vertices=len(values),reference_first_pixel=case_first,reference_pixels=pixel_at-case_first,strict_GREATER=c['r'][0xde]==6))
    check(ep_at==len(endpoints)and part_at==len(parts)and pixel_at==len(pixels),'Synthetic stream incomplete')
    controls=a.out/'gpu_controls.bin';controls.write_bytes(control)
    result=dict(schema='upstream-backed-rectangle-synthetic-contract/v1',passed=True,synthetic=True,reference=identity(ref/'reference.json'),controls=identity(controls),cases=rows,
        endpoint_and_candidate_pixel_bits_equal_to_upstream=True,model=identity(Path(kernel.__file__)),producer_sha256=sha(Path(__file__)),GPU_executed=False,
        limits=['Generated diagnostic cases, not additional original poses. Candidate coverage reference omits texture/alpha/depth/blend.'])
    (a.out/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,cases=len(cases),parts=part_at,candidate_pixels=pixel_at)))


if __name__=='__main__':main()
