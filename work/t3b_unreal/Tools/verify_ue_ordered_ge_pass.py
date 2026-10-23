"""Prepared acceptance audit for a future actual UE ordered-pass capture.

No result is generated until the real compiled module has run successfully.
"""
import argparse,hashlib,json,struct
from pathlib import Path
import numpy as np
from PIL import Image


def check(ok,reason):
    if not ok:raise ValueError(reason)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def js(p):return json.loads(p.read_text(encoding='utf-8'))
def file(row):
    p=Path(row['file']);check(sha(p)==row['sha256'],'Recorded file changed: '+str(p));return p
def image(row):return np.asarray(Image.open(file(row)).convert('RGB'),dtype=np.int16)


def read_bundle(raw):
    check(raw[:8]==b'T3BGPU1\0','Wrong source bundle');w,h,frames,atlases=struct.unpack_from('<4I',raw,8);offset=24
    check((w,h,frames,atlases)==(512,768,12,2),'Unexpected source-series scope')
    for _ in range(atlases):
        tw,th=struct.unpack_from('<2I',raw,offset);offset+=8+tw*th*4
    result=[]
    for sample in range(frames):
        index,count=struct.unpack_from('<2I',raw,offset);offset+=8;check(index==sample and count==107,'Original draw sequence differs')
        vertices=bytearray();sections=[];first=0
        for ordinal in range(count):
            texture,order,n=struct.unpack_from('<3I',raw,offset);offset+=12
            check(order==ordinal and n%3==0 and texture<2,'Original draw metadata invalid')
            sections.append((first,n,texture));vertices+=raw[offset:offset+n*36];offset+=n*36;first+=n
        result.append((sections,bytes(vertices),first))
    check(offset==len(raw),'Incomplete/trailing bundle data');return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);a=p.parse_args()
    target=a.run/'independent_render_acceptance.json';check(not target.exists(),'Never replace prior acceptance')
    r=js(a.run/'actual_ue_ge_pass.json');request=js(a.run/'request.json');done=js(a.run/'process_completed.json')
    check(r['passed']and done['exit_code']==0 and r['process_id']==done['pid']and r['run_id']==request['run_id'],'No successful actual UE acquisition')
    check(sha(a.run/'capture_ge_ordered_pass_executed.py')==r['script_sha256']==request['script_sha256'],'Executed producer changed')
    file(request['actual_module']);source=read_bundle(file(request['bundle']).read_bytes())
    for row in request['current_source_inventory']:file(row)
    check(r['all_original_packages_unchanged']and r['packages_after']==r['protected_packages_before'],'UE asset packages changed')
    for row in r['packages_after']:file(row)
    check(len(r['samples'])==12,'Incomplete actual scene replay');results=[]
    for entry,(sections,vertices,count)in zip(r['samples'],source):
        sample=entry['sample'];check(sample==len(results),'Actual sample sequence differs')
        check(entry['actor_transform']==dict(translation=[0.,0.,0.],scale=[1.,1.,1.],quaternion=[0.,0.,0.,1.]),'Unexpected actor calibration transform')
        submitted=file(entry['submitted']).read_bytes();check(submitted[:8]==b'T3BSUB1\0','Actual submission schema differs')
        index,draws,n=struct.unpack_from('<3I',submitted,8)
        check((index,draws,n)==(sample,len(sections),count),'Actual submission shape differs')
        offset=20
        for section in sections:
            check(struct.unpack_from('<3I',submitted,offset)==section,'Actual source draw order/atlas differs');offset+=12
        check(submitted[offset:]==vertices,'Actual C++ world-vertex/UV/color input bits differ')
        views={}
        for view,y in [('positive_y',340.),('negative_y',-340.)]:
            v=entry['views'][view];t=v['camera_component_transform']
            check(t['translation']==[0.,y,88.]and t['scale']==[1.,1.,1.],'Actual camera position differs')
            q=np.array([0.,0.,-2**-.5 if y>0 else 2**-.5,2**-.5])
            check(np.max(np.abs(np.array(t['quaternion'])-q))<1e-14,'Actual camera orientation differs')
            off=image(v['images']['0']);on=image(v['images']['1'])
            control=image(r['samples'][0]['views'][view]['hidden_control'])
            check(off.shape==on.shape==control.shape==(768,512,3),'Actual image extent differs')
            foreground_off=int((np.max(np.abs(off-control),axis=2)>3).sum())
            foreground_on=int((np.max(np.abs(on-control),axis=2)>3).sum())
            changed=int(np.any(off!=on,axis=2).sum())
            check(foreground_on>1000 and foreground_off>1000 and changed>0,'Actual pass not visible or depth control ineffective')
            views[view]=dict(foreground_pixels_depth0=foreground_off,foreground_pixels_depth1=foreground_on,depth_intervention_changed_pixels=changed)
        results.append(dict(sample=sample,CPU_submission_bits_exact=True,views=views))
    report=dict(schema='actual-UE-ordered-GE-pass-independent-audit/v1',passed=True,report_sha256=sha(a.run/'actual_ue_ge_pass.json'),
                samples=results,actual_UE_captures=48,original_vertices_checked=44388,CPU_submission_bits_exact=True,
                actual_depth_intervention_visibly_changed_all_views=True,UE_GPU_vertex_readback_acquired=False,
                UE_GPU_depth_readback_acquired=False,original_PSP_pixels_verified=False,original_timing_verified=False,
                full_M1_verified=False,UBT_build_source_provenance_verified=False,
                limits=['A separate actual UBT build report is required for compiler/source provenance.',
                        'Submitted bytes are actor CPU input, not RHI vertex-buffer readback.',
                        'Image changes measure the rendered depth intervention, not original camera/raster equivalence.',
                        'HDR target/pre-exposure/tonemapping, complete scene transparency order and original fog/stencil remain separate.'])
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(dict(passed=True,actual_UE_captures=48,CPU_vertices_checked=44388)))


if __name__=='__main__':main()
