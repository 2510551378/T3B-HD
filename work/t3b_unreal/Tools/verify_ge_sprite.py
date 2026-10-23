"""Audit actual source rectangle geometry/GPU outputs against pinned coverage."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw


def check(v,msg):
    if not v:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def file(r):
    p=Path(r['file']);check(sha(p)==r['sha256'],'Changed evidence: '+str(p));return p


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True,type=Path);a=p.parse_args()
    out=a.run;dest=out/'independent_verification.json';check(not dest.exists(),'Never replace accepted sprite audit')
    req=read(out/'request.json');actual=read(out/'actual_gpu_report.json');start=read(out/'started.json');done=read(out/'completed.json')
    check(req['build_exit_code']==done['exit_code']==0 and actual['pid']==start['pid']==done['pid'],'GPU build/process identity differs')
    for row in req['sources']:file(row)
    check(sha(Path(req['command'][0]))==req['executable_sha256'],'Executed EXE changed')
    source=read(file(req['inputs']));raw=file(req['binary']).read_bytes();check(raw[:8]==b'T3BGEF3\0','Wrong merged geometry format')
    base_path=file(source['base_inputs']);base=read(base_path);g=read(file(source['sprite_geometry']));check(g['passed'],'Geometry source/reference checks did not pass')
    file(g['model']);sprite=read(file(g['source_inputs']));reference=read(file(g['reference']))
    check(reference['passed']and file(reference['inputs'])==file(g['source_inputs']),'Wrong pinned upstream reference pairing')
    for row in reference['sources']+reference['generated_functions']+reference['compatibility_headers']:file(row)
    file(reference['driver'])
    project=Path(__file__).resolve().parents[1];sys.path.insert(0,str(project.parent/'psp_parse/tools'))
    from extract_runtime_character import read_ppdmp
    from exact_aya_materials import iter_material_draws,decode_texture
    import ge_sprite_geometry as kernel
    parts=np.fromfile(file(reference['outputs']['parts']),dtype=kernel.PART);pixels=np.fromfile(file(reference['outputs']['candidate_pixels']),dtype=kernel.PIXEL)
    quad_data=np.fromfile(file(g['geometry']),dtype='<f4').reshape(-1,10)
    baseline=project/'Validation/ge_strip_fx_runs/eb127720dab34700b91773818e73350e';check(read(baseline/'independent_verification.json')['passed'],'Accepted base native proof missing')
    check(file(read(baseline/'request.json')['inputs'])==base_path,'Another baseline scene was merged')
    check(struct.unpack_from('<4I',raw,8)==(480,272,12,len(source['atlases'])),'Wrong full input extent')
    at=24
    for i,t in enumerate(source['atlases']):
        w,h=struct.unpack_from('<2I',raw,at);at+=8;rgba=raw[at:at+w*h*4];at+=w*h*4
        check(hashlib.sha256(rgba).hexdigest()==t['rgba_sha256']and(out/f'atlas_{i}_actual.rgba').read_bytes()==rgba,'Actual GPU atlas upload/readback differs')
    canonical=('register_record','register_word','WORLD_payload','VIEW_payload','PROJECTION_payload','flags','vertices','texture_RGBA_sha256','registers')
    frames=[];sprite_owners=[];total=0;sprite_vertices=0;candidate_masks=[]
    for i,(frame,old,gf)in enumerate(zip(source['frames'],base['frames'],g['frames'])):
        sid,n=struct.unpack_from('<2I',raw,at);at+=8;check(sid==i and n==len(frame['draws']),'Frame/source pairing differs')
        retained=[d for d in frame['draws']if d['category']!='original_rectangle_sprites']
        check([{k:d[k]for k in canonical}for d in retained]==[{k:d[k]for k in canonical}for d in old['draws']],'Original scene/state/camera/texture/order changed')
        sr=gf['source'];capture=Path(sr['capture']['path']);check(sha(capture)==sr['capture']['sha256'],'Original source capture changed')
        commands,push=read_ppdmp(str(capture));state=next(d for d in iter_material_draws(commands,push)if(d['register_record'],d['register_word'])==(sr['record'],sr['word']))
        regs=state['registers'];rgba,facts=decode_texture(state['texture0']['raw'],regs,state['clut'],state['clut_known'])
        expected_flags=1|16|256|512|4096|(regs[0x9b]<<14)|(int(regs[0xde]==6)<<15)|65536
        body=next(d for d in old['draws']if d['category']=='body');expected_flags|=int(sr['VIEW_payload']!=body['VIEW_payload']or sr['PROJECTION_payload']!=body['PROJECTION_payload'])<<7
        so=np.fromfile(out/f'sample_{i}.clip_uv_color_fog_f32',dtype='<f4').reshape(-1,11);old_so=np.fromfile(baseline/f'sample_{i}.clip_uv_color_fog_f32',dtype='<f4').reshape(-1,11);so_at=old_at=0;sprite_count=0
        for ordinal,row in enumerate(frame['draws']):
            texture,index,flags,count,ref=struct.unpack_from('<5I',raw,at);at+=20;matrix=np.frombuffer(raw,dtype='<f4',count=16,offset=at).reshape(4,4);at+=64
            fog=np.frombuffer(raw,dtype='<f4',count=4,offset=at);at+=16;fog_rgb=struct.unpack_from('<4I',raw,at);at+=16
            vertices=np.frombuffer(raw,dtype='<f4',count=count*10,offset=at).reshape(count,10);at+=count*40;output=so[so_at:so_at+count];so_at+=count;total+=count
            check((texture,index,flags,count)==(row['texture'],ordinal,row['flags'],row['vertices'])and hashlib.sha256(vertices.tobytes()).hexdigest()==row['vertex_input_sha256'],'Input layout40-byte checksum/header differs')
            if row['category']!='original_rectangle_sprites':
                prior=np.column_stack([vertices[:,:5],vertices[:,6:]]).astype('<f4')
                check(not np.any(vertices[:,5])and hashlib.sha256(prior.tobytes()).hexdigest()==row['base_vertex_input_sha256'],'Source-fog layout conversion changed retained vertices')
                check(output.tobytes()==old_so[old_at:old_at+count].tobytes(),'Retained actual GPU VS outputs changed');old_at+=count;continue
            check(flags==expected_flags and np.array_equal(matrix,np.eye(4))and not np.any(fog),'Rectangle projection/fog mode differs')
            check(row['register_record']==sr['record']and row['register_word']==sr['word']and row['registers']==sr['registers'],'Original sprite source draw/state differs')
            check(ref==(regs[0xdc]>>8)&255 and fog_rgb[:3]==tuple((regs[0xcf]>>(8*k))&255 for k in range(3)),'Original fog colour/stencil reference differs')
            check(source['atlases'][texture]['rgba_sha256']==facts['rgba_sha256']==sr['texture_RGBA_sha256'],'Actual GPU sprite CLUT material binding differs')
            first=gf['first_vertex'];check(vertices.tobytes()==quad_data[first:first+count].tobytes(),'GPU vertices differ from verified source rectangle geometry')
            expected_clip=np.column_stack([vertices[:,:3],np.ones(count,dtype='<f4')]).astype('<f4')
            check(output[:,:4].tobytes()==expected_clip.tobytes(),'Actual GPU rectangle clip changed')
            check(output[:,4:6].tobytes()==vertices[:,3:5].tobytes()and output[:,6:10].tobytes()==vertices[:,6:].tobytes()and output[:,10].tobytes()==vertices[:,5].tobytes(),'Actual GPU sprite UV/flat colour/fog changed')
            sprite_count+=1;sprite_vertices+=count;sprite_owners.append(row['owner'])
        check(sprite_count==1 and frame['draws'][-1]['category']=='original_rectangle_sprites'and so_at==len(so)and old_at==len(old_so),'Incomplete GPU source batch/retained stream')
        mask=np.zeros((272,480),dtype=bool);selected=pixels[parts['sample'][pixels['part']-1]==i];mask[selected['y'],selected['x']]=True;candidate_masks.append(mask)
        frames.append(dict(sample=i,source_rectangles=sr['source_rectangles'],generated_quad_parts=gf['emitted_quad_parts'],generated_vertices=gf['vertices'],
            source_depth_function=regs[0xde],candidate_coverage_union_pixels=int(mask.sum())))
    check(at==len(raw)and sprite_vertices==6450 and total==444555,'Wrong full recovered geometry scope')
    contract=None;contract_results=[]
    if req.get('sprite_controls'):
        contract=read(file(req['sprite_controls']));check(contract['passed']and contract['synthetic'],'Synthetic contract reference did not pass')
        file(req['control_binary']);file(contract['model']);contract_reference=read(file(contract['reference']))
        for row in contract_reference['sources']+contract_reference['generated_functions']+contract_reference['compatibility_headers']:file(row)
        file(contract_reference['driver'])
        contract_parts=np.fromfile(file(contract_reference['outputs']['parts']),dtype=kernel.PART)
        contract_pixels=np.fromfile(file(contract_reference['outputs']['candidate_pixels']),dtype=kernel.PIXEL)
    images={};records=[]
    for c in actual['captures']:
        stem=c['stem'];paths=[out/(stem+s)for s in ('.rgba','.owner_u32','.depth_stencil_u32')]
        rgb=np.fromfile(paths[0],dtype='u1').reshape(272,480,4);owner=np.fromfile(paths[1],dtype='<u4').reshape(272,480);depth=np.fromfile(paths[2],dtype='<u4').reshape(272,480)
        check(np.all(rgb[:,:,3]==255)and(stem.startswith('sprite_contract_')or np.any(owner)),'Invalid/empty actual GPU output')
        if c['mode']in('no_depth_writes','effects_only','sprites_only'):check(not np.any(depth),'No-depth-write pass altered depth/stencil')
        png=out/(stem+'.png');check(not png.exists(),'Never overwrite derived GPU PNG');Image.fromarray(rgb).save(png)
        images[stem]=(rgb,owner,depth);records.append(dict(stem=stem,rgba_sha256=sha(paths[0]),owner_sha256=sha(paths[1]),depth_stencil_sha256=sha(paths[2]),png_sha256=sha(png)))
    check(len(images)==115+(len(contract['cases'])if contract else 0),'Incomplete source/analytic/sprite-contract captures')
    for name in ('fog_control_0','fog_control_1','fog_control_2','stencil_depth_fail_control','double_source_alpha_0','double_source_alpha_1','double_source_alpha_2'):
        for suffix in ('.rgba','.owner_u32','.depth_stencil_u32'):check((out/(name+suffix)).read_bytes()==(baseline/(name+suffix)).read_bytes(),'Previously verified numeric GPU control changed')
    for i in range(12):
        rgb,owner,depth=images[f'sample_{i}_source_states'];off=images[f'sample_{i}_no_sprites'];fog=images[f'sample_{i}_no_fog']
        for index,suffix in enumerate(('.rgba','.owner_u32','.depth_stencil_u32')):check(off[index].tobytes()==(baseline/f'sample_{i}_source_states{suffix}').read_bytes(),'Disabling sprites changed accepted strip-FX baseline')
        check(np.array_equal(depth,off[2]),'Sprites changed original main depth/stencil')
        check(np.array_equal(owner,fog[1])and np.array_equal(depth,fog[2]),'Fog intervention changed ownership/depth')
        mask=owner==sprite_owners[i];changed=np.any(rgb[:,:,:3]!=off[0][:,:,:3],axis=2)
        check(np.any(mask)and np.any(changed)and not np.any(mask&~candidate_masks[i]),'Actual sprite ownership lies outside pinned upstream candidate coverage')
        check(not np.any(changed&~mask),'Colour changed outside actual surviving sprite fragments')
        isolated=images[f'sample_{i}_sprites_only'][1]>0;check(not np.any(isolated&~candidate_masks[i]),'Isolated GPU rectangle raster exceeds upstream candidate coverage')
        frames[i].update(actual_surviving_sprite_owner_pixels=int(mask.sum()),changed_RGB_pixels=int(changed.sum()))
    if contract:
        for case in contract['cases']:
            i=case['case'];rgb,owner,depth=images[f'sprite_contract_{i}'];expected_rgb=np.tile(np.array([32,64,96],dtype='u1'),(272,480,1));expected_owner=np.zeros((272,480),dtype=bool)
            data=contract_pixels[contract_parts['sample'][contract_pixels['part']-1]==i]
            check(len(data)==case['reference_pixels'],'Synthetic reference pixel count changed')
            for pixel in data:
                if case['strict_GREATER']and pixel['z']==0:continue
                x,y=int(pixel['x']),int(pixel['y']);color=int(pixel['color']);q=int(pixel['fog']);alpha=(color>>24)&255
                if alpha==0:continue
                primary=np.array([(color>>(8*k))&255 for k in range(3)],dtype=np.int64)
                shaded=((primary*q+np.array([68,112,142])*(255-q)+255)>>8).astype('<f4');a=np.float32(alpha/255)
                expected_rgb[y,x]=np.rint(shaded*a+expected_rgb[y,x].astype('<f4')*(np.float32(1)-a)).clip(0,255).astype('u1');expected_owner[y,x]=True
            error=int(np.abs(rgb[:,:,:3].astype('i2')-expected_rgb.astype('i2')).max())
            check(np.array_equal(owner>0,expected_owner)and not np.any(depth),'Synthetic rectangle GPU coverage/depth semantics differ from upstream')
            check(error<=1,'Synthetic second-vertex colour/reversed fog/ordinary D3D blend differs by >1 LSB')
            contract_results.append(dict(case=i,name=case['name'],exact_GPU_coverage_pixels=int(expected_owner.sum()),max_continuous_blend_RGB_error_LSB=error))
        check(not np.any(images['sprite_contract_11'][1])and np.any(images['sprite_contract_10'][1]),'Actual GREATER/GEQUAL at equal depth did not differ')
        prior=project/'Validation/ge_sprite_runs/2e663ad5aa23446e9dbdbf6726a4add3';check(read(prior/'independent_verification.json')['passed'],'Prior115-capture proof missing')
        for c in read(prior/'actual_gpu_report.json')['captures']:
            for suffix in('.rgba','.owner_u32','.depth_stencil_u32'):check((out/(c['stem']+suffix)).read_bytes()==(prior/(c['stem']+suffix)).read_bytes(),'Optional contract run changed accepted115 original captures')
    sheet=Image.new('RGB',(1440,1200),(22,22,22));draw=ImageDraw.Draw(sheet)
    for i in range(12):
        x=i%3*480;y=i//3*300;sheet.paste(Image.fromarray(images[f'sample_{i}_source_states'][0]).convert('RGB'),(x,y+28));draw.text((x+8,y+6),f'Sample{i}: captured scene + original rectangle sprites',fill='white')
    sheet.save(out/'CONTACT_SHEET.png')
    report=dict(schema='t3b-original-rectangle-sprite-GPU-audit/v1',passed=True,pid=actual['pid'],adapter=actual['adapter'],frames=frames,captures=len(images),synthetic_sprite_GPU_cases=contract_results,
        source_rectangles=6975,source_endpoints=13950,generated_quad_vertices=sprite_vertices,total_GPU_vertices=total,actual_GPU_atlases=len(source['atlases']),
        retained_actual_GPU_vertex_outputs_byte_identical=True,no_sprites_RGB_owner_depth_byte_identical_to_baseline=True,
        actual_sprite_coverage_subset_of_pinned_candidate_coverage=True,source_depth_GREATER_frame3_preserved=True,files=records,
        UE_executed=False,original_hardware_pixel_equivalence=False,capture_camera_dependent_sprite_geometry=True,original_clock_verified=False,
        limits=['Actual GPU raster/texture/alpha/depth/blend differs from full PSP fixed-point/D16 pipeline; upstream candidate coverage is checked before those operations.',
            'New sprite quads are capture-camera dependent; source endpoints/matrices retained for future runtime recomputation. Lines/HUD/framebuffer postprocess remain excluded.'])
    dest.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({k:report[k]for k in ('passed','source_rectangles','generated_quad_vertices','total_GPU_vertices','actual_GPU_atlases','captures')}))


if __name__=='__main__':main()
