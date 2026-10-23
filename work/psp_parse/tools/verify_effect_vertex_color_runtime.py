"""Run production parent/mode/cache/palette/vertex-color core against actual CPU writes."""
import argparse
import copy
import json
import shutil
import struct
import subprocess
from pathlib import Path
from analyze_fx_node_time import bits,check,identity,number,read,registers,sha,sidecar
from analyze_fx_vertex_color import mode_reference,palette_reference


def raw(item):return sidecar(item['raw'])


def packet(ops):
    b=bytearray(b'T3BRC1\0\0'+struct.pack('<I',len(ops)))
    for o in ops:
        palette=raw(o['source_palette']);old=raw(o['previous_palette']);check(len(palette)==len(old),'Palette extent differs')
        b.extend(struct.pack('<16I',o['mode'],*o['source_bits'],*o['parent_bits'],*o['previous_cached_bits'],o['pending'],o['capacity'],len(palette))+palette+old)
        b.extend(struct.pack('<I',len(o['draws'])))
        for d in o['draws']:
            vertices=raw(d['vertices_before']);indices=d['color_indices']
            b.extend(struct.pack('<3I',d['vtype'],len(indices),len(vertices))+struct.pack('<%dI'%len(indices),*indices)+vertices)
    return b


def expected(ops):
    b=bytearray()
    for o in ops:
        palette=raw(o['expected_palette']);b.extend(struct.pack('<10I',*o['expected_combined_bits'],*o['expected_processed_bits'],o['expected_enqueue'],len(palette))+palette)
        b.extend(struct.pack('<I',len(o['draws'])))
        for d in o['draws']:
            vertices=raw(d['vertices_after']);b.extend(struct.pack('<I',len(vertices))+vertices)
    return b


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--proof',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();check(not args.out.exists(),'Never replace vertex-color execution evidence');args.out.mkdir(parents=True)
    proof=read(args.proof);check(proof['passed']and proof['actual_palette_conversions']==5,'Missing actual converted palettes')
    for k in ('producer','oracle','capture','module'):check(identity(Path(proof[k]['file']))==proof[k],'Source evidence changed')
    actual=proof['operations'];capture=read(Path(proof['capture']['file']));module=Path(proof['module']['file']).read_bytes()
    template=capture['rows'][1];mg,mf=registers(template['modulated']['allRegisters']);pg,pf=registers(template['paletteEntry']['allRegisters'])
    fixtures=args.out/'synthetic_original_instruction_inputs';fixtures.mkdir();synthetic=[]
    cases=[('mode_'+str(mode),mode,[127.125,200,300,64],[1,0.8,0.5,1],'changed',0x11e)for mode in (0,1,6,7,8,9,10,11,12,255)]
    cases += [('negative_palette_byte_store',9,[128,64,32,-1],[1]*4,'changed',0x11e),
              ('inverse_alpha_clamp',6,[128,64,32,200],[1]*4,'changed',0x11e),
              ('mode10_negative_factor',10,[128,64,32,300],[1]*4,'changed',0x11e),
              ('cache_same_bits',1,[128,56,8,48],[1]*4,'same',0x11e),
              ('cache_full',1,[128,56,8,48],[1]*4,'full',0x11e),
              ('cache_signed_zero',0,[-0.0,0,1,0],[1]*4,'signed_zero',0x11e),
              ('no_UV_stride12',1,[128,56,8,48],[1]*4,'changed',0x11c)]
    for name,mode,source,parent,cache_mode,vt in cases:
        folder=fixtures/name;folder.mkdir()
        def retain(name,address,data):
            path=folder/name;path.write_bytes(data);return dict(address=address,size=len(data),raw=dict(file=str(path.resolve()),bytes=len(data),sha256=sha(data)))
        sb,pb=list(map(bits,source)),list(map(bits,parent));combined=[bits(number(a)*number(b))for a,b in zip(sb,pb)]
        rec=bytearray(raw(template['modulated']['record']));rec[0x4b]=mode
        record=retain('source_record.bin',template['modulated']['record']['address'],rec)
        stack=retain('combined_RGBA.bin',mg[29],struct.pack('<4I',*combined));f=list(mf);f[26]=bits(1)
        processed,trace=mode_reference(module,mg,f,record,stack,template['modulated']['jumpTable'])
        processed_bits=list(struct.unpack('<4I',processed));previous=[bits(1234)]*4;pending,capacity=0,2
        if cache_mode=='same':previous=processed_bits[:]
        elif cache_mode=='full':pending=capacity=1
        elif cache_mode=='signed_zero':previous=processed_bits[:];previous[0]=bits(0)
        enqueue=pending<capacity and previous!=processed_bits
        pe=template['paletteEntry'];src=retain('source_palette.bin',pg[6],raw(pe['source']))
        tint=retain('palette_tint.bin',pg[7],processed);old=retain('old_palette.bin',pg[4],raw(pe['outputBefore']))
        vm,converted=palette_reference(module,pg,pf,src,tint,old)
        result=retain('expected_palette.bin',pg[4],converted if enqueue else raw(old))
        stride,offset=(16,4)if vt==0x11e else(12,0);indices=[0,1,1]
        vertices=bytes((j*13+7)%256 for j in range(len(indices)*stride));patched=bytearray(vertices)
        if enqueue:
            for j,index in enumerate(indices):patched[j*stride+offset:j*stride+offset+4]=converted[index*4:index*4+4]
        d=dict(vtype=vt,color_indices=indices,vertices_before=retain('vertices_before.bin',0x0b000000,vertices),vertices_after=retain('vertices_after.bin',0x0b000000,patched))
        synthetic.append(dict(case=name,classification='synthetic original scalar opcode operands/layout',source_bits=sb,parent_bits=pb,mode=mode,
            previous_cached_bits=previous,pending=pending,capacity=capacity,source_palette=src,previous_palette=old,
            expected_combined_bits=combined,expected_processed_bits=processed_bits,expected_enqueue=enqueue,expected_palette=result,draws=[d],
            original_mode_trace=trace,original_palette_trace=vm.trace))
    project=Path(__file__).resolve().parents[2]/'t3b_unreal';public=project/'Source/T3BRemake/Public'
    sources=[project/'Source/T3BRemake/Private/T3BGEEffectVertexColor.cpp',project/'Tools/ge_effect_vertex_color_probe.cpp']
    snapshot=args.out/'executed_source_snapshot';snapshot.mkdir();inventory=[]
    for source in sources+[public/'T3BGEEffectVertexColor.h',Path(__file__)]+[Path(__file__).with_name(n)for n in ('analyze_fx_vertex_color.py','replay_fx_render_color.py','analyze_fx_node_time.py','analyze_fx_property_callbacks.py')]:
        dest=snapshot/source.name;shutil.copyfile(source,dest);inventory.append(dict(**identity(source),retained_copy=str(dest.resolve())))
    exe=args.out/'ge_effect_vertex_color_probe.exe';build=['C:\\Strawberry\\c\\bin\\g++.exe','-std=c++17','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off',
        '-I'+str(public),*map(str,sources),'-o',str(exe)]
    process=subprocess.run(build,capture_output=True);(args.out/'build_stdout.log').write_bytes(process.stdout);(args.out/'build_stderr.log').write_bytes(process.stderr)
    check(process.returncode==0,'Production vertex-color build failed');runs=[]
    for name,ops in [('actual',actual),('synthetic',synthetic)]:
        inputs,reference,output=(args.out/(name+s)for s in ('_inputs.bin','_expected.bin','_output.bin'))
        inputs.write_bytes(packet(ops));reference.write_bytes(expected(ops));command=[str(exe),str(inputs),str(output)]
        process=subprocess.run(command,capture_output=True);(args.out/(name+'_stdout.log')).write_bytes(process.stdout);(args.out/(name+'_stderr.log')).write_bytes(process.stderr)
        check(process.returncode==0 and output.read_bytes()==reference.read_bytes(),'Production parent/mode/cache/palette/vertex colors differ: '+name)
        runs.append(dict(classification=name,render_operations=len(ops),command=command,inputs=identity(inputs),reference=identity(reference),output=identity(output),all_output_bytes_equal=True))
    bad_index=copy.deepcopy(actual[1]);bad_index['draws'][0]['color_indices'][0]=99
    bad_vt=copy.deepcopy(actual[1]);bad_vt['draws'][0]['vtype']=0x522
    nonfinite=copy.deepcopy(actual[1]);nonfinite['source_bits'][0]=0x7f800000
    invalid_cache=copy.deepcopy(actual[1]);invalid_cache['pending']=invalid_cache['capacity']+1
    negative=[]
    for name,data in [('truncated',packet(actual)[:-1]),('trailing',packet(actual)+b'\0'),('palette_index',packet([bad_index])),
                      ('unsupported_layout',packet([bad_vt])),('nonfinite',packet([nonfinite])),('invalid_cache',packet([invalid_cache]))]:
        path=args.out/('negative_'+name+'.bin');path.write_bytes(data)
        process=subprocess.run([str(exe),str(path),str(args.out/('negative_'+name+'.output'))],capture_output=True)
        check(process.returncode!=0,'Invalid vertex-color input accepted: '+name)
        negative.append(dict(case=name,exit_code=process.returncode,diagnostic=process.stderr.decode('utf-8',errors='replace').strip()))
    for item in inventory:
        check(identity(Path(item['file']))['sha256']==item['sha256']==identity(Path(item['retained_copy']))['sha256'],'Source changed during compilation')
    result=dict(schema='production-original-effect-vertex-color-proof/v1',passed=True,proof=identity(args.proof),actual_executable=identity(exe),build_command=build,
                source_inventory=inventory,runs=runs,synthetic_fixtures=synthetic,negative_controls=negative,actual_palette_conversions=proof['actual_palette_conversions'],
                actual_patched_draws=proof['patched_draws'],actual_patched_vertices=proof['patched_vertices'],actual_UE_module_executed=False,
                default_M1_binding_replaced=False,new_GE_consumption_capture_verified=False,
                limits=['Production numeric core covers parent/mode color, byte-exact cache equality, vertex-color palette and supported vertex layouts.',
                        'Raw cache allocation/scheduling, pointer ownership, texture CLUT and final GPU execution remain external.',
                        'Other color modes, negative/large inputs, signed zero and stride12 are explicit synthetic fixtures, not new original game observations.'])
    (args.out/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,actual_render_operations=len(actual),actual_palette_conversions=proof['actual_palette_conversions'],
                         patched_draws=proof['patched_draws'],patched_vertices=proof['patched_vertices'],synthetic_operations=len(synthetic),rejected_controls=len(negative))))


if __name__=='__main__':main()
