"""Compile and execute owned same-frame scene/production color composition."""
import argparse,hashlib,json,os,shutil,subprocess,uuid
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ident(p):return dict(file=str(p.resolve()),sha256=sha(p))
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.write_text(json.dumps(v,indent=2),encoding='utf-8')
def check(v,s):
    if not v:raise ValueError(s)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('scene','palette-run','compiler'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();project=Path(__file__).resolve().parents[1];out=project/'Validation/fx_scene_gpu_runs'/uuid.uuid4().hex;out.mkdir(parents=True)
    for folder in ('runtime','ge'):(out/folder).mkdir()
    scene=read(a.scene);scene_binary=Path(scene['binary']['file']);check(scene['passed']and sha(scene_binary)==scene['binary']['sha256'],'Scene changed')
    palette_request=read(a.palette_run/'request.json');palette=Path(palette_request['binary']['file']);check(sha(palette)==palette_request['binary']['sha256'],'Palette inputs changed')
    check(read(a.palette_run/'independent_verification.json')['passed'],'Palette GPU reference not passed')
    source_names=['ge_fx_scene_gpu.cpp','ge_effect_palette_gpu.cpp','ge_strip_fx_reference.cpp','ge_depth_reference.cpp','ge_strip_fx.hlsl','run_fx_scene_gpu.py']
    sources=[project/'Tools'/n for n in source_names]
    sources += [project/'Source/T3BRemake/Public'/n for n in ('T3BGEGeometry.h','T3BGELighting.h','T3BGEEffectGeometry.h','T3BGEEffectVertexColor.h')]
    sources += [project/'Source/T3BRemake/Private'/n for n in ('T3BGEGeometry.cpp','T3BGEEffectGeometry.cpp','T3BGEEffectVertexColor.cpp')]
    rows=[]
    for source in sources:
        dest=out/source.name;shutil.copyfile(source,dest);rows.append(dict(source=str(source.resolve()),**ident(dest)))
    adapters=[]
    for source,dest,before,after in [('ge_strip_fx_reference.cpp','ge_strip_fx_reference_adapter.cpp','int main(int argc,char** argv) {','int T3BStripLegacyMain(int argc,char** argv) {'),
                                     ('ge_effect_palette_gpu.cpp','ge_effect_palette_gpu_adapter.cpp','int main(int argc,char** argv){','int T3BPaletteLegacyMain(int argc,char** argv){')]:
        original=(out/source).read_text(encoding='utf-8');check(original.count(before)==1,'Ambiguous entry rename');path=out/dest;path.write_text(original.replace(before,after),encoding='utf-8');adapters.append(dict(source=source,before=before,after=after,**ident(path)))
    exe=out/'ge_fx_scene_gpu.exe';cmd=[str(a.compiler),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off',str(out/'ge_fx_scene_gpu.cpp'),*[str(out/n)for n in ('T3BGEGeometry.cpp','T3BGEEffectGeometry.cpp','T3BGEEffectVertexColor.cpp')],'-o',str(exe),'-ld3d11','-ld3dcompiler','-ldxgi','-ldxguid']
    request=dict(sources=rows,adapters=adapters,scene=ident(a.scene),scene_binary=ident(scene_binary),palette_request=ident(a.palette_run/'request.json'),palette=ident(palette),build_command=cmd,UE_executed=False)
    write(out/'request.json',request);r=subprocess.run(cmd,capture_output=True);(out/'build_stdout.log').write_bytes(r.stdout);(out/'build_stderr.log').write_bytes(r.stderr)
    request['build_exit_code']=r.returncode;write(out/'request.json',request);check(r.returncode==0,'GPU build failed: '+str(out))
    cmd=[str(exe),str(scene_binary),str(palette),str(out/'ge_strip_fx.hlsl'),str(out)];request.update(command=cmd,executable=ident(exe));write(out/'request.json',request)
    with(out/'stdout.log').open('w',encoding='utf-8')as stdout,(out/'stderr.log').open('w',encoding='utf-8')as stderr:
        process=subprocess.Popen(cmd,cwd=out,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt'else 0)
        write(out/'started.json',dict(pid=process.pid,command=cmd));print(json.dumps(dict(run=str(out),pid=process.pid)),flush=True);code=process.wait()
    write(out/'completed.json',dict(pid=process.pid,exit_code=code));check(code==0,'GPU execution failed: '+str(out));print(json.dumps(dict(passed=True,run=str(out))))

if __name__=='__main__':main()
