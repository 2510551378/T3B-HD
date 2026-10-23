"""Run production color->palette->vertex patch->effect decoder on exact GE-matched draws."""
import argparse
import json
import shutil
import struct
import subprocess
from pathlib import Path
import numpy as np
from analyze_fx_node_time import check,identity,read,sidecar


def raw(window):return sidecar(window['raw'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--proof',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();check(not args.out.exists(),'Never replace integrated effect evidence');args.out.mkdir(parents=True)
    proof=read(args.proof);check(proof['passed']and proof['matched_GE_primitive_count']>0,'No exact GE vertex-color matches')
    for key in ('producer','capture','CPU_write_proof'):check(identity(Path(proof[key]['file']))==proof[key],'GE proof source changed')
    inputs=bytearray(b'T3BPC1\0\0'+struct.pack('<I',len(proof['matched_primitives'])));expected=bytearray();bindings=[];total_vertices=0
    for m in proof['matched_primitives']:
        op=m['CPU_palette_operation'];source=m['source_color_binding'];d=m['source_primitive'];regs=[0]*256
        for key,value in m['registers'].items():regs[int(key,16)]=value
        vt,n=d['vtype'],d['count'];check(vt==0x11e,'Current integrated match needs original RGBA8888/U16/S16 format')
        palette=raw(op['source_palette']);before=raw(source['vertices_before']);after=sidecar(d['vertices'])
        check(after==raw(source['vertices_after'])and len(after)==n*16,'GE after-image binding differs')
        inputs.extend(struct.pack('<259I',*regs,vt,n,op['mode'])+struct.pack('<8I',*op['source_bits'],*op['parent_bits']))
        inputs.extend(struct.pack('<I',len(palette))+palette+struct.pack('<%dI'%n,*source['color_indices'])+struct.pack('<I',len(before))+before)
        converted=raw(op['expected_palette']);expected.extend(struct.pack('<I',len(converted))+converted+struct.pack('<I',len(after))+after)
        indices=[index for j in range(n-2)for index in ([j+1,j,j+2]if j&1 else[j,j+1,j+2])]
        expected.extend(struct.pack('<2I',n,len(indices)))
        def f24(k):return np.frombuffer(struct.pack('<I',regs[k]<<8),dtype='<f4')[0]
        scale=np.array([f24(0x48),f24(0x49)],dtype='<f4');offset=np.array([f24(0x4a),f24(0x4b)],dtype='<f4')
        for k in range(n):
            pos=np.array(struct.unpack_from('<3h',after,k*16+8),dtype='<f4')/np.float32(32768)
            uv=np.array(struct.unpack_from('<2H',after,k*16),dtype='<f4')/np.float32(32768)
            uv=(uv*scale).astype('<f4')+offset;rgba=struct.unpack_from('<4B',after,k*16+4)
            expected.extend(struct.pack('<5f4B',*pos,*uv,*rgba))
        expected.extend(struct.pack('<%dI'%len(indices),*indices));total_vertices+=n
        bindings.append(dict(CPU_row=m['CPU_sample'],subdraw=m['subdraw'],GE_sample=m['GE_sample'],GE_record=m['record'],
            texture_RGBA_sha256=m['texture_RGBA_sha256'],WORLD=m['WORLD_payload'],VIEW=m['VIEW_payload'],PROJECTION=m['PROJECTION_payload'],
            material_parameters=m['material_parameters'],CLUT=m['CLUT']))
    input_path,reference,output=(args.out/name for name in ('original_pipeline_inputs.bin','independent_GE_expected.bin','runtime_output.bin'))
    input_path.write_bytes(inputs);reference.write_bytes(expected)
    project=Path(__file__).resolve().parents[2]/'t3b_unreal';public=project/'Source/T3BRemake/Public';private=project/'Source/T3BRemake/Private'
    sources=[private/'T3BGEEffectVertexColor.cpp',private/'T3BGEEffectGeometry.cpp',project/'Tools/ge_effect_tinted_strip_probe.cpp']
    snapshot=args.out/'executed_source_snapshot';snapshot.mkdir();inventory=[]
    for path in sources+[public/n for n in ('T3BGEEffectVertexColor.h','T3BGEEffectGeometry.h','T3BGELighting.h')]+[Path(__file__),Path(__file__).with_name('analyze_fx_vertex_color_GE.py')]:
        dest=snapshot/path.name;shutil.copyfile(path,dest);inventory.append(dict(**identity(path),retained_copy=str(dest.resolve())))
    exe=args.out/'ge_effect_tinted_strip_probe.exe';build=['C:\\Strawberry\\c\\bin\\g++.exe','-std=c++17','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off',
        '-I'+str(public),*map(str,sources),'-o',str(exe)]
    process=subprocess.run(build,capture_output=True);(args.out/'build_stdout.log').write_bytes(process.stdout);(args.out/'build_stderr.log').write_bytes(process.stderr)
    check(process.returncode==0,'Integrated production effect build failed')
    command=[str(exe),str(input_path),str(output)];process=subprocess.run(command,capture_output=True)
    (args.out/'stdout.log').write_bytes(process.stdout);(args.out/'stderr.log').write_bytes(process.stderr)
    check(process.returncode==0 and output.read_bytes()==reference.read_bytes(),'Integrated palette/patch/position/UV/color/topology differs from original GE')
    bad_lighting=bytearray(inputs);struct.pack_into('<I',bad_lighting,12+0x17*4,1)
    bad_uv=bytearray(inputs);struct.pack_into('<I',bad_uv,12+0xc0*4,1)
    bad_prim=bytearray(inputs);struct.pack_into('<I',bad_prim,12+4*4,(3<<16)|4)
    controls=[]
    for name,bad in [('lighting_contract',bad_lighting),('UV_generation_contract',bad_uv),('wrong_primitive',bad_prim),('truncated',inputs[:-1])]:
        path=args.out/('negative_'+name+'.bin');path.write_bytes(bad)
        process=subprocess.run([str(exe),str(path),str(args.out/('negative_'+name+'.output'))],capture_output=True)
        check(process.returncode!=0,'Invalid integrated draw accepted: '+name)
        controls.append(dict(case=name,exit_code=process.returncode,diagnostic=process.stderr.decode('utf-8',errors='replace').strip()))
    for item in inventory:
        check(identity(Path(item['file']))['sha256']==item['sha256']==identity(Path(item['retained_copy']))['sha256'],'Integrated source changed during build')
    report=dict(schema='production-original-tinted-effect-strip-proof/v1',passed=True,proof=identity(args.proof),build_command=build,run_command=command,source_inventory=inventory,
        executable=identity(exe),inputs=identity(input_path),reference=identity(reference),actual_output=identity(output),bindings=bindings,
        draws=len(bindings),vertices=total_vertices,triangles=sum(m['source_primitive']['count']-2 for m in proof['matched_primitives']),
        all_palette_patched_vertices_local_position_UV_color_topology_bytes_equal=True,negative_controls=controls,
        actual_UE_module_executed=False,actual_GPU_pixels_verified=False,default_M1_binding_replaced=False,
        limits=['One process executes both production color and existing effect geometry cores on exact recorded GE-matched observations.',
                'Outputs are original local render attributes/strip topology; retained matrices, CLUT, texture and blending remain renderer inputs.',
                'This does not execute the formal UE module or validate new final GPU pixels/playable M1.'])
    (args.out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,draws=report['draws'],vertices=total_vertices,triangles=report['triangles'],rejected_controls=len(controls))))


if __name__=='__main__':main()
