"""Execute production effect decoder on actually correlated full subdraws."""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np

from extract_runtime_character import layout


def check(value, reason):
    if not value:
        raise ValueError(reason)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def identity(p):
    return dict(file=str(p.resolve()),sha256=sha(p))


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof',type=Path,action='append',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    check(not args.out.exists(),'Never replace actual decoder evidence')
    args.out.mkdir(parents=True)
    observations=[]
    for p in args.proof:
        r=read(p)
        check(r['passed'] and r['matched_GE_primitive_count']>0,'No full-handler GE evidence')
        for m in r['matched_primitives']:
            observations.append((p,m))
    header=b'T3BFXS1\0'+struct.pack('<I',len(observations))
    input_bytes=bytearray(header)
    expected=bytearray()
    bindings=[]
    total_vertices=total_indices=0
    for index,(proof,m) in enumerate(observations):
        d=m['source_primitive'];path=Path(d['vertices']['file'])
        check(sha(path)==d['vertices']['sha256'],'Original source vertices changed')
        raw=path.read_bytes();vt,n=d['vtype'],d['count'];r=[0]*256
        for key,value in m['registers'].items():
            r[int(key,16)]=value
        input_bytes.extend(struct.pack('<256I3I',*r,vt,n,len(raw))+raw)
        stride,fields=layout(vt)
        check(len(raw)==stride*n,'Original effect source extent')
        def f24(k):
            return np.frombuffer(struct.pack('<I',r[k]<<8),dtype='<f4')[0]
        scale=np.array([f24(0x48),f24(0x49)],dtype='<f4')
        offset=np.array([f24(0x4a),f24(0x4b)],dtype='<f4')
        indices=[]
        for j in range(n-2):
            indices.extend([j+1,j,j+2] if j&1 else [j,j+1,j+2])
        expected.extend(struct.pack('<2I',n,len(indices)))
        for j in range(n):
            at=j*stride
            pos=np.array(struct.unpack_from('<3h',raw,at+fields['pos'][0]),dtype='<f4')/np.float32(32768)
            uv=np.array(struct.unpack_from('<2H',raw,at+fields['uv'][0]),dtype='<f4')/np.float32(32768)
            uv=(uv*scale).astype('<f4')+offset
            rgba=struct.unpack_from('<4B',raw,at+fields['col'][0]) if 'col'in fields else tuple((r[0x55]>>(8*k))&255 for k in range(3))+(r[0x58]&255,)
            expected.extend(struct.pack('<5f4B',*pos,*uv,*rgba))
        expected.extend(struct.pack('<%dI'%len(indices),*indices))
        bindings.append(dict(index=index,proof=identity(proof),CPU_sample=m['CPU_sample'],subdraw=m['subdraw'],GE_sample=m['GE_sample'],GE_record=m['record'],
            runtime_geometry_id=m['runtime_geometry_id'],vtype=vt,source_vertices=n,texture_RGBA_sha256=m['texture_RGBA_sha256']))
        total_vertices+=n;total_indices+=len(indices)
    inputs,reference=args.out/'original_effect_inputs.bin',args.out/'independent_expected.bin'
    inputs.write_bytes(input_bytes);reference.write_bytes(expected)
    project=Path(__file__).resolve().parents[2]/'t3b_unreal'
    public,private=project/'Source/T3BRemake/Public',project/'Source/T3BRemake/Private'
    sources=[private/'T3BGEEffectGeometry.cpp',project/'Tools/ge_effect_geometry_probe.cpp']
    snapshot=args.out/'executed_source_snapshot';snapshot.mkdir()
    inventory=[]
    for p in sources+[public/'T3BGEEffectGeometry.h',public/'T3BGELighting.h',Path(__file__)]:
        copy=snapshot/p.name;shutil.copyfile(p,copy);inventory.append(dict(**identity(p),retained_copy=str(copy.resolve())))
    exe,output=args.out/'ge_effect_geometry_probe.exe',args.out/'runtime_decoded.bin'
    build=['C:\\Strawberry\\c\\bin\\g++.exe','-std=c++17','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-I'+str(public),*map(str,sources),'-o',str(exe)]
    result=subprocess.run(build,capture_output=True)
    (args.out/'build_stdout.log').write_bytes(result.stdout);(args.out/'build_stderr.log').write_bytes(result.stderr)
    check(result.returncode==0,'Production effect decoder build failed')
    command=[str(exe),str(inputs),str(output)]
    result=subprocess.run(command,capture_output=True)
    (args.out/'stdout.log').write_bytes(result.stdout);(args.out/'stderr.log').write_bytes(result.stderr)
    check(result.returncode==0,'Actual source effect decoder failed')
    check(output.read_bytes()==reference.read_bytes(),'Production position/UV/color/strip indices differ from independent source decoding')
    bad_lighting=bytearray(input_bytes);struct.pack_into('<I',bad_lighting,12+0x17*4,1)
    bad_primitive=bytearray(input_bytes);struct.pack_into('<I',bad_primitive,12+4*4,0x30004)
    cases=[('truncated',input_bytes[:-1]),('trailing',input_bytes+b'\0'),('unsupported_lighting',bad_lighting),('wrong_PRIM',bad_primitive)]
    rejected=[]
    for name,bad in cases:
        p=args.out/('negative_'+name+'.bin');p.write_bytes(bad)
        process=subprocess.run([str(exe),str(p),str(args.out/('negative_'+name+'.output'))],capture_output=True)
        check(process.returncode!=0,'Bad source effect input accepted: '+name)
        rejected.append(dict(case=name,exit_code=process.returncode,diagnostic=process.stderr.decode('utf-8',errors='replace').strip()))
    for item in inventory:
        check(sha(Path(item['file']))==item['sha256']==sha(Path(item['retained_copy'])),'Source changed while compiling')
    report=dict(schema='production-original-effect-geometry-proof/v1',passed=True,input=identity(inputs),reference=identity(reference),actual_output=identity(output),
        actual_executable=identity(exe),build_command=build,run_command=command,source_inventory=inventory,bindings=bindings,
        draws=len(observations),source_vertices=total_vertices,triangle_indices=total_indices,triangles=total_indices//3,
        all_position_UV_color_and_indices_bytes_equal=True,negative_controls=rejected,actual_UE_module_executed=False,default_M1_binding_replaced=False,
        limits=['Production core decodes original unweighted/unlit VTYPE102/11e strips and source UV/ambient-color contract only.',
                'Original per-draw matrices/material bindings remain separate verified inputs. This does not reconstruct authored time, new-camera billboard behavior, or final raster pixels.',
                'Standalone production core execution does not establish formal UE module loading, M1 gameplay or HD artwork.'])
    (args.out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,draws=len(observations),vertices=total_vertices,triangles=total_indices//3,rejected_controls=len(rejected))))


if __name__=='__main__':
    main()
