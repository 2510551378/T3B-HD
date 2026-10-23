"""Verify the exact UE production core and shared pixel helper executed natively."""
import argparse,hashlib,json,struct
from pathlib import Path
import numpy as np
from PIL import Image

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(v,s):
    if not v:raise ValueError(s)
def checked(row):
    p=Path(row['file']);check(sha(p)==row['sha256'],'Evidence changed: '+str(p));return p

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);a=p.parse_args();out=a.run
    check(not(out/'independent_verification.json').exists(),'Never replace a completed proof')
    req=read(out/'request.json');actual=read(out/'actual_gpu_report.json');done=read(out/'completed.json');start=read(out/'started.json')
    for source in req['sources']:checked(source)
    for key in ('scene','palette','baseline','shader','adapter','compiler','probe','executable','rebuilt'):checked(req[key])
    check(req['probe_build_exit']==req['gpu_build_exit']==done['exit_code']==0 and actual['pid']==start['pid']==done['pid'],'Build or actual process identity differs')
    check(Path(req['scene']['file']).read_bytes()==Path(req['rebuilt']['file']).read_bytes(),'Production core altered scene data')
    stats=dict(frames=3,atlases=79,draws=838,vertices=109299,color_draws=24)
    check(req['probe_result']==stats==json.loads((out/'probe_run_stdout.log').read_text(encoding='utf-8')),'Actual production coverage differs')
    names={'truncated_scene','trailing_scene','truncated_palette','unsupported_scene_flags','nonfinite_vertex','wrong_effect_projection','wrong_source_RGBA','wrong_effect_CLUT_texture'}
    check({c['case']for c in req['negative_cases']}==names and all(c['exit_code']!=0 for c in req['negative_cases']),'Missing bad-binding gate')
    for name in names:check(not(out/(name+'_output.bin')).exists()and(out/(name+'_stderr.log')).stat().st_size>0,'Rejected binding published an output')
    adapter=(out/'ge_strip_fx_reference.cpp').read_text(encoding='utf-8').replace(req['adapter_before'],req['adapter_after'])
    check(adapter==Path(req['adapter']['file']).read_text(encoding='utf-8'),'Native adapter modifies renderer')
    original=(out/'ge_strip_fx.hlsl').read_text(encoding='utf-8');shader=Path(req['shader']['file']).read_text(encoding='utf-8');helper=(out/'T3BGESceneCommon.ush').read_text(encoding='utf-8')
    check(shader.startswith(original[:original.index('uint QuantizeFog(')]+helper) and shader.count(helper)==1,'Shared production shader was rewritten')
    usf=(out/'T3BGEScene.usf').read_text(encoding='utf-8');check('#include "/T3B/Private/T3BGESceneCommon.ush"'in usf and 'T3BSceneShade(Atlas.Sample' in usf,'UE shader does not use tested pixel helper')
    baseline_path=Path(req['baseline']['file']);baseline=read(baseline_path);base=baseline_path.parent;check(baseline['passed'] and baseline['source_draws']==838,'Baseline scope differs')
    previous_request=read(checked(baseline['request']));check(req['scene']==previous_request['scene_binary'] and req['palette']==previous_request['palette'],'Bridge changed verified input identity')
    previous_sources={row['source']:row for row in previous_request['sources']}
    for row in req['sources']:
        if row['source'] in previous_sources:check(row['sha256']==previous_sources[row['source']]['sha256'],'Shared preexisting renderer/core changed')
    source=read(checked(previous_request['scene']));images=[];vertices=0
    check(len(actual['captures'])==3,'Unexpected GPU capture scope')
    for frame in source['frames']:
        sample=frame['sample'];prefix='sample_%d_runtime'%sample
        stream=out/('sample_%d.clip_uv_color_fog_f32'%sample);previous=base/'runtime'/('sample_%d.clip_uv_color_fog_f32'%sample)
        check(stream.read_bytes()==previous.read_bytes(),'Production parser/evaluator VS output differs from verified GE scene')
        n=sum(d['vertices']for d in frame['draws']);check(stream.stat().st_size==n*44,'GPU VS extent differs');vertices+=n
        for suffix in ('.rgba','.owner_u32','.depth_stencil_u32'):
            check((out/(prefix+suffix)).read_bytes()==(base/(prefix+suffix)).read_bytes(),'Shared UE shader/production path GPU result differs: '+prefix+suffix)
        rgba=np.fromfile(out/(prefix+'.rgba'),dtype='u1').reshape(272,480,4);Image.fromarray(rgba).save(out/(prefix+'.png'));images.append(prefix+'.png')
    for i in range(79):check((out/('atlas_%d_actual.rgba'%i)).read_bytes()==(base/('atlas_%d_actual.rgba'%i)).read_bytes(),'Actual original atlas GPU upload differs')
    check(vertices==109299,'Incomplete GPU production scope')
    proof=dict(schema='UE-scene-production-core-native-bridge/v1',passed=True,actual_pid=actual['pid'],adapter=actual['adapter'],
               request=dict(file=str((out/'request.json').resolve()),sha256=sha(out/'request.json')),production=stats,
               native_GPU_captures=3,shared_shader_framebuffers_equal=True,production_scene_bytes_equal=True,negative_cases=8,
               UE_module_built=False,UE_RHI_callbacks_executed=False,default_M1_replaced=False,
               limits=['Production engine-independent scene core and shared UE pixel helper were compiled/executed in native D3D11.',
                       'New UE actor, shader parameter bindings, RDG callback and RHI states are source integration only; formal UE build/runtime remains unverified.',
                       'The new UE entry is opt-in source-camera calibration using separate source depth. It is not independent PC camera/gameplay or original authored timing.'])
    (out/'independent_verification.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
    html='<!doctype html><meta charset="utf-8"><title>UE生产core原场景桥接验证</title><style>body{background:#171a1d;color:#eee;font:16px system-ui;max-width:1000px;margin:30px auto}img{width:960px;max-width:100%;image-rendering:pixelated}</style><h1>UE生产core与共享shader：实际native验证</h1><p>当前为独立D3D11：UE actor/RDG回调尚未正式编译运行。3帧原场景，838draw／79原贴图，颜色core与UE共享pixel helper实际执行，全部结果同此前GE输入基线。</p>'
    html+=''.join('<p>原记录%d</p><img src="%s">'%(i+1,name)for i,name in enumerate(images));(out/'PREVIEW.html').write_text(html,encoding='utf-8')
    print(json.dumps(dict(passed=True,production=stats,GPU_captures=3,rejected_bindings=8,UE_callbacks_executed=False)))

if __name__=='__main__':main()
