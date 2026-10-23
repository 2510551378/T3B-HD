"""Freeze UE production scene core/shared shader, execute loader and native GPU."""
import argparse,hashlib,json,os,shutil,struct,subprocess,uuid
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ident(p):return dict(file=str(p.resolve()),sha256=sha(p))
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.write_text(json.dumps(v,indent=2),encoding='utf-8')
def check(v,s):
    if not v:raise ValueError(s)
def checked(i):
    p=Path(i['file']);check(sha(p)==i['sha256'],'Input changed');return p
def execute(cmd,out,label):
    r=subprocess.run(cmd,capture_output=True);(out/(label+'_stdout.log')).write_bytes(r.stdout);(out/(label+'_stderr.log')).write_bytes(r.stderr);return r

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',type=Path,required=True);a=p.parse_args()
    project=Path(__file__).resolve().parents[1];root=project.parent/'psp_parse';out=project/'Validation/scene_color_bridge_runs'/uuid.uuid4().hex;out.mkdir(parents=True)
    baseline=project/'Validation/fx_scene_gpu_runs/3765b564f94b4d3f904b06290044d764';bp=read(baseline/'independent_verification.json');check(bp['passed'],'Baseline not verified')
    base_req=read(checked(bp['request']));scene=checked(base_req['scene_binary']);palette=checked(base_req['palette'])
    files=[project/'Tools'/n for n in('ge_scene_runtime_gpu.cpp','ge_scene_probe.cpp','ge_strip_fx_reference.cpp','ge_depth_reference.cpp','ge_strip_fx.hlsl','run_scene_color_bridge.py')]
    files += [project/'Source/T3BRemake/Public'/n for n in('T3BGEGeometry.h','T3BGELighting.h','T3BGEScene.h','T3BGEEffectGeometry.h','T3BGEEffectVertexColor.h','T3BGESceneReplayActor.h')]
    files += [project/'Source/T3BRemake/Private'/n for n in('T3BGEGeometry.cpp','T3BGEScene.cpp','T3BGEEffectGeometry.cpp','T3BGEEffectVertexColor.cpp','T3BGESceneReplayActor.cpp','T3BGESceneViewExtension.h','T3BGESceneViewExtension.cpp')]
    files += [project/'Shaders/Private'/n for n in('T3BGEScene.usf','T3BGESceneCommon.ush')]
    rows=[]
    for source in files:
        dest=out/source.name;shutil.copyfile(source,dest);rows.append(dict(source=str(source),**ident(dest)))
    original=(out/'ge_strip_fx_reference.cpp').read_text(encoding='utf-8');before='int main(int argc,char** argv) {';after='int T3BStripLegacyMain(int argc,char** argv) {';check(original.count(before)==1,'Entry ambiguity')
    adapter=out/'ge_strip_fx_reference_adapter.cpp';adapter.write_text(original.replace(before,after),encoding='utf-8')
    shader=(out/'ge_strip_fx.hlsl').read_text(encoding='utf-8');split=shader.index('uint QuantizeFog(')
    # The unchanged legacy D3DCompile adapter has no include handler. Inline the
    # exact retained helper text, rather than rewriting its arithmetic.
    wrapper=shader[:split]+(out/'T3BGESceneCommon.ush').read_text(encoding='utf-8')+'''
struct Pixel {float4 Color:SV_Target0;uint Owner:SV_Target1;};
Pixel PSMain(Interpolated V){Pixel O;O.Color=T3BSceneShade(Atlas.Sample(AtlasSampler,V.UV),V.Color,V.Fog,Control.w,FogRGB.rgb);O.Owner=Control.x;return O;}
'''
    shader_path=out/'scene_shared_pixel.hlsl';shader_path.write_text(wrapper,encoding='utf-8')
    request=dict(sources=rows,scene=ident(scene),palette=ident(palette),baseline=ident(baseline/'independent_verification.json'),
                 adapter=ident(adapter),adapter_before=before,adapter_after=after,shader=ident(shader_path),compiler=ident(a.compiler),
                 UE_module_built=False,UE_callbacks_executed=False,shared_pixel_shader_tested_in_native_D3D11=True)
    write(out/'request.json',request)
    core=['T3BGEScene.cpp','T3BGEEffectVertexColor.cpp','T3BGEEffectGeometry.cpp']
    common=[str(a.compiler),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-I'+str(out)]
    probe=out/'ge_scene_probe.exe';cmd=common+[str(out/'ge_scene_probe.cpp')]+[str(out/n)for n in core]+['-o',str(probe)]
    result=execute(cmd,out,'probe_build');request['probe_build_command']=cmd;request['probe_build_exit']=result.returncode;write(out/'request.json',request);check(result.returncode==0,'Production core build failed: '+str(out))
    rebuilt=out/'production_rebuilt_scene.bin';cmd=[str(probe),str(scene),str(palette),str(rebuilt)];result=execute(cmd,out,'probe_run');check(result.returncode==0,'Production reader/evaluator rejected verified data')
    check(rebuilt.read_bytes()==scene.read_bytes(),'Production reader/evaluator changes scene data');stats=json.loads(result.stdout);check(stats==dict(frames=3,atlases=79,draws=838,vertices=109299,color_draws=24),'Production source scope differs')
    raw_scene=scene.read_bytes();raw_palette=palette.read_bytes();scene_at=24;palette_at=24
    for _ in range(struct.unpack_from('<I',raw_scene,20)[0]):w,h=struct.unpack_from('<2I',raw_scene,scene_at);scene_at+=8+w*h*4
    scene_at+=8
    for _ in range(struct.unpack_from('<I',raw_palette,20)[0]):w,h=struct.unpack_from('<2I',raw_palette,palette_at);palette_at+=8+w*h*4
    palette_at+=8
    cases=[]
    def reject(label,changed_scene=None,changed_palette=None):
        s=scene;p=palette
        if changed_scene is not None:s=out/(label+'_scene.bin');s.write_bytes(changed_scene)
        if changed_palette is not None:p=out/(label+'_palette.bin');p.write_bytes(changed_palette)
        output=out/(label+'_output.bin');r=execute([str(probe),str(s),str(p),str(output)],out,label)
        check(r.returncode!=0 and not output.exists(),'Bad source binding accepted: '+label);cases.append(dict(case=label,exit_code=r.returncode,error=r.stderr.decode('utf-8').strip()))
    reject('truncated_scene',raw_scene[:-1]);reject('trailing_scene',raw_scene+b'\0');reject('truncated_palette',changed_palette=raw_palette[:-1])
    for label,offset,value in [('unsupported_scene_flags',scene_at+8,128),('nonfinite_vertex',scene_at+116,0x7fc00000)]:
        bad=bytearray(raw_scene);struct.pack_into('<I',bad,offset,value);reject(label,bad)
    for label,offset in [('wrong_effect_projection',palette_at+12),('wrong_source_RGBA',palette_at+1148)]:
        bad=bytearray(raw_palette);value=struct.unpack_from('<f',bad,offset)[0];struct.pack_into('<f',bad,offset,value+1);reject(label,changed_palette=bad)
    bad=bytearray(raw_palette);bad[32]^=1;reject('wrong_effect_CLUT_texture',changed_palette=bad)
    gpu=out/'ge_scene_runtime_gpu.exe';cmd=common+[str(out/'ge_scene_runtime_gpu.cpp'),str(out/'T3BGEGeometry.cpp')]+[str(out/n)for n in core]+['-o',str(gpu),'-ld3d11','-ld3dcompiler','-ldxgi','-ldxguid']
    r=execute(cmd,out,'gpu_build');request.update(probe=ident(probe),probe_command=[str(probe),str(scene),str(palette),str(rebuilt)],probe_result=stats,negative_cases=cases,gpu_build_command=cmd,gpu_build_exit=r.returncode);write(out/'request.json',request);check(r.returncode==0,'Native bridge build failed: '+str(out))
    cmd=[str(gpu),str(scene),str(palette),str(shader_path),str(out)];request.update(executable=ident(gpu),command=cmd,rebuilt=ident(rebuilt));write(out/'request.json',request)
    with(out/'stdout.log').open('w',encoding='utf-8')as stdout,(out/'stderr.log').open('w',encoding='utf-8')as stderr:
        process=subprocess.Popen(cmd,cwd=out,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt'else 0)
        write(out/'started.json',dict(pid=process.pid,command=cmd));print(json.dumps(dict(run=str(out),pid=process.pid)),flush=True);code=process.wait()
    write(out/'completed.json',dict(pid=process.pid,exit_code=code));check(code==0,'Native bridge GPU failed: '+str(out));print(json.dumps(dict(passed=True,run=str(out))))

if __name__=='__main__':main()
