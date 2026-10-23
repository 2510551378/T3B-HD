"""Actual UE Aya/weapon replay paired by original GE dump, without socket guesses."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import traceback
import unreal

P = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
O = Path(os.environ['T3B_PAIR_REPORT']); INPUT = Path(os.environ['T3B_PAIR_INPUT'])
R = dict(schema='aya-weapon-same-ge-dump-ue-replay/v1', passed=False, samples=[], materials={},
         original_timing_verified=False, muzzle_semantics_confirmed=False, named_socket_reconstructed=False,
         original_main_depth_write_verified=False, formal_M1_replaced=False)


def check(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def flush():
    O.write_text(json.dumps(R, indent=2) + '\n', encoding='utf-8')


def note(stage):
    R['stage'] = stage; flush(); unreal.log('T3B_WEAPON_GE_PAIR ' + stage)


def inventory():
    return [dict(file=str(p), bytes=p.stat().st_size, sha256=sha(p)) for p in sorted((P / 'Content').rglob('*'))
            if p.is_file() and p.suffix.lower() in ('.uasset', '.umap', '.uexp', '.ubulk')]


def vec(v):
    return [v.x, v.y, v.z]


def transform(t):
    return dict(translation=vec(t.translation), scale=vec(t.scale3d), quaternion=[t.rotation.x, t.rotation.y, t.rotation.z, t.rotation.w])


def read_proof(path, manifest):
    proof = json.loads(path.read_text(encoding='utf-8'))
    check(proof['passed'] and proof['all_transform_color_bytes_equal'] and proof['input_sha256'] == manifest['binary']['sha256'],
          'Production-core proof has different data')
    compared = Path(proof['input_manifest']['file'])
    check(sha(compared) == proof['input_manifest']['sha256'], 'Compared input manifest changed')
    previous = json.loads(compared.read_text(encoding='utf-8'))
    check(previous['draws'] == manifest['draws'] and previous['frames'] == manifest['frames'], 'Compared series binding differs')
    for source in proof['sources']:
        check(sha(Path(source['file'])) == source['sha256'], 'Evaluated production source changed')
    for key in ('runtime_output', 'runtime_uv'):
        check(sha(Path(proof[key]['file'])) == proof[key]['sha256'], 'Compared runtime output changed')
    data = Path(proof['runtime_output']['file']).read_bytes(); uv = Path(proof['runtime_uv']['file']).read_bytes()
    check(len(data) == manifest['total_vertices'] * 32 and len(uv) == manifest['total_vertices'] * 8, 'Invalid series extent')
    check(all(data[i:i+3] == b'\0\0\0' for i in range(28, len(data), 32)), 'Secondary specular requires separate shader')
    return data, uv


def main():
    wm = json.loads(INPUT.read_text(encoding='utf-8')); check(wm['passed'] and wm['same_GE_dump_pairing'], 'Unverified original pair')
    body_input = Path(wm['paired_body_input']['file']); check(sha(body_input) == wm['paired_body_input']['sha256'], 'Paired body source changed')
    bm = json.loads(body_input.read_text(encoding='utf-8'))
    wp = Path(os.environ['T3B_PAIR_WEAPON_RUNTIME']); bp = Path(os.environ['T3B_PAIR_BODY_RUNTIME'])
    wdata, wuv = read_proof(wp, wm); bdata, buv = read_proof(bp, bm)
    R.update(input=dict(file=str(INPUT), sha256=sha(INPUT)), body_input=dict(file=str(body_input), sha256=sha(body_input)),
             runtime_proofs={name: dict(file=str(path), sha256=sha(path)) for name, path in [('body', bp), ('weapon', wp)]},
             protected_packages_before=inventory())
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world(); check(world is not None, 'No editor world')
    for actor in sub.get_all_level_actors():
        sub.destroy_actor(actor)
    body_material = unreal.load_asset('/Game/T3B/NativeCandidates/AyaCull/Run_8198e8faa071458c834fa911389cc582/M_Aya_SingleSided')
    parent = unreal.load_asset('/Game/T3B/Materials/M_Weapon_000'); check(isinstance(parent, unreal.Material), 'Missing original weapon material')
    if os.environ.get('T3B_PAIR_REUSE_MATERIAL'):
        prior_path=Path(os.environ['T3B_PAIR_REUSE_MATERIAL']);prior=json.loads(prior_path.read_text(encoding='utf-8'))
        for item in prior['new_packages']:
            check(sha(Path(item['file']))==item['sha256'],'Previously saved isolated material changed')
        weapon_material=unreal.load_asset(prior['materials']['weapon']['asset'])
        R['reused_material']=dict(report=str(prior_path),sha256=sha(prior_path),prior_acquisition_passed=prior['passed'],
                                  prior_draw_order_verification_passed=False)
    else:
        destination = '/Game/T3B/NativeCandidates/WeaponGEPaired/Run_' + R['run_id'] + '/M_Weapon_SourceCull'
        check(not unreal.EditorAssetLibrary.does_asset_exist(destination), 'Never overwrite weapon candidate')
        weapon_material = unreal.EditorAssetLibrary.duplicate_asset(parent.get_path_name(), destination)
        check(isinstance(weapon_material, unreal.Material), 'Weapon material copy failed')
        weapon_material.set_editor_property('two_sided', False)
        unreal.MaterialEditingLibrary.recompile_material(weapon_material)
        check(unreal.EditorAssetLibrary.save_loaded_asset(weapon_material, False), 'New weapon candidate save failed')
    for name, material in [('body', body_material), ('weapon', weapon_material)]:
        check(isinstance(material, unreal.Material) and material.get_editor_property('two_sided') is False, 'Source cull material missing')
        R['materials'][name] = dict(asset=material.get_path_name(), two_sided=False,
                                     blend_mode=str(material.get_editor_property('blend_mode')), shading_model=str(material.get_editor_property('shading_model')))
    tex = unreal.load_asset('/Game/T3B/Textures/T_61aae23a2efeb6a31d85abfb')
    check(isinstance(tex, unreal.Texture2D) and tex.get_editor_property('srgb') is False, 'Original weapon linear texture missing')
    R['weapon_texture'] = dict(asset=tex.get_path_name(), srgb=False,
                               width=tex.blueprint_get_size_x(), height=tex.blueprint_get_size_y())
    export_task = unreal.AssetExportTask()
    exported_texture = O.parent / 'actual_weapon_texture.png'
    for prop, value in dict(object=tex, exporter=unreal.TextureExporterPNG(), filename=str(exported_texture),
                            automated=True, prompt=False, replace_identical=False).items():
        export_task.set_editor_property(prop, value)
    check(unreal.Exporter.run_asset_export_task(export_task) and exported_texture.is_file(), 'Actual weapon texture source export failed')
    R['weapon_texture']['actual_source_png'] = dict(file=str(exported_texture), sha256=sha(exported_texture))
    actors = {}
    for name, material, priority in [('body', body_material, 0), ('weapon', weapon_material, 1)]:
        actor = sub.spawn_actor_from_class(unreal.DynamicMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), True)
        comp = actor.get_dynamic_mesh_component(); comp.set_material(0, material)
        comp.set_vertex_color_space_transform_mode(unreal.DynamicMeshVertexColorTransformMode.NO_TRANSFORM)
        comp.set_translucent_sort_priority(priority); comp.set_visibility(False, True)
        actors[name] = dict(actor=actor, component=comp, mesh=comp.get_dynamic_mesh(), built=False, priority=priority)
    camera = sub.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 340, 88), unreal.Rotator(0, 0, 0), True)
    capture = camera.get_component_by_class(unreal.SceneCaptureComponent2D)
    for prop, value in dict(capture_every_frame=False, capture_on_movement=False,
                            capture_source=unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR,
                            projection_type=unreal.CameraProjectionMode.PERSPECTIVE if os.environ.get('T3B_PAIR_CAMERAS') else unreal.CameraProjectionMode.ORTHOGRAPHIC, ortho_width=180.,
                            primitive_render_mode=unreal.SceneCapturePrimitiveRenderMode.PRM_USE_SHOW_ONLY_LIST).items():
        capture.set_editor_property(prop, value)
    for entry in actors.values():
        capture.show_only_actor_components(entry['actor'], False)
    settings = capture.get_editor_property('post_process_settings')
    for prop, value in dict(override_auto_exposure_method=True, auto_exposure_method=unreal.AutoExposureMethod.AEM_MANUAL,
                            override_auto_exposure_bias=True, auto_exposure_bias=0.,
                            override_auto_exposure_apply_physical_camera_exposure=True, auto_exposure_apply_physical_camera_exposure=False,
                            override_motion_blur_amount=True, motion_blur_amount=0., override_bloom_intensity=True, bloom_intensity=0.).items():
        settings.set_editor_property(prop, value)
    capture.set_editor_property('post_process_settings', settings)
    width,height=(480,272) if os.environ.get('T3B_PAIR_CAMERAS') else (512,768)
    target = unreal.RenderingLibrary.create_render_target2d(world, width, height, unreal.TextureRenderTargetFormat.RTF_RGBA8,
                                                          unreal.LinearColor(0, 0, 0, 1), False, False)
    capture.set_editor_property('texture_target', target)
    R['render_settings'] = dict(width=width, height=height, RHI='D3D11', target_gamma=target.get_editor_property('target_gamma'),
                                ortho_width=180., manual_exposure=0., physical_camera_exposure=False, bloom=0., motion_blur=0.)
    units = json.loads((P.parent / 'psp_parse/out/AYA_NATIVE_GLTF_20261020/aya_native.gltf').read_text(encoding='utf-8'))['nodes'][0]['scale'][0]
    first = wm['frames'][0]['paired_body_first_vertex']; source = list(struct.iter_unpack('<6f4B3Bx', bdata[first*32:(first+3456)*32]))
    origin = [(min(v[0] for v in source)+max(v[0] for v in source))/2, min(v[1] for v in source),
              (min(v[2] for v in source)+max(v[2] for v in source))/2]
    R.update(fixed_shared_PSP_world_origin=origin, metres_per_PSP_world_unit=units,
             coordinate_contract='UEcm=((world.x-origin.x),(world.z-origin.z),(world.y-origin.y))*units*100; body and gun identical conversion')
    source_camera=None
    if os.environ.get('T3B_PAIR_CAMERAS'):
        helper=Path(os.environ['T3B_PAIR_CAMERA_HELPER'])
        spec=importlib.util.spec_from_file_location('t3b_source_camera_capture',helper)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        source_camera=module.SourceCamera(os.environ['T3B_PAIR_CAMERAS'],sub,capture,world)
        R['source_camera']=source_camera.identity
        R['render_settings']['projection_type']='custom_perspective'
    street=None
    if os.environ.get('T3B_PAIR_STREET'):
        check(source_camera is not None,'Street capture requires exact original camera')
        helper=Path(os.environ['T3B_PAIR_STREET_HELPER'])
        spec=importlib.util.spec_from_file_location('t3b_paired_street_capture',helper)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        street=module.StreetSnapshot(os.environ['T3B_PAIR_STREET'],sub,capture,O.parent)
        R['paired_street']=street.identity
    other=None
    if os.environ.get('T3B_PAIR_OTHER_ACTOR_RUNTIME'):
        check(source_camera is not None and street is not None and getattr(street,'is_series',False),'Other actor requires same-sample street series')
        helper=Path(os.environ['T3B_PAIR_OTHER_ACTOR_HELPER']);spec=importlib.util.spec_from_file_location('t3b_other_actor_capture',helper)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        other=module.OtherActor(os.environ['T3B_PAIR_OTHER_ACTOR_RUNTIME'],P,O.parent,R['run_id'],sub,capture,origin,units,wm,bm,read_proof)
        R['other_actor']=other.identity
    Q = unreal.GeometryScript_MeshQueries; L = unreal.GeometryScript_List; E = unreal.GeometryScript_MeshEdits
    C = unreal.GeometryScript_VertexColors; N = unreal.GeometryScript_Normals
    readbacks = {name: (O.parent / (name + '_actual_components.bin')).open('wb') for name in actors}

    def export(name):
        file = O.parent / name; check(not file.exists(), 'Never replace actual PNG')
        unreal.AutomationLibrary.finish_loading_before_screenshot(); capture.capture_scene()
        unreal.RenderingLibrary.export_render_target(world, target, str(O.parent), name)
        check(file.is_file(), 'PNG capture missing'); return dict(file=str(file), bytes=file.stat().st_size, sha256=sha(file))

    def update(name, raw, uvraw, count, sample):
        rows = list(struct.iter_unpack('<6f4B3Bx', raw)); tex = list(struct.iter_unpack('<2f', uvraw)); entry = actors[name]
        positions = [unreal.Vector((v[0]-origin[0])*units*100, (v[2]-origin[2])*units*100, (v[1]-origin[1])*units*100) for v in rows]
        normals = [unreal.Vector(v[3], v[5], v[4]) for v in rows]; colors = [unreal.LinearColor(*[c/255 for c in v[6:10]]) for v in rows]
        dm = entry['mesh']
        if not entry['built']:
            buffers = unreal.GeometryScriptSimpleMeshBuffers()
            for prop, value in dict(vertices=positions, normals=normals, uv0=[unreal.Vector2D(*v) for v in tex], vertex_colors=colors,
                                    triangles=[unreal.IntVector(i, i+1, i+2) for i in range(0,count,3)]).items():
                buffers.set_editor_property(prop, value)
            E.append_buffers_to_mesh(dm, buffers, 0, False); entry['built'] = True
        else:
            E.set_all_mesh_vertex_positions(dm, L.convert_array_to_vector_list(positions))
            N.set_mesh_per_vertex_normals(dm, L.convert_array_to_vector_list(normals))
            C.set_mesh_per_vertex_colors(dm, L.convert_array_to_color_list(colors))
        actual = entry['component'].get_dynamic_mesh()
        check(actual == dm and Q.get_vertex_count(actual) == count and Q.get_num_triangle_i_ds(actual) == count//3, 'Actual topology changed')
        _, pl, pg = Q.get_all_vertex_positions(actual, False); _, cl, cv, cg = C.get_mesh_per_vertex_colors(actual, False)
        _, nl, nv, ng = N.get_mesh_per_vertex_normals(actual, False)
        check(cv and nv and not(pg or cg or ng), 'Actual component overlays invalid')
        pos = L.convert_vector_list_to_array(pl); col = L.convert_color_list_to_array(cl); nor = L.convert_vector_list_to_array(nl)
        check(len(pos) == len(col) == len(nor) == count, 'Actual readback count differs')
        dest = readbacks[name]; start = dest.tell()
        for v,c,n in zip(pos,col,nor):
            dest.write(struct.pack('<3d4f3f', v.x,v.y,v.z,c.r,c.g,c.b,c.a,n.x,n.y,n.z))
        result = dict(vertices=count, readback_byte_offset=start, actor_transform=transform(entry['actor'].get_actor_transform()),
                      component_transform=transform(entry['component'].get_world_transform()),
                      actual_translucency_sort_priority=entry['component'].get_editor_property('translucency_sort_priority'))
        if sample in (0,11):
            inds=bytearray();uvs=bytearray()
            for ti in range(count//3):
                iv,valid=Q.get_triangle_indices(actual,ti);check(valid,'Missing triangle');inds+=struct.pack('<3I',iv.x,iv.y,iv.z)
                a,b,c,valid=Q.get_triangle_u_vs(actual,0,ti);check(valid,'Missing UV')
                for v in (a,b,c):uvs+=struct.pack('<2f',v.x,v.y)
            result['topology_uv']={}
            for key,data in [('indices',inds),('uv',uvs)]:
                path=O.parent/(name+'_'+str(sample)+'_'+key+'.bin');path.write_bytes(data)
                result['topology_uv'][key]=dict(file=str(path),sha256=sha(path))
        return result

    try:
        for frame in (wm['frames'][:1] if street and not getattr(street,'is_series',False) else wm['frames']):
            if street and getattr(street,'is_series',False):street.select_sample(frame['sample'])
            sample=frame['sample']; bi=frame['paired_body_first_vertex']; wi=frame['first_output_vertex']
            if other:other.select_sample(sample)
            bf=bm['frames'][frame['body_frame_index']];bd=bm['draws'][bf['first_draw']:bf['first_draw']+106]
            wd=wm['draws'][frame['first_draw']];weapon_ge_command=(wd['register_record'],wd['register_word'])
            before=all((d['register_record'],d['register_word'])<weapon_ge_command for d in bd)
            after=all((d['register_record'],d['register_word'])>weapon_ge_command for d in bd)
            check(before or after,'Interleaved body/weapon PRIMs require packet-level components')
            for name,priority in [('body',0 if before else 1),('weapon',1 if before else 0)]:
                actors[name]['component'].set_translucent_sort_priority(priority)
            result=dict(sample=sample,capture=frame['capture'],actors={},views={},
                        observed_GE_order='body_then_weapon'if before else'weapon_then_body')
            result['actors']['body']=update('body',bdata[bi*32:(bi+3456)*32],buv[bi*8:(bi+3456)*8],3456,sample)
            result['actors']['weapon']=update('weapon',wdata[wi*32:(wi+243)*32],wuv[wi*8:(wi+243)*8],243,sample)
            for view,y in ([('original',None)] if source_camera else [('positive_y',340.),('negative_y',-340.)]):
                if source_camera:
                    source_camera.apply_report=source_camera.apply(camera,sample)
                else:
                    location=unreal.Vector(0,y,88);camera.set_actor_location(location,False,False)
                    camera.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(location,unreal.Vector(0,0,88)),False)
                result['views'][view]=dict(camera_component_transform=transform(capture.get_world_transform()),images={})
                if source_camera:result['views'][view]['original_camera']=source_camera.apply_report
                for mode,visible in [('hidden',()),('body_only',('body',)),('weapon_only',('weapon',)),('combined',('body','weapon'))]:
                    if mode=='hidden' and sample!=0:continue
                    for name,entry in actors.items():entry['component'].set_visibility(name in visible,True)
                    result['views'][view]['images'][mode]=export('%02d_%s_%s.png'%(sample,view,mode))
                if source_camera:
                    for entry in actors.values():entry['component'].set_visibility(False,True)
                    _,positions,gaps=Q.get_all_vertex_positions(actors['body']['mesh'],False)
                    check(not gaps,'Marker source has vertex gaps')
                    result['views'][view]['marker_control']=source_camera.markers(sample,L.convert_vector_list_to_array(positions),export)
                if street:
                    check(sample==street.data['source_sample'],'Never mix street snapshot with another sample')
                    street.show(True)
                    for name,entry in actors.items():entry['component'].set_visibility(False,True)
                    result['views'][view]['images']['street_only']=export('%02d_original_street_only.png'%sample)
                    for entry in actors.values():entry['component'].set_visibility(True,True)
                    result['views'][view]['images']['street_with_aya_weapon']=export('%02d_original_street_with_aya_weapon.png'%sample)
                    street.show(False)
                if other:
                    for entry in actors.values():entry['component'].set_visibility(False,True)
                    other.show(True)
                    result['views'][view]['images']['other_actor_only']=export('%02d_original_other_actor_only.png'%sample)
                    street.show(True)
                    for entry in actors.values():entry['component'].set_visibility(True,True)
                    result['views'][view]['images']['street_with_all_original_actors']=export('%02d_original_street_with_all_actors.png'%sample)
                    other.show(False);street.show(False)
            R['samples'].append(result);note('sample_'+str(sample))
    finally:
        for file in readbacks.values():file.close()
    R['readbacks']={name:dict(file=str(Path(file.name)),sha256=sha(Path(file.name)),stride=52,format='<3d4f3f') for name,file in readbacks.items()}
    check(len(R['samples'])==(1 if street and not getattr(street,'is_series',False) else 12),'Incomplete actual paired replay');R['passed']=True


if __name__=='__main__':
    R.update(run_id=os.environ['T3B_PAIR_RUN'],process_id=os.getpid(),script_sha256=sha(Path(__file__)),engine_version=unreal.SystemLibrary.get_engine_version())
    try:main()
    except Exception as error:R.update(error=str(error),traceback=traceback.format_exc());unreal.log_error(str(error))
    finally:
        if 'protected_packages_before'in R:
            after=inventory();R['packages_after']=after;lookup={i['file']:i for i in after}
            R['all_original_packages_unchanged']=all(lookup.get(i['file'])==i for i in R['protected_packages_before'])
            R['new_packages']=[i for i in after if i['file']not in{v['file']for v in R['protected_packages_before']}]
            if not R['all_original_packages_unchanged']:R['passed']=False
        flush()
    if not R['passed']:raise RuntimeError(R.get('error','Paired GE replay failed'))
