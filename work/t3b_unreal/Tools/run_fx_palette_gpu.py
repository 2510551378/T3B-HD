"""Freeze source-matched tint inputs and execute owned headless D3D11 validation."""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import uuid
from pathlib import Path
import numpy as np
from PIL import Image


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ident(p):return dict(file=str(p.resolve()),sha256=sha(p))
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,r):p.write_text(json.dumps(r,indent=2),encoding='utf-8')
def check(v,why):
    if not v:raise ValueError(why)


def prepare(proof_path,out):
    project=Path(__file__).resolve().parents[1];sys.path.insert(0,str(project.parent/'psp_parse/tools'))
    from analyze_fx_node_time import sidecar
    proof=read(proof_path);check(proof['passed']and proof['matched_GE_primitive_count']==24,'Expected exact GE-matched color inputs')
    def f24(values):return(np.asarray(values,dtype='<u4')<<8).view('<f4').astype(float)
    textures=list(proof['textures'].items());frames=sorted(set(m['GE_sample']for m in proof['matched_primitives']))
    check(frames==[0,1,2],'Current isolated GPU sample pairing')
    data=bytearray(b'T3BPCG1\0'+struct.pack('<4I',480,272,len(frames),len(textures)));texture_rows=[]
    for digest,t in textures:
        path=Path(t['png']['file']);check(sha(path)==t['png']['sha256'],'Original texture PNG changed')
        image=Image.open(path).convert('RGBA');rgba=image.tobytes();check(hashlib.sha256(rgba).hexdigest()==digest,'Original source texture differs')
        data.extend(struct.pack('<2I',*image.size)+rgba);texture_rows.append(dict(width=image.width,height=image.height,RGBA_sha256=digest,source=t))
    draw_rows=[]
    for frame in frames:
        rows=[m for m in proof['matched_primitives']if m['GE_sample']==frame];data.extend(struct.pack('<2I',frame,len(rows)))
        for m in rows:
            r=[0]*256
            for key,value in m['registers'].items():r[int(key,16)]=value
            check(r[0x17]==0 and r[0x50]==1 and r[0xe7]==1 and r[0x24]==0 and r[0xde]==7,'Unsupported source effect depth/light contract')
            check(r[0xdf]==0xa6 and r[0xe1]==0xffffff and r[0xc0]&3==0 and r[0xc9]&7==0 and r[0xc9]&256,'Unsupported source effect blend/texture function')
            check(r[0x22]&1 and r[0xdb]==0xff0006 and(r[0xc2]>>16)&7==0 and r[0x9b]in(0,1),'Unsupported source effect alpha/mip/cull')
            check(r[0x20]==r[0x25]==r[0x28]==r[0xe8]==r[0xe9]==0 and r[0xd2]==3,'Unsupported source effect raster mode')
            check(r[0x15]==r[0xd4]==0 and r[0x16]==r[0xd5]==0x43ddf and r[0xd6]==0 and r[0xd7]==65535,'Source viewport/scissor/depth range differs')
            flags=1|((1-(r[0xe7]&1))<<1)|((r[0x1d]&1)<<2)|(((r[0xc9]>>16)&1)<<3)|((r[0x1f]&1)<<4)|((r[0x24]&1)<<5)|((r[0x1c]&1)<<6)
            flags|=(r[0xc7]&1)<<8|((r[0xc7]>>8)&1)<<9|1024|2048|4096|(r[0x9b]<<14)
            W=np.eye(4);W[:,:3]=f24(m['WORLD_payload']).reshape(4,3);V=np.eye(4);V[:,:3]=f24(m['VIEW_payload']).reshape(4,3);P=f24(m['PROJECTION_payload']).reshape(4,4)
            scale=f24([r[k]for k in (0x42,0x43,0x44)]);center=f24([r[k]for k in (0x45,0x46,0x47)]);offset=np.array([r[k]&65535 for k in (0x4c,0x4d)])/16
            remap=np.diag([scale[0]/240,-scale[1]/136,scale[2]/65535,1]);remap[3,:3]=[(center[0]-offset[0])/240-1,1-(center[1]-offset[1])/136,center[2]/65535]
            matrix=(W@V@P@remap).astype('<f4');fog=W@V[:,2];fog[3]+=f24([r[0xcd]])[0];fog=(fog*f24([r[0xce]])[0]).astype('<f4')
            fog_rgb=[(r[0xcf]>>(8*k))&255 for k in range(3)]+[0]
            texture=next(i for i,(digest,_)in enumerate(textures)if digest==m['texture_RGBA_sha256'])
            data.extend(struct.pack('<3I',texture,flags,(r[0xdc]>>8)&255)+matrix.tobytes()+fog.tobytes()+struct.pack('<4I',*fog_rgb)+struct.pack('<256I',*r))
            op=m['CPU_palette_operation'];d=m['source_color_binding'];vt,n=m['source_primitive']['vtype'],m['source_primitive']['count']
            palette=sidecar(op['source_palette']['raw']);before=sidecar(d['vertices_before']['raw']);after=Path(m['source_primitive']['vertices']['file']).read_bytes()
            check(hashlib.sha256(after).hexdigest()==m['source_primitive']['vertices']['sha256']and after==sidecar(d['vertices_after']['raw']),'GE/source after binding differs')
            data.extend(struct.pack('<4I',vt,n,op['mode'],len(palette))+struct.pack('<8I',*op['source_bits'],*op['parent_bits'])+palette+struct.pack('<%dI'%n,*d['color_indices'])+before+after)
            indices=np.array([index for j in range(n-2)for index in([j+1,j,j+2]if j&1 else[j,j+1,j+2])])
            local=np.array([struct.unpack_from('<3h',after,k*16+8)for k in range(n)],dtype='<f4')/np.float32(32768)
            uv=np.array([struct.unpack_from('<2H',after,k*16)for k in range(n)],dtype='<f4')/np.float32(32768)
            uv=(uv*f24([r[0x48],r[0x49]]).astype('<f4')).astype('<f4')+f24([r[0x4a],r[0x4b]]).astype('<f4')
            colors=np.array([list(after[k*16+4:k*16+8])for k in range(n)],dtype='<f4')/np.float32(255)
            vertex=np.column_stack([local,uv,colors]).astype('<f4')[indices]
            data.extend(struct.pack('<I',len(vertex))+vertex.tobytes())
            draw_rows.append(dict(frame=frame,ordinal=m['subdraw'],matched_primitive=m,flags=flags,vertex_input_sha256=hashlib.sha256(vertex.tobytes()).hexdigest(),
                                  combined_matrix=matrix.tolist(),fog=fog.tolist()))
    binary=out/'original_palette_GPU_inputs.bin';binary.write_bytes(data)
    manifest=dict(passed=True,proof=ident(proof_path),binary=ident(binary),textures=texture_rows,draws=draw_rows,producer=ident(Path(__file__)))
    write(out/'inputs.json',manifest);return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--proof',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);a=p.parse_args()
    project=Path(__file__).resolve().parents[1];out=project/'Validation/fx_palette_gpu_runs'/uuid.uuid4().hex;out.mkdir(parents=True)
    for name in ('ge','runtime','previous'):(out/name).mkdir()
    inputs=prepare(a.proof,out)
    files=[project/'Tools'/n for n in ('ge_effect_palette_gpu.cpp','ge_strip_fx_reference.cpp','ge_depth_reference.cpp','ge_strip_fx.hlsl')]
    files += [project/'Source/T3BRemake/Public'/n for n in ('T3BGEGeometry.h','T3BGELighting.h','T3BGEEffectGeometry.h','T3BGEEffectVertexColor.h')]
    files += [project/'Source/T3BRemake/Private'/n for n in ('T3BGEGeometry.cpp','T3BGEEffectGeometry.cpp','T3BGEEffectVertexColor.cpp')]+[Path(__file__)]
    inventory=[]
    for source in files:
        dest=out/source.name;shutil.copyfile(source,dest);inventory.append(dict(source=str(source.resolve()),**ident(dest)))
    legacy=(out/'ge_strip_fx_reference.cpp').read_text(encoding='utf-8');needle='int main(int argc,char** argv) {';check(legacy.count(needle)==1,'Ambiguous legacy entry adapter')
    adapter=out/'ge_strip_fx_reference_adapter.cpp';adapter.write_text(legacy.replace(needle,'int T3BStripLegacyMain(int argc,char** argv) {'),encoding='utf-8')
    exe=out/'ge_effect_palette_gpu.exe'
    build=[str(a.compiler),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off',str(out/'ge_effect_palette_gpu.cpp'),str(out/'T3BGEGeometry.cpp'),str(out/'T3BGEEffectGeometry.cpp'),str(out/'T3BGEEffectVertexColor.cpp'),'-o',str(exe),'-ld3d11','-ld3dcompiler','-ldxgi','-ldxguid']
    request=dict(schema='owned-original-palette-D3D11-request/v1',sources=inventory,adapter=ident(adapter),adapter_change='Only rename legacy main to T3BStripLegacyMain; GPU implementation unchanged.',
                 inputs=ident(out/'inputs.json'),binary=inputs['binary'],build_command=build,UE_executed=False,PSP_final_pixel_equivalence=False)
    write(out/'request.json',request);process=subprocess.run(build,capture_output=True)
    (out/'build_stdout.log').write_bytes(process.stdout);(out/'build_stderr.log').write_bytes(process.stderr);request['build_exit_code']=process.returncode;write(out/'request.json',request)
    check(process.returncode==0,'Owned GPU build failed: '+str(out));command=[str(exe),str(out/'original_palette_GPU_inputs.bin'),str(out/'ge_strip_fx.hlsl'),str(out)]
    request.update(command=command,executable=ident(exe));write(out/'request.json',request)
    with(out/'stdout.log').open('w',encoding='utf-8')as stdout,(out/'stderr.log').open('w',encoding='utf-8')as stderr:
        process=subprocess.Popen(command,cwd=out,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt'else 0)
        write(out/'started.json',dict(pid=process.pid,command=command));print(json.dumps(dict(run=str(out),pid=process.pid)),flush=True);code=process.wait()
    write(out/'completed.json',dict(pid=process.pid,exit_code=code));check(code==0,'Owned GPU execution failed: '+str(out))
    print(json.dumps(dict(passed=True,run=str(out))))


if __name__=='__main__':main()
