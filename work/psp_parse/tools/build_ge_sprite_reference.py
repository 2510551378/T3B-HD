"""Compile unchanged pinned transform/rectangle functions with test-only adapters."""
import argparse,hashlib,json,shutil,subprocess,urllib.request
from pathlib import Path


def check(v,msg):
    if not v:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def identity(p):return dict(file=str(p.resolve()),sha256=sha(p))
def function(source,signature):
    begin=source.index(signature);at=source.index('{',begin);depth=1;end=at+1
    while depth:
        if source[end]=='{':depth+=1
        if source[end]=='}':depth-=1
        end+=1
    return source[begin:end]+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('inputs','compiler','out'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();check(not a.out.exists(),'Never replace upstream reference evidence');a.out.mkdir(parents=True)
    root=Path(__file__).resolve().parents[1];official=a.out/'official_ppsspp_v1.20.4';official.mkdir()
    local={'TransformUnit.cpp':root/'out/AYA_CULL_ORIENTATION_20261020/official_ppsspp_v1.20.4/GPU_Software_TransformUnit.cpp',
        'Rasterizer.cpp':root/'out/ORIGINAL_SCENE_GE_REPLAY_20261021/official_ppsspp_v1.20.4/Rasterizer.cpp'}
    provenance=[]
    for name,path in local.items():
        target=official/name;target.write_bytes(path.read_bytes());provenance.append(dict(**identity(target),local_source=identity(path)))
    url='https://raw.githubusercontent.com/hrydgard/ppsspp/v1.20.4/GPU/Software/Clipper.cpp'
    retained=root/'out/GE_RECT_SPRITES_20261021/reference_v1/official_ppsspp_v1.20.4/Clipper.cpp'
    if retained.is_file():(official/'Clipper.cpp').write_bytes(retained.read_bytes())
    else:
        with urllib.request.urlopen(url,timeout=30)as response:(official/'Clipper.cpp').write_bytes(response.read())
    provenance.append(dict(**identity(official/'Clipper.cpp'),url=url))
    # These are prior fixed upstream headers plus explicit framework/storage shims.
    include_source=root/'out/OTHER_ACTOR_GE_PAIRED_20261021/comparison_v1/include';inc=a.out/'include';shutil.copytree(include_source,inc)
    transform=(official/'TransformUnit.cpp').read_text(encoding='utf-8');raster=(official/'Rasterizer.cpp').read_text(encoding='utf-8');clip=(official/'Clipper.cpp').read_text(encoding='utf-8')
    snippets={
        'upstream_transform.inc':function(transform,'template <bool depthClamp, bool alwaysCheckRange>')+
            function(transform,'void ComputeTransformState(')+function(transform,'static inline __m128 Dot43SSE4(')+function(transform,'static inline float Dot43('),
        'upstream_rectangle.inc':function(raster,'static inline u8 ClampFogDepth(')+function(raster,'void DrawRectangle('),
        'upstream_process_rect.inc':function(clip,'static inline bool CheckOutsideZ(')+function(clip,'void ProcessRect('),
    }
    for name,code in snippets.items():(a.out/name).write_text('// Verbatim functions from retained GPL-2.0 PPSSPP sources; test-only adapters in driver.cpp.\n'+code,encoding='utf-8')
    driver=a.out/'driver.cpp';driver.write_bytes((root/'tools/sprite_reference/driver.cpp').read_bytes());exe=a.out/'sprite_reference.exe'
    cmd=[str(a.compiler),'-std=c++17','-O2','-Wall','-Wextra','-Wno-unused-parameter','-msse4.1','-ffp-contract=off','-I'+str(inc),str(driver),'-o',str(exe)]
    build=subprocess.run(cmd,capture_output=True,encoding='utf-8',errors='replace')
    (a.out/'build_stdout.log').write_text(build.stdout,encoding='utf-8');(a.out/'build_stderr.log').write_text(build.stderr,encoding='utf-8')
    (a.out/'build_command.json').write_text(json.dumps(cmd,indent=2),encoding='utf-8');check(build.returncode==0,'Upstream sprite reference compilation failed')
    manifest=read(a.inputs);binary=Path(manifest['binary']['file']);check(sha(binary)==manifest['binary']['sha256'],'Original source endpoints changed')
    output=[a.out/'endpoints.bin',a.out/'parts.bin',a.out/'candidate_pixels.bin'];command=[str(exe),str(binary),*map(str,output)]
    run=subprocess.run(command,capture_output=True,encoding='utf-8',errors='replace')
    (a.out/'stdout.log').write_text(run.stdout,encoding='utf-8');(a.out/'stderr.log').write_text(run.stderr,encoding='utf-8')
    check(run.returncode==0,'Actual upstream sprite reference execution failed')
    report=dict(schema='pinned-PPSSPP-sprite-coverage-reference/v1',passed=True,inputs=identity(a.inputs),input_binary=identity(binary),
        command=command,build_command=cmd,executable_sha256=sha(exe),compiler_sha256=sha(a.compiler),build_exit_code=build.returncode,exit_code=run.returncode,
        sources=provenance,generated_functions=[identity(a.out/name)for name in snippets],driver=identity(driver),compatibility_headers=[identity(f)for f in sorted(inc.rglob('*'))if f.is_file()],
        outputs={k:identity(v)for k,v in zip(('endpoints','parts','candidate_pixels'),output)},result=json.loads(run.stdout),
        texture_sampling_performed=False,depth_tests_performed=False,original_hardware_pixels_verified=False,
        scope='Unmodified PPSSPP v1.20.4 transform-state math, clipping, fog splitting and rectangle coverage/UV with explicit recording and state adapters.',
        limits=['Candidate pixels precede original texture/alpha/depth/blend; they are not complete source game pixels.',
                'Full-frame scissor bins are used; through/lighting/texture projection paths reject; only retained VTYPE119 source path.'])
    (a.out/'reference.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,**report['result'])))


if __name__=='__main__':main()
