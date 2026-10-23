"""Export observed immutable geometry/color references, preserving dynamic tint ownership."""
import argparse
import hashlib
import json
import shutil
import struct
from pathlib import Path
from analyze_fx_node_time import check,identity,read,sidecar


def raw(window):return sidecar(window['raw'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--proof',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();check(not args.out.exists(),'Never replace color-binding export');args.out.mkdir(parents=True)
    proof=read(args.proof);check(proof['passed'],'No original color-write proof');ops=[o for o in proof['operations']if o['expected_enqueue']]
    first=ops[0];source=raw(first['source_palette']);palette=args.out/'source_vertex_color_palette.bin';palette.write_bytes(source)
    templates=[];signature=hashlib.sha256(source)
    for j,draw in enumerate(first['draws']):
        vt=draw['vtype'];stride,offset=(16,4)if vt==0x11e else(12,0)
        before=raw(draw['vertices_before']);masked=bytearray(before)
        for i in range(len(draw['color_indices'])):masked[i*stride+offset:i*stride+offset+4]=b'\0'*4
        for op in ops:
            check(raw(op['source_palette'])==source and len(op['draws'])==len(first['draws']),'Observed original palette/draw count changed')
            d=op['draws'][j];check(d['vtype']==vt and d['color_indices']==draw['color_indices'],'Original color-reference layout changed')
            b=bytearray(raw(d['vertices_before']))
            for i in range(len(d['color_indices'])):b[i*stride+offset:i*stride+offset+4]=b'\0'*4
            check(b==masked,'Observed original non-color geometry changed')
        path=args.out/('draw_%02d_captured_vertices.bin'%j);path.write_bytes(before)
        signature.update(struct.pack('<2I',vt,len(draw['color_indices']))+masked+struct.pack('<%dI'%len(draw['color_indices']),*draw['color_indices']))
        templates.append(dict(draw=j,vtype=vt,vertices=len(draw['color_indices']),stride=stride,color_offset=offset,color_indices=draw['color_indices'],
                              captured_vertices=identity(path),color_recomputed_before_use=True))
    result=dict(schema='original-FX-observed-vertex-color-bindings/v1',passed=True,proof=identity(args.proof),producer=identity(Path(__file__)),
                descriptor_offset=0x10c78,source_type=155,source_vertex_palette=identity(palette),templates=templates,
                observed_non_color_geometry_and_references_sha256=signature.hexdigest(),observations_cross_checked=len(ops),
                default_M1_binding_replaced=False,
                limits=['Captured vertex colors reflect a previous actual tint; consumers must overwrite every color through the original palette references before drawing.',
                        'The signature identifies this observed palette/reference/non-color-geometry layout, not a universal original resource GUID.',
                        'Texture CLUT, original matrices, UV state and actual frame tint remain separate inputs.'])
    shutil.copyfile(Path(__file__),args.out/'executed_export_fx_vertex_color_bindings.py')
    (args.out/'vertex_color_bindings.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,draw_templates=len(templates),vertices=sum(d['vertices']for d in templates),cross_checked_observations=len(ops))))


if __name__=='__main__':main()
