"""Freeze and execute an owned D3D11 per-draw source-state reference."""
import argparse,hashlib,json,os,subprocess,uuid
from pathlib import Path


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--sprite-controls',type=Path);a=p.parse_args()
    project=Path(__file__).resolve().parents[1];out=project/'Validation/ge_sprite_runs'/uuid.uuid4().hex;out.mkdir(parents=True)
    inputs=read(a.inputs);binary=Path(inputs['binary']['file'])
    if not inputs['passed']or sha(binary)!=inputs['binary']['sha256']:raise ValueError('Source scene input changed')
    files=[project/'Tools/ge_sprite_reference.cpp',project/'Tools/ge_depth_reference.cpp',project/'Tools/ge_sprite.hlsl',
           project/'Source/T3BRemake/Public/T3BGEGeometry.h',project/'Source/T3BRemake/Private/T3BGEGeometry.cpp']
    rows=[]
    for f in files:
        copy=out/f.name;copy.write_bytes(f.read_bytes());rows.append(dict(source=str(f),file=str(copy),sha256=sha(copy)))
    exe=out/'ge_sprite_reference.exe'
    command=[str(a.compiler),'-std=c++17','-O2','-Wall','-Wextra','-Werror',str(out/'ge_sprite_reference.cpp'),str(out/'T3BGEGeometry.cpp'),
             '-o',str(exe),'-ld3d11','-ld3dcompiler','-ldxgi','-ldxguid']
    request=dict(schema='t3b-observed-per-draw-GPU-request/v1',sources=rows,inputs=dict(file=str(a.inputs.resolve()),sha256=sha(a.inputs)),
        binary=inputs['binary'],build_command=command,UE_executed=False,PSP_fixed_point_equivalence=False)
    write(out/'request.json',request);result=subprocess.run(command,capture_output=True,encoding='utf-8',errors='replace')
    (out/'build_stdout.log').write_text(result.stdout,encoding='utf-8');(out/'build_stderr.log').write_text(result.stderr,encoding='utf-8')
    request['build_exit_code']=result.returncode;write(out/'request.json',request)
    if result.returncode:raise RuntimeError(f'Native compilation failed: {out}')
    args=[str(exe),str(binary),str(out/'ge_sprite.hlsl'),str(out)]
    if a.sprite_controls:
        control=read(a.sprite_controls);control_binary=Path(control['controls']['file'])
        if not control['passed']or not control['synthetic']or sha(control_binary)!=control['controls']['sha256']:raise ValueError('Unverified sprite contract controls')
        args.append(str(control_binary));request.update(sprite_controls=dict(file=str(a.sprite_controls.resolve()),sha256=sha(a.sprite_controls)),control_binary=control['controls'])
    request.update(executable_sha256=sha(exe),command=args);write(out/'request.json',request)
    with (out/'stdout.log').open('w',encoding='utf-8')as stdout,(out/'stderr.log').open('w',encoding='utf-8')as stderr:
        process=subprocess.Popen(args,cwd=out,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt'else 0)
        write(out/'started.json',dict(pid=process.pid,command=args));print(json.dumps(dict(run=str(out),pid=process.pid)),flush=True);code=process.wait()
    write(out/'completed.json',dict(pid=process.pid,exit_code=code))
    if code:raise RuntimeError(f'Owned GPU process failed: {out}')
    print(json.dumps(dict(passed=True,run=str(out))))


if __name__=='__main__':main()
