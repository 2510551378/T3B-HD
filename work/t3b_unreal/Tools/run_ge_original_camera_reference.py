"""Run original-camera Aya+weapon geometry with the project world shader body."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def write(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiler',type=Path,required=True);p.add_argument('--cameras',type=Path,required=True);a=p.parse_args()
    project=Path(__file__).resolve().parents[1];out=project/'Validation/ge_original_camera_runs'/uuid.uuid4().hex
    out.mkdir(parents=True);camera=read(a.cameras)
    if not camera['passed'] or sha(Path(camera['binary']['file']))!=camera['binary']['sha256']:
        raise ValueError('Camera evidence changed')
    bundle=Path(camera['geometry_bundle']['file'])
    if sha(bundle)!=camera['geometry_bundle']['sha256']:raise ValueError('Geometry changed')
    sources=[project/'Tools/ge_depth_reference.cpp',project/'Tools/ge_original_camera_reference.cpp',
             project/'Source/T3BRemake/Public/T3BGEGeometry.h',project/'Source/T3BRemake/Private/T3BGEGeometry.cpp',
             project/'Shaders/Private/T3BGEOrdered.usf',project/'Shaders/Private/T3BGECommon.ush']
    frozen=[]
    for s in sources:
        copy=out/s.name;copy.write_bytes(s.read_bytes());frozen.append(dict(source=str(s),file=str(copy),sha256=sha(copy)))
    text=(out/'T3BGEOrdered.usf').read_bytes()
    platform=b'#include "/Engine/Public/Platform.ush"';shared=b'#include "/T3B/Private/T3BGECommon.ush"'
    if text.count(platform)!=1 or text.count(shared)!=1:raise ValueError('Unexpected shader includes')
    shader=out/'executed_shader.hlsl';shader.write_bytes(text.replace(platform,b'// Direct FXC probe; no Engine Platform symbols used.').replace(shared,(out/'T3BGECommon.ush').read_bytes()))
    exe=out/'ge_original_camera_reference.exe'
    cmd=[str(a.compiler),'-std=c++17','-O2','-Wall','-Wextra','-Werror',str(out/'ge_original_camera_reference.cpp'),
         str(out/'T3BGEGeometry.cpp'),'-o',str(exe),'-ld3d11','-ld3dcompiler','-ldxgi','-ldxguid']
    request=dict(schema='t3b-original-camera-native-GPU-request/v1',sources=frozen,
        shader=dict(file=str(shader),sha256=sha(shader)),
        cameras=dict(file=str(a.cameras.resolve()),sha256=sha(a.cameras)),camera_binary=camera['binary'],
        geometry_bundle=camera['geometry_bundle'],build_command=cmd,UE_executed=False)
    write(out/'request.json',request)
    build=subprocess.run(cmd,capture_output=True,encoding='utf-8',errors='replace')
    (out/'build_stdout.log').write_text(build.stdout,encoding='utf-8');(out/'build_stderr.log').write_text(build.stderr,encoding='utf-8')
    request['build_exit_code']=build.returncode;write(out/'request.json',request)
    if build.returncode:raise RuntimeError(f'Native build failed: {out}')
    command=[str(exe),str(bundle),str(shader),camera['binary']['file'],str(out)]
    request.update(executable_sha256=sha(exe),run_command=command);write(out/'request.json',request)
    with (out/'stdout.log').open('w',encoding='utf-8') as stdout,(out/'stderr.log').open('w',encoding='utf-8') as stderr:
        process=subprocess.Popen(command,cwd=out,stdout=stdout,stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt'else 0)
        write(out/'started.json',dict(pid=process.pid,command=command));code=process.wait()
    write(out/'completed.json',dict(pid=process.pid,exit_code=code))
    print(json.dumps(dict(run=str(out),pid=process.pid,exit_code=code),ensure_ascii=False))
    if code:raise RuntimeError(f'GPU run failed: {out}')


if __name__=='__main__':main()
