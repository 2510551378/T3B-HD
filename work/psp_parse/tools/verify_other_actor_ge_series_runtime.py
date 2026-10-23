"""Compile production actor replay and compare with pinned upstream arithmetic."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path


def check(v,msg):
    if not v:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def identity(p):return dict(file=str(p.resolve()),sha256=sha(p))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('inputs','comparison','compiler','out'):p.add_argument('--'+k,required=True,type=Path)
    a=p.parse_args();check(not a.out.exists(),'Never replace actor runtime proof');a.out.mkdir(parents=True)
    m=read(a.inputs);c=read(a.comparison);binary=Path(m['binary']['file']);official=a.comparison.parent/'official_outputs.bin'
    check(m['passed']and c['passed']and m['draw_count']==336 and m['total_vertices']==21600,'Actor input/reference scope differs')
    check(sha(binary)==m['binary']['sha256']==c['inputs_sha256']and sha(official)==c['official_output_sha256'],'Compared actor inputs/output changed')
    root=Path(__file__).resolve().parents[1].parent/'t3b_unreal';source=root/'Source/T3BRemake'
    files=[source/'Private/T3BGELighting.cpp',source/'Private/T3BGESeries.cpp',source/'Public/T3BGELighting.h',source/'Public/T3BGESeries.h',root/'Tools/ge_other_actor_series_probe.cpp']
    copies=[]
    for f in files:
        dest=a.out/f.name;shutil.copyfile(f,dest);copies.append(dest)
    exe=a.out/'ge_other_actor_series_probe.exe'
    cmd=[str(a.compiler),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-msse4.1','-ffp-contract=off','-I'+str(a.out),
        *[str(f)for f in copies if f.suffix=='.cpp'],'-o',str(exe)]
    build=subprocess.run(cmd,capture_output=True,encoding='utf-8',errors='replace')
    (a.out/'build_stdout.log').write_text(build.stdout,encoding='utf-8');(a.out/'build_stderr.log').write_text(build.stderr,encoding='utf-8')
    check(build.returncode==0,'Actor production build failed')
    out=a.out/'runtime_outputs.bin';uv=a.out/'runtime_uv.f32';command=[str(exe),str(binary),str(out),str(uv)]
    run=subprocess.run(command,capture_output=True,encoding='utf-8')
    (a.out/'stdout.log').write_text(run.stdout,encoding='utf-8');(a.out/'stderr.log').write_text(run.stderr,encoding='utf-8')
    check(run.returncode==0,'Actor production evaluation failed')
    check(out.read_bytes()==official.read_bytes(),'Production transform/light differs from pinned software model')
    raw=binary.read_bytes();expected=bytearray()
    for draw in m['draws']:
        at=draw['binary_byte_offset']+1464
        for i in range(draw['vertex_count']):expected+=raw[at+i*64+56:at+i*64+64]
    check(uv.read_bytes()==expected,'Actor UV bits changed')
    result=json.loads(run.stdout);check(result==dict(samples=12,vertices=21600),'Unexpected evaluated actor coverage')
    report=dict(schema='other-actor-production-series-proof/v1',passed=True,input_manifest=identity(a.inputs),input_sha256=sha(binary),
        comparison=identity(a.comparison),runtime_output=identity(out),runtime_uv=identity(uv),sources=[identity(f)for f in copies],
        build_command=cmd,command=command,compiler_sha256=sha(a.compiler),executable_sha256=sha(exe),result=result,
        all_transform_color_bytes_equal=True,all_uv_bytes_equal=True,UE_executed=False,original_hardware_pixels_verified=False,original_timing_verified=False)
    (a.out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,**result)))


if __name__=='__main__':main()
