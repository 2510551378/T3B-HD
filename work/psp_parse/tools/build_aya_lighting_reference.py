"""Build a fixed upstream reference and compare native lighting on retained inputs.

Upstream source files remain byte-identical. Explicit, test-only compatibility
headers adapt register storage and unused framework facilities; Math3D/Lighting
arithmetic is compiled from the original tagged files, not a rewritten formula.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def check(ok,message):
    if not ok:raise ValueError(message)


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--compiler',type=Path,required=True)
    p.add_argument('--inputs',type=Path,default=ROOT/'out/AYA_GE_VERTEX_LIGHTING_20261020/inputs/inputs.json',
                   help='Retained input manifest, including separately captured sample series')
    a=p.parse_args()
    check(not a.out.exists(),'Never overwrite prior comparison');a.out.mkdir(parents=True)
    ref=ROOT/'out/AYA_GE_VERTEX_LIGHTING_20261020/reference';inc=a.out/'include';inc.mkdir()
    mapping={'GPU/Math3D.h':'GPU_Math3D.h','Common/Math/SIMDHeaders.h':'Common_Math_SIMDHeaders.h',
             'Common/Math/fast/fast_matrix.h':'Common_Math_fast_fast_matrix.h',
             'GPU/Software/Lighting.h':'GPU_Software_Lighting.h'}
    source_manifest=[]
    for target,name in mapping.items():
        output=inc/target;output.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ref/name,output)
        source_manifest.append(dict(file=str(output),sha256=sha(output),upstream=name))
    shims={
        'ppsspp_config.h':'#pragma once\n#define PPSSPP_ARCH(x) PPSSPP_ARCH_##x\n#define PPSSPP_ARCH_SSE2 1\n#define PPSSPP_ARCH_X86 0\n#define PPSSPP_ARCH_ARM64_NEON 0\n#define PPSSPP_ARCH_ARM_NEON 0\n#define PPSSPP_ARCH_LOONGARCH64 0\n#define PPSSPP_ARCH_LOONGARCH64_LSX 0\n#define PPSSPP_PLATFORM(x) 0\n',
        'Common/Common.h':'#pragma once\n#include <algorithm>\n#include <cstdint>\n#include <cassert>\nusing u8=std::uint8_t;using u16=std::uint16_t;using u32=std::uint32_t;using s8=std::int8_t;using s16=std::int16_t;using s32=std::int32_t;\n',
        'Common/CPUDetect.h':'#pragma once\nstruct TestCPUInfo{bool bSSE4_1;};extern TestCPUInfo cpu_info;\n',
        'Core/Util/AudioFormat.h':'#pragma once\ninline int clamp_u8(int v){return v<0?0:v>255?255:v;}\n',
        'GPU/Software/TransformUnit.h':'#pragma once\n#include "GPU/Math3D.h"\nusing namespace Math3D;using WorldCoords=Vec3<float>;struct VertexData{Vec3f texturecoords;u32 color0=0,color1=0;};\n',
    }
    for target,data in shims.items():
        output=inc/target;output.parent.mkdir(parents=True,exist_ok=True);output.write_text(data,encoding='utf-8')
    shutil.copyfile(ROOT/'tools/lighting_reference/GPUStateCompat.h',inc/'GPU/GPUState.h')
    for name in ('GPU_Software_Lighting.cpp','GPU_Math3D.cpp'):shutil.copyfile(ref/name,a.out/name)
    own=ROOT.parent/'t3b_unreal/Source/T3BRemake';exe=a.out/'compare_lighting.exe'
    cmd=[str(a.compiler),'-std=c++17','-O2','-Wall','-Wextra','-Wno-unused-parameter','-msse4.1','-ffp-contract=off',
         '-I'+str(inc),'-I'+str(own/'Public'),str(a.out/'GPU_Software_Lighting.cpp'),str(a.out/'GPU_Math3D.cpp'),
         str(ROOT/'tools/lighting_reference/compare.cpp'),str(own/'Private/T3BGELighting.cpp'),'-o',str(exe)]
    build=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (a.out/'build_stdout.log').write_text(build.stdout,encoding='utf-8');(a.out/'build_stderr.log').write_text(build.stderr,encoding='utf-8')
    (a.out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n',encoding='utf-8')
    check(build.returncode==0,'Reference build failed: '+str(a.out))
    manifest=json.loads(a.inputs.read_text(encoding='utf-8'))
    check(manifest['passed'],'Input recovery failed')
    inputs=Path(manifest['binary']['file'])
    check(sha(inputs)==manifest['binary']['sha256'],'Retained lighting inputs changed')
    official=a.out/'official_outputs.bin';candidate=a.out/'native_outputs.bin'
    run=subprocess.run([str(exe),str(inputs),str(official),str(candidate)],capture_output=True,text=True,encoding='utf-8')
    (a.out/'run_stdout.log').write_text(run.stdout,encoding='utf-8');(a.out/'run_stderr.log').write_text(run.stderr,encoding='utf-8')
    r=dict(schema='aya-ge-vertex-lighting-reference-comparison/v1',passed=run.returncode==0,
           input_manifest=str(a.inputs.resolve()),input_manifest_sha256=sha(a.inputs),
           inputs_sha256=sha(inputs),compiler=str(a.compiler),compiler_version=subprocess.run([str(a.compiler),'--version'],capture_output=True,text=True).stdout.splitlines()[0],
           original_lighting_source_sha256=sha(ref/'GPU_Software_Lighting.cpp'),
           original_math_source_sha256=sha(ref/'GPU_Math3D.cpp'),compatibility_header_sha256=sha(inc/'GPU/GPUState.h'),
           native_source_sha256=sha(own/'Private/T3BGELighting.cpp'),native_header_sha256=sha(own/'Public/T3BGELighting.h'),
           comparison_driver_sha256=sha(ROOT/'tools/lighting_reference/compare.cpp'),builder_sha256=sha(Path(__file__)),
           compatibility_headers=[dict(file=str(p),sha256=sha(p))for p in sorted(inc.rglob('*'))if p.is_file()],
           reference_sources=source_manifest,executable_sha256=sha(exe),exit_code=run.returncode,
           comparison=json.loads(run.stdout),official_output_sha256=sha(official),native_output_sha256=sha(candidate),
           output_stride_bytes=32,original_runtime_output_sampled=False,hardware_pixel_equivalence_verified=False,
           reference_scope='Pinned PPSSPP v1.20.4 x64 software-lighting SSE4 model, compiled unchanged arithmetic with retained-state/test-framework adapters.',
           limits=['Input geometry/matrices/registers are original recorded observations; computed lighting colors are reconstructions.',
                   'Matching this software model does not prove PSP hardware or PPSSPP hardware-backend output pixels.',
                   'No verified authored-clip clock, rasterization, fog, texture combine, depth or blend acceptance.'])
    (a.out/'comparison.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(r['comparison']))
    check(r['passed'],'Actual reference comparison differs; inspect preserved outputs')


if __name__=='__main__':main()
