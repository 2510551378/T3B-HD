"""Retain/compile/run an owned D3D11 GE depth-write intervention experiment."""
import argparse,hashlib,json,os,struct,subprocess,uuid
from pathlib import Path
import numpy as np
from PIL import Image


def check(ok,reason):
    if not ok:raise ValueError(reason)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def json_file(p):return json.loads(p.read_text(encoding='utf-8'))


def read_proof(path,manifest):
    proof=json_file(path);check(proof['passed']and proof['input_sha256']==manifest['binary']['sha256'],'Unverified production inputs')
    for key in ('runtime_output','runtime_uv'):
        check(sha(Path(proof[key]['file']))==proof[key]['sha256'],'Runtime output changed')
    for row in proof['sources']:check(sha(Path(row['file']))==row['sha256'],'Evaluated production source changed')
    ref=json_file(Path(proof['comparison']['file']));official=Path(proof['comparison']['file']).parent/'official_outputs.bin'
    check(sha(official)==ref['official_output_sha256']and official.read_bytes()==Path(proof['runtime_output']['file']).read_bytes(),'Independent software output mismatch')
    return Path(proof['runtime_output']['file']).read_bytes(),Path(proof['runtime_uv']['file']).read_bytes()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',type=Path,required=True);a=p.parse_args()
    project=Path(__file__).resolve().parents[1];root=project.parent/'psp_parse';run=uuid.uuid4().hex
    out=project/'Validation/ge_depth_reference_runs'/run;out.mkdir(parents=True)
    wm_path=root/'out/WEAPON_GE_PAIRED_20261020/inputs_v1/inputs.json';wm=json_file(wm_path)
    bm_path=Path(wm['paired_body_input']['file']);check(sha(bm_path)==wm['paired_body_input']['sha256'],'Body pairing changed');bm=json_file(bm_path)
    bp=root/'out/AYA_GE_SAMPLE_SERIES_20261020/runtime_v1/verification.json';wp=root/'out/WEAPON_GE_PAIRED_20261020/runtime_v1/verification.json'
    bd,bu=read_proof(bp,bm);wd,wu=read_proof(wp,wm)
    body_mat=json_file(root/'out/AYA_NATIVE_GLTF_20261020/raw/input_materials.json')['materials'][0]
    textures=[Path(body_mat['png']),Path(next(iter(wm['materials'].values()))['png'])]
    units=json_file(root/'out/AYA_NATIVE_GLTF_20261020/aya_native.gltf')['nodes'][0]['scale'][0]
    dtype=np.dtype([('position','<f4',3),('normal','<f4',3),('color','u1',4),('secondary','u1',3),('pad','u1')])
    sources=[np.frombuffer(bd,dtype=dtype),np.frombuffer(wd,dtype=dtype)]
    uv=[np.frombuffer(bu,dtype='<f4').reshape(-1,2),np.frombuffer(wu,dtype='<f4').reshape(-1,2)]
    first=wm['frames'][0]['paired_body_first_vertex'];points=sources[0][first:first+3456]['position'].astype(np.float64)
    origin=np.array([(points[:,0].min()+points[:,0].max())/2,points[:,1].min(),(points[:,2].min()+points[:,2].max())/2])
    raw_sources=[Path(bm['binary']['file']).read_bytes(),Path(wm['binary']['file']).read_bytes()]
    bundle=out/'original_calibration_inputs.bin';frames=[];texture_rows=[]
    with bundle.open('wb')as f:
        f.write(b'T3BGPU1\0'+struct.pack('<4I',512,768,12,2))
        for i,path in enumerate(textures):
            im=Image.open(path).convert('RGBA');rgba=im.tobytes();f.write(struct.pack('<2I',*im.size));f.write(rgba)
            texture_rows.append(dict(index=i,source=str(path),sha256=sha(path),width=im.width,height=im.height,rgba_sha256=hashlib.sha256(rgba).hexdigest()))
        for frame in wm['frames']:
            bf=bm['frames'][frame['body_frame_index']];draws=[(0,d)for d in bm['draws'][bf['first_draw']:bf['first_draw']+106]]
            draws.append((1,wm['draws'][frame['first_draw']]))
            draws.sort(key=lambda x:(x[1]['register_record'],x[1]['register_word']))
            f.write(struct.pack('<2I',frame['sample'],len(draws)));entries=[]
            for ordinal,(actor,d)in enumerate(draws):
                regs=struct.unpack_from('<256I',raw_sources[actor],d['binary_byte_offset'])
                check(regs[0x21]==regs[0x22]==regs[0x23]==regs[0x1d]==1 and regs[0x9b]==0 and regs[0xe7]==0
                      and regs[0xde]==7 and regs[0xdf]==0x32 and regs[0xdb]==0xff0006 and regs[0xc9]==0x10100,
                      'Original source alpha/depth/cull/texture contract outside this experiment')
                check(regs[0xe8]==regs[0xe9]==regs[0x24]==0,'Original color/stencil contract differs')
                n=d['vertex_count'];start=d['first_output_vertex'];src=sources[actor][start:start+n]
                check(not np.any(src['secondary']),'Secondary specular requires another shader')
                vertex=np.empty((n,9),dtype='<f4')
                vertex[:,:3]=((src['position'].astype(np.float64)-origin)*units*100)[:,[0,2,1]]
                vertex[:,3:5]=uv[actor][start:start+n];vertex[:,5:9]=src['color'].astype(np.float64)/255
                offset=f.tell();f.write(struct.pack('<3I',actor,ordinal,n));f.write(vertex.tobytes())
                entries.append(dict(owner_id=ordinal+1,actor='body'if actor==0 else'weapon',packet=d['packet'],vertices=n,
                                     binary_byte_offset=offset,vertex_sha256=hashlib.sha256(vertex.tobytes()).hexdigest(),
                                     source_register_record=d['register_record'],source_register_word=d['register_word']))
            frames.append(dict(sample=frame['sample'],capture=frame['capture'],draws=entries))
    cpp=out/'ge_depth_reference_executed.cpp';shader=out/'ge_depth_reference_executed.hlsl'
    cpp.write_bytes((project/'Tools/ge_depth_reference.cpp').read_bytes())
    template=(project/'Tools/ge_depth_reference.hlsl').read_bytes();common=(project/'Shaders/Private/T3BGECommon.ush').read_bytes()
    marker=b'#include "/T3B/Private/T3BGECommon.ush"';check(template.count(marker)==1,'Missing shared UE/native shader marker')
    shader.write_bytes(template.replace(marker,common))
    (out/'ge_depth_reference_template.hlsl').write_bytes(template);(out/'T3BGECommon.ush').write_bytes(common)
    core=out/'T3BGEGeometry.cpp';core.write_bytes((project/'Source/T3BRemake/Private/T3BGEGeometry.cpp').read_bytes())
    header=out/'T3BGEGeometry.h';header.write_bytes((project/'Source/T3BRemake/Public/T3BGEGeometry.h').read_bytes())
    exe=out/'ge_depth_reference.exe';cmd=[str(a.compiler),'-std=c++17','-O2','-Wall','-Wextra','-Werror',str(cpp),str(core),'-o',str(exe),'-ld3d11','-ld3dcompiler','-ldxgi','-ldxguid']
    build=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (out/'build_stdout.log').write_text(build.stdout,encoding='utf-8');(out/'build_stderr.log').write_text(build.stderr,encoding='utf-8')
    request=dict(schema='ge-original-depth-gpu-experiment-request/v1',run_id=run,build_command=cmd,build_exit_code=build.returncode,
                  sources=[dict(file=str(f),sha256=sha(f))for f in(cpp,shader,core,header,out/'ge_depth_reference_template.hlsl',out/'T3BGECommon.ush')],
                  body_input=dict(file=str(bm_path),sha256=sha(bm_path)),weapon_input=dict(file=str(wm_path),sha256=sha(wm_path)),
                  runtime_proofs=[dict(file=str(bp),sha256=sha(bp)),dict(file=str(wp),sha256=sha(wp))],
                  bundle=dict(file=str(bundle),sha256=sha(bundle)),textures=texture_rows,frames=frames,
                  fixed_shared_PSP_world_origin=origin.tolist(),metres_per_PSP_world_unit=units,
                  original_camera=False,original_depth_quantization=False,original_fog=False,
                  target='Controlled original-geometry alpha-blend/depth-write GPU experiment; not full PSP pixel equivalence or a UE module.')
    (out/'request.json').write_text(json.dumps(request,indent=2)+'\n',encoding='utf-8')
    check(build.returncode==0,'Native GPU probe build failed; preserved '+str(out))
    run_cmd=[str(exe),str(bundle),str(shader),str(out)];request.update(executable_sha256=sha(exe),run_command=run_cmd)
    (out/'request.json').write_text(json.dumps(request,indent=2)+'\n',encoding='utf-8')
    with(out/'stdout.log').open('wb')as stdout,(out/'stderr.log').open('wb')as stderr:
        process=subprocess.Popen(run_cmd,cwd=out,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt'else 0)
        (out/'process_started.json').write_text(json.dumps(dict(pid=process.pid,run_id=run))+'\n',encoding='utf-8')
        print(json.dumps(dict(pid=process.pid,run_id=run,folder=str(out))),flush=True);code=process.wait()
    (out/'process_completed.json').write_text(json.dumps(dict(pid=process.pid,exit_code=code))+'\n',encoding='utf-8')
    check(code==0,'Actual GPU probe failed; preserved '+str(out))
    actual=json_file(out/'actual_gpu_report.json');check(actual['passed']and actual['pid']==process.pid,'Actual GPU process identity differs')
    print(json.dumps(dict(passed=True,report=str(out/'actual_gpu_report.json'))),flush=True)


if __name__=='__main__':main()
