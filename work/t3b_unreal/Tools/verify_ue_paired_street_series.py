"""Audit complete observed instance sets and UE component reuse across samples."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from verify_ue_paired_street import check,sha,read,file,image,f24


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True,type=Path);a=p.parse_args()
    folder=a.run;out=folder/'independent_street_series_verification.json';check(not out.exists(),'Refuse completed-audit overwrite')
    project=Path(__file__).resolve().parents[1];parse=project.parent/'psp_parse';sys.path.insert(0,str(parse/'tools'))
    from extract_runtime_character import read_ppdmp,layout
    from inventory_original_scene import draw_stream
    from exact_aya_materials import iter_material_draws,decode_texture
    r=read(folder/'ue_weapon_ge_paired.json');request=read(folder/'request.json');done=read(folder/'process_completed.json')
    started=read(folder/'process_started.json')
    check(r['passed']and done['exit_code']==0 and r['process_id']==done['pid']==started['pid'],'Actual process identity failed')
    check(r['run_id']==request['run_id']==started['run_id'],'Actual run identity failed')
    check(sha(folder/'capture_weapon_ge_paired_executed.py')==request['script_sha256']==r['script_sha256'],'Executed producer changed')
    report=r['paired_street'];series=read(file(report['series']));check(file(request['street_series'])==file(report['series']),'Scene series identity differs')
    helper=file(request['street_helper']);check(sha(helper)==report['helper_sha256'],'Executed scene helper differs')
    check(len(series['frames'])==len(report['frames'])==len(r['samples'])==12,'Incomplete sample coverage')
    camera_audit=read(folder/'independent_camera_verification.json');check(camera_audit['passed']and camera_audit['actual_GPU_marker_checks']==72,'Actual camera raster not verified')
    component=file(report['components']).read_bytes();indices=file(report['indices']).read_bytes();uv=file(report['uv']).read_bytes()
    expected_component_offset=expected_index_offset=expected_uv_offset=0
    input_dtype=np.dtype([('position','<f8',3),('uv','<f4',2),('color','u1',4)])
    actual_dtype=np.dtype([('position','<f8',3),('color','<f4',4)])
    origin=np.array(r['fixed_shared_PSP_world_origin']);units=r['metres_per_PSP_world_unit']
    old_scene=read(project.parent/'t3b_hd/assets/scenes/original_street/original_street.json')
    bank={d['vertex_payload_sha256']for d in old_scene['draws']}
    baseline=read(project/'Validation/original_camera_ue_runs/5a76f5096f5c46be84c5d8f1260a1f29/ue_weapon_ge_paired.json')
    rows=[];textures={};total=0;world_groups={};images=[]
    for sample,(source,actual,entry)in enumerate(zip(series['frames'],report['frames'],r['samples'])):
        check(source['sample']==actual['sample']==entry['sample']==sample,'Source/actual sample mismatch')
        snapshot=read(file(source['snapshot']));check(actual['snapshot']==source['snapshot'],'Scene bound to another snapshot')
        pp=Path(snapshot['capture']['path']);check(sha(pp)==snapshot['capture']['sha256'],'Original PPDMP changed')
        commands,push=read_ppdmp(str(pp));draws={(d['register_record'],d['register_word']):d for d in draw_stream(commands,push)}
        states={(d['register_record'],d['register_word']):d for d in iter_material_draws(commands,push)}
        observed=set();unmatched=[]
        for key,d in draws.items():
            v=d['vertex'];raw=push[v['pointer']:v['pointer']+v['bytes']]
            h=hashlib.sha256(struct.pack('<I',d['vtype'])+raw).hexdigest()
            if h in bank:observed.add(key)
            elif d['vtype']==0x11f:unmatched.append(dict(record=key[0],word=key[1],vertices=d['count'],vertex_sha256=h))
        check(observed=={(d['register_record'],d['register_word'])for d in snapshot['draws']},'Observed street instances omitted or invented')
        check(actual['draw_count']==len(observed)==len(actual['draws'])==snapshot['draw_count'],'Actual draw count differs')
        check(actual['vertices']==snapshot['vertices']and actual['inactive_buffer_slots']==140-len(observed),'Inactive buffer accounting differs')
        raw_bundle=file(snapshot['binary']).read_bytes();n,count,m=struct.unpack_from('<3I',raw_bundle,8)
        check((n,count,m)==(snapshot['draw_count'],snapshot['vertices'],81)and len(raw_bundle)==20+n*20+count*36,'Invalid scene snapshot extent')
        changed=[];rebuilt=0
        for i,(d,e)in enumerate(zip(snapshot['draws'],actual['draws'])):
            key=d['register_record'],d['register_word'];raw_draw=draws[key];state=states[key]
            check(raw_draw['world']==d['WORLD_payload']and raw_draw['view']==d['VIEW_payload']and raw_draw['proj']==d['PROJECTION_payload'],'Source matrix mismatch')
            check({hex(k):v for k,v in state['registers'].items()}==d['original_registers'],'Source PRIM register state mismatch')
            v=raw_draw['vertex'];raw=push[v['pointer']:v['pointer']+v['bytes']];stride,offs=layout(raw_draw['vtype']);count=d['vertices']
            check(raw_draw['vtype']==0x11f and raw_draw['primitive']==3 and raw_draw['count']==count,'Unsupported/changed original scene primitive')
            check(hashlib.sha256(struct.pack('<I',raw_draw['vtype'])+raw).hexdigest()==d['raw_vertex_sha256'],'Original geometry identity mismatch')
            local=np.array([struct.unpack_from('<3h',raw,k*stride+offs['pos'][0])for k in range(count)],dtype=float)/32768
            matrix=f24(raw_draw['world']).reshape(3,4,order='F');world=np.column_stack([local,np.ones(count)])@matrix.T
            expected=((world-origin)*units*100)[:,[0,2,1]]
            actual_positions=np.frombuffer(component,dtype=actual_dtype,count=count,offset=e['readback_byte_offset'])
            bridge=np.frombuffer(raw_bundle,dtype=input_dtype,count=count,offset=20+n*20+d['first_vertex']*36)
            check(np.ascontiguousarray(expected,dtype='<f8').tobytes()==actual_positions['position'].tobytes()==bridge['position'].tobytes(),'Actual/bridge source WORLD positions differ')
            colors=np.array([struct.unpack_from('<4B',raw,k*stride+8)for k in range(count)],dtype='u1')
            check(bridge['color'].tobytes()==colors.tobytes()and actual_positions['color'].tobytes()==(colors.astype(float)/255).astype('<f4').tobytes(),'Actual scene colors differ')
            raw_uv=b''.join(raw[k*stride:k*stride+8]for k in range(count))
            check(uv[e['uv_byte_offset']:e['uv_byte_offset']+count*8]==raw_uv==bridge['uv'].tobytes(),'Actual/source scene UV differs')
            check(indices[e['index_byte_offset']:e['index_byte_offset']+count*4]==np.arange(count,dtype='<u4').tobytes(),'Original triangle order/multiplicity differs')
            check((e['readback_byte_offset'],e['index_byte_offset'],e['uv_byte_offset'])==
                  (expected_component_offset,expected_index_offset,expected_uv_offset),'Readback offsets overlap or skip data')
            expected_component_offset+=count*40;expected_index_offset+=count*4;expected_uv_offset+=count*8
            check(e['buffer_slot']==i and e['vertices']==count and e['material_asset']==d['material_asset']and
                  e['actual_sort_priority']==-1000+i and e['two_sided']==(not bool(d['source_cull'])),'Component material/order/cull differs')
            check(e['component_transform']==dict(translation=[0.,0.,0.],scale=[1.,1.,1.],quaternion=[0.,0.,0.,1.]),'Scene component world transform is not identity')
            tex=state['texture0'];rgba,facts=decode_texture(tex['raw'],state['registers'],state['clut'],state['clut_known'])
            check(facts['rgba_sha256']==d['texture_rgba_sha256'],'Actual source CLUT material mismatch');textures[facts['rgba_sha256']]=rgba
            if not d['WORLD_matches_old_reference']:
                changed.append(dict(resource_sha256=d['raw_vertex_sha256'],WORLD_payload=d['WORLD_payload']))
            world_groups.setdefault(d['raw_vertex_sha256'],set()).add(tuple(d['WORLD_payload']))
            rebuilt+=int(e['geometry_rebuilt']);total+=count
        current=entry['views']['original'];prior=baseline['samples'][sample]['views']['original']
        for k in ('camera_component_transform','original_camera'):check(current[k]==prior[k],'Scene changed accepted original camera')
        for name in ('body_only','weapon_only','combined'):
            check(np.array_equal(image(current['images'][name]),image(prior['images'][name])),'Hidden scene leaks into actor control')
        street=image(current['images']['street_only']);combined=image(current['images']['street_with_aya_weapon'])
        check(street.shape==combined.shape==(272,480,4),'Rendered extent differs')
        changed_px=int((np.max(np.abs(street[:,:,:3].astype('i2')-combined[:,:,:3].astype('i2')),axis=2)>1).sum())
        check(changed_px>100,'Aya/gun missing from actual combined sample')
        images.append(combined)
        rows.append(dict(sample=sample,draws=n,vertices=snapshot['vertices'],changed_reference_world_instances=changed,
            inactive_slots=actual['inactive_buffer_slots'],rebuilt_buffer_slots=rebuilt,
            pixels_changed_by_actors=changed_px,unmatched_VTYPE_11f_draws_not_rendered=unmatched))
    check((expected_component_offset,expected_index_offset,expected_uv_offset)==(len(component),len(indices),len(uv)),'Trailing or incomplete actual stream')
    check(total==358488 and sum(row['draws']for row in rows)==1568,'Incomplete observed scene series')
    check(len(textures)==len(report['textures'])==73,'Texture coverage mismatch')
    for row in report['textures']:check(row['srgb']is False and image(row).tobytes()==textures[row['source_rgba_sha256']],'Actual Texture2D Source RGBA differs')
    old=project/'Validation/paired_street_ue_runs/f42f69bcedf741fd9515fcfc9d7a72c9/ue_weapon_ge_paired.json';old=read(old)
    for name in ('street_only','street_with_aya_weapon'):
        check(np.array_equal(image(r['samples'][0]['views']['original']['images'][name]),image(old['samples'][0]['views']['original']['images'][name])),'Sample0 street image regression')
    for row in r['protected_packages_before']:file(row)
    for row in r['new_packages']:file(row)
    check(r['all_original_packages_unchanged']and r['new_packages']==([r['other_actor']['created_material_package']]if request.get('other_actor_runtime')else[]),'Existing assets changed')
    sheet=Image.new('RGB',(1440,1200),(22,22,22));draw=ImageDraw.Draw(sheet)
    for i,im in enumerate(images):
        x=(i%3)*480;y=(i//3)*300;sheet.paste(Image.fromarray(im).convert('RGB'),(x,y+28));draw.text((x+8,y+6),f'Sample {i}: {rows[i]["draws"]} observed street draws',fill='white')
    sheet.save(folder/'STREET_CONTACT_SHEET.png')
    result=dict(schema='t3b-street-series-UE-audit/v1',passed=True,pid=r['process_id'],engine_version=r['engine_version'],samples=rows,
        scene_component_vertices=total,scene_draws=1568,Texture2D_Source_RGBA_exact=73,
        actual_GPU_camera_markers=72,geometry_resources_with_multiple_WORLD_values=sum(len(x)>1 for x in world_groups.values()),
        sample0_street_images_pixel_identical=True,original_packages_unchanged=len(r['protected_packages_before']),
        temporal_object_identity_verified=False,original_timing_verified=False,interpolation_used=False,
        source_fog_stencil_equivalence=False,source_translucent_depth_equivalence=False,formal_M1_replaced=False,
        limits=['All observed draws from the previous street bank, not all unknown source draws or a complete level.',
                'WORLD variants do not prove one persistent object moved; buffer slots are only render storage.'])
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k]for k in ('passed','scene_component_vertices','scene_draws','Texture2D_Source_RGBA_exact','geometry_resources_with_multiple_WORLD_values')}))


if __name__=='__main__':main()
