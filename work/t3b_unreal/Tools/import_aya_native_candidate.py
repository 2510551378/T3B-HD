"""Actual built-in UE glTF import into a fresh, isolated candidate namespace.

Run by the hidden commandlet wrapper. Existing161 packages and source glTF/bin
are fingerprinted before/after. This never replaces the PMC source replay.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import unreal

PROJECT=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
RUN=os.environ['T3B_NATIVE_RUN_ID']
OUTPUT=Path(os.environ['T3B_NATIVE_REPORT_PATH']).resolve()
GLTF=Path(os.environ['T3B_NATIVE_GLTF']).resolve()
CANDIDATE_KIND=os.environ.get('T3B_NATIVE_CANDIDATE_KIND','original')
DESTINATION='/Game/T3B/NativeCandidates/'+('AyaCompact'if CANDIDATE_KIND=='compact'else'Aya')+'/Run_'+RUN
ASSETS=unreal.EditorAssetLibrary
RESULT={'schema':'t3b-ue-native-gltf-import/v1','native_import_completed':False,'native_structure_verified':False,'verified_source_material_bound':False,
        'destination':DESTINATION,'source_runtime_replaced':False,'UE_skinning_vertex_numeric_verified':False,
        'ue_render_verified':False,'ue_gameplay_executed':False,'ue_cpp_build_executed':False}
EXPECTED_GLTF=os.environ.get('T3B_NATIVE_EXPECTED_GLTF','93c78d4014a2255b15915f8150868d1654718b256a72995f25966581a578a4f7')
EXPECTED_BIN=os.environ.get('T3B_NATIVE_EXPECTED_BIN','8ce1805dcaf6cdb8f73c0d2d2784a8d20f0e611fbb2d144d0a2d025d839d8454')


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def must(value,message):
    if not value:raise RuntimeError(message)


def old_packages():
    report=PROJECT/'Validation/asset_import_runs/0fac54502ca140d4accffa2e5a7bc618/ue_editor_asset_creation.json'
    frozen=json.loads(report.read_text(encoding='utf-8'));checks=[]
    for saved in frozen['saved_assets']:
        path=Path(saved['file']);must(path.is_file()and digest(path)==saved['sha256'],f'Existing verified package changed: {path}')
        checks.append({'file':str(path),'sha256':saved['sha256']})
    must(len(checks)==161,'Expected existing161 verified packages')
    prior=PROJECT/'Validation/native_import_runs/64e9826c75854a7ba8f7f36eabefb4cf/ue_native_import.json'
    if prior.is_file():
        for saved in json.loads(prior.read_text(encoding='utf-8'))['saved_native_packages']:must(digest(Path(saved['file']))==saved['sha256'],'Old native candidate changed')
    fixed=PROJECT.parent/'psp_parse/out/AYA_NATIVE_GLTF_20261020'
    must(digest(fixed/'aya_native.gltf')=='93c78d4014a2255b15915f8150868d1654718b256a72995f25966581a578a4f7'and digest(fixed/'aya_native.bin')=='8ce1805dcaf6cdb8f73c0d2d2784a8d20f0e611fbb2d144d0a2d025d839d8454','Frozen original glTF/bin changed')
    return checks


def transform_dict(value):
    t=value.translation;q=value.rotation;s=value.scale3d
    return {'translation':[float(t.x),float(t.y),float(t.z)],'quaternion_xyzw':[float(q.x),float(q.y),float(q.z),float(q.w)],
            'scale':[float(s.x),float(s.y),float(s.z)]}


def inspect_mesh(mesh,gltf):
    component=unreal.SkeletalMeshComponent()
    component.set_skinned_asset_and_update(mesh,False)
    count=component.get_num_bones();names=[str(component.get_bone_name(i))for i in range(count)]
    parents={name:str(component.get_parent_bone(name))for name in names}
    rows=[];expected_parent=gltf['skins'][0]['extras']['source_parent']
    for index in range(44):
        name=f'source_bone_{index:02d}';expected=f'source_bone_{expected_parent[index]:02d}'if expected_parent[index]>=0 else'Source_skeleton_root'
        actual_index=component.get_bone_index(name)
        rows.append({'source_index':index,'expected_name':name,'UE_bone_index':actual_index,'parent':parents.get(name),
                     'expected_source_parent_name':expected,'present':actual_index>=0,'parent_matches_source':parents.get(name)==expected})
    skeleton=mesh.get_editor_property('skeleton')
    information={'asset':mesh.get_path_name(),'skeleton':skeleton.get_path_name()if skeleton else None,'bone_count':count,'bone_names':names,
        'root_bones':[name for name,parent in parents.items()if parent in ['None','']],'bone_parents':parents,'source44_mapping':rows,
        'all44_source_indices_present':all(r['present']for r in rows),'all44_parent_links_match':all(r['parent_matches_source']for r in rows),
        'LOD_count':unreal.SkeletalMeshEditorSubsystem.get_lod_count(mesh)}
    information['actual_asset_reference_pose']=[{'bone':name,'index':i,**transform_dict(component.get_ref_pose_transform(i))}for i,name in enumerate(names)]
    information['reference_pose_API']='USkinnedMeshComponent::GetRefPoseTransform directly reads asset RefSkeleton.GetRefBonePose, SkinnedMeshComponent.cpp:2727; component registration is not required.'
    information['reference_pose_coordinate_limit']='Native importer axes must be reconciled with PMC ToUE=(pc.z,-pc.x,pc.y)*100 before runtime replacement; no axis correction was applied.'
    return information


def inspect_animation(animation,mesh,gltf):
    lib=unreal.AnimationLibrary
    length=float(lib.get_sequence_length(animation));frames=int(lib.get_num_frames(animation))
    tracks=[str(n)for n in lib.get_animation_track_names(animation)]
    expected=json.loads((GLTF.parent/'provenance.json').read_text(encoding='utf-8'))['actual_times_seconds']
    result={'asset':animation.get_path_name(),'sequence_length_seconds':length,'frame_count':frames,
        'track_names':tracks,'track_count':len(tracks),'source_time_count':len(expected),'source_length_seconds':expected[-1],
        'length_difference_seconds':length-expected[-1],'source44_tracks_present':all(f'source_bone_{i:02d}'in tracks for i in range(44))}
    try:
        model=animation.get_editor_property('data_model_interface')
        result['data_model']={'frame_rate':str(model.get_frame_rate()),'keys':model.get_number_of_keys(),'frames':model.get_number_of_frames(),'length':model.get_play_length()}
    except Exception as error:result['data_model_query_unavailable']=str(error)
    try:
        names=['Source_skeleton_root']+[f'source_bone_{i:02d}'for i in range(44)]
        samples=[]
        for time in [0.,length/2,length]:
            poses=lib.get_bone_poses_for_time(animation,names,time,False,mesh)
            samples.append({'seconds':time,'local_bone_transforms':[{'bone':name,**transform_dict(pose)}for name,pose in zip(names,poses)]})
        result['actual_animation_local_transform_probes']=samples
        root_pose=samples[0]['local_bone_transforms'][0]
        expected_units=gltf['nodes'][0]['scale'][0]
        result['synthetic_root_scale']=root_pose['scale']
        result['synthetic_root_contains_canonical_scale']=all(abs(s-expected_units)<1e-6 for s in root_pose['scale'])
        result['native_axis_observation']='Local source translation (x,y,z) is imported as (100*x,100*z,100*y); enclosing canonical uniform scale is retained in the synthetic root. This differs from the custom PMC axis permutation and must be reconciled before runtime replacement.'
    except Exception as error:result['bone_transform_query_unavailable']=str(error)
    return result


def bind_verified_source_material(mesh,gltf):
    manifest_path=PROJECT/'Content/SourceData/manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    aya=next(a for a in manifest['actors']if a['name']=='Aya')
    must(len(aya['materials'])==1 and len(gltf['materials'])==1,'Expected one explicitly identified Aya material')
    item=aya['materials'][0];source=gltf['materials'][0];ge=source['extras']['original_GE_parameters']
    primitives=gltf['meshes'][0]['primitives']
    must(len(primitives)==106 and all(p['material']==0 for p in primitives),'Source primitive material mapping changed')
    must(source['extras']['source_material_id']=='506dc44780fe0539edee976e3b5607b1a1c90b933d900fb605751cda42497657','Source material identity differs')
    must(item['asset']=='/Game/T3B/Materials/M_Aya_000.M_Aya_000','Expected frozen verified Aya material')
    texture_item=next(t for t in manifest['textures']if t['asset']==item['texture_asset'])
    native_png=GLTF.parent/gltf['images'][0]['uri'];staged_png=PROJECT/'Content/SourceData'/item['texture']
    must(digest(native_png)==digest(staged_png)==texture_item['container']['sha256'],'Candidate and verified PNG bytes differ')
    must(texture_item['rgba_sha256']=='15d1850ff7828d8c60989b9115f741139df8795659a9e142d9cd3c5ebe857955','Original RGBA identity differs')
    must([item['su'],item['sv']]==ge['uv_scale']and [item['ou'],item['ov']]==ge['uv_offset'],'UV transform differs')
    must(item['rgb_scale']==2 and ge['color_double']and item['alpha_ref']==ge['alpha_test_ref']==0,'Double RGB/alpha reference differs')
    must(item['alpha_test']and ge['alpha_test_enabled']and ge['alpha_test_function']==6,'Expected strict greater alpha test')
    must(bool(item['blend'])==ge['alpha_blend_enabled']and item['wrap_s']==item['wrap_t']==0 and ge['wrap_u']==ge['wrap_v']=='repeat','Blend/wrap differs')
    material=ASSETS.load_asset(item['asset']);texture=ASSETS.load_asset(item['texture_asset'])
    must(isinstance(material,unreal.Material)and isinstance(texture,unreal.Texture2D),'Verified material or texture cannot load')
    frozen=json.loads((PROJECT/'Validation/asset_import_runs/0fac54502ca140d4accffa2e5a7bc618/ue_editor_asset_creation.json').read_text(encoding='utf-8'))
    signature=ASSETS.get_metadata_tag(material,'T3BMaterialSignature')
    must(signature==frozen['material_recipe_signatures'][item['asset']],'Verified material recipe signature differs')
    must(ASSETS.get_metadata_tag(texture,'T3BSourceRGBA')==texture_item['rgba_sha256'],'Actual Texture2D source RGBA metadata differs')
    samples=[n for n in unreal.MaterialEditingLibrary.get_material_expressions(material)if isinstance(n,unreal.MaterialExpressionTextureSample)]
    must(len(samples)==1 and samples[0].get_editor_property('texture')==texture,'Actual material TextureSample reference differs')
    slots=list(mesh.get_editor_property('materials'))
    subsystem=unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    section_slots=[[subsystem.get_lod_material_slot(mesh,lod,section)for section in range(subsystem.get_num_sections(mesh,lod))]for lod in range(subsystem.get_lod_count(mesh))]
    slot_info=[{'slot':i,'name':str(slot.get_editor_property('material_slot_name')),
        'imported_name':str(slot.get_editor_property('imported_material_slot_name')),
        'previous_material':slot.get_editor_property('material_interface').get_path_name()if slot.get_editor_property('material_interface')else None}for i,slot in enumerate(slots)]
    RESULT['material_binding_pending']={'actual_slots':slot_info,'actual_LOD_section_slots':section_slots}
    must(len(slots)==1 and all(index==0 for indices in section_slots for index in indices)and all(section_slots),'Actual UE slots/sections cannot be uniquely mapped to source material0')
    must(slot_info[0]['imported_name']==source['name']or slot_info[0]['name']==source['name'],'Actual native slot name does not identify frozen source material0')
    slots[0].set_editor_property('material_interface',material)
    mesh.set_editor_property('materials',slots)
    must(ASSETS.save_loaded_asset(mesh,False),'Could not save new candidate material binding')
    must(mesh.get_editor_property('materials')[0].get_editor_property('material_interface')==material,'Saved candidate material reference differs')
    RESULT['verified_source_material_bound']=True
    return {'source_material_index':0,'source_material_id':source['extras']['source_material_id'],'source_primitives':106,
        'native_slots_before_binding':slot_info,'actual_LOD_section_slots':section_slots,'bound_UE_slot':0,'bound_material':material.get_path_name(),
        'texture':texture.get_path_name(),'rgba_sha256':texture_item['rgba_sha256'],'identical_native_and_staged_PNG_sha256':digest(native_png),
        'frozen_recipe_signature':signature,'manifest_material':item,'source_GE_parameters':ge,
        'limits':['Original GE cull=true differs from verified C baseline two_sided=true.',
            'Original blend main-pass depth writes are unsupported by standard UE translucent material.',
            'Native glTF has no animated COLOR_0 face shade; existing material RGB*vertexRGB*2 does not by itself reproduce C posed-face light. Appearance is not accepted.',
            'Binding reuses read-only verified source material; it does not modify old material or texture packages.']}


def main():
    must(OUTPUT.is_relative_to(PROJECT/'Validation'),'Report outside project Validation')
    must(digest(GLTF)==EXPECTED_GLTF and digest(GLTF.parent/'aya_native.bin')==EXPECTED_BIN,'Frozen glTF/bin input identity differs')
    gltf=json.loads(GLTF.read_text(encoding='utf-8'));before=old_packages()
    must(not ASSETS.does_directory_exist(DESTINATION),'New run destination must not already exist; never overwrite prior candidates')
    RESULT['candidate_kind']=CANDIDATE_KIND
    RESULT.update(source_gltf={'file':str(GLTF),'sha256':EXPECTED_GLTF},source_bin_sha256=EXPECTED_BIN,
        source_glTF_vertices=3456,source_primitives=106,source_original_bones=44,source_synthetic_joint=1,source_time_count=60)
    pipeline=unreal.InterchangeGenericAssetsPipeline()
    mesh_pipeline=pipeline.get_editor_property('mesh_pipeline')
    mesh_pipeline.set_editor_property('import_skeletal_meshes',True)
    mesh_pipeline.set_editor_property('import_static_meshes',False)
    mesh_pipeline.set_editor_property('create_physics_asset',False)
    animation_pipeline=pipeline.get_editor_property('animation_pipeline')
    animation_pipeline.set_editor_property('import_animations',True)
    animation_pipeline.set_editor_property('import_bone_tracks',True)
    animation_pipeline.set_editor_property('use30_hz_to_bake_bone_animation',False)
    animation_pipeline.set_editor_property('custom_bone_animation_sample_rate',0)
    material_pipeline=pipeline.get_editor_property('material_pipeline')
    material_pipeline.set_editor_property('import_materials',False)
    material_pipeline.get_editor_property('texture_pipeline').set_editor_property('import_textures',False)
    stack=unreal.InterchangePipelineStackOverride();stack.add_pipeline(pipeline)
    RESULT['pipeline_policy']={'class':pipeline.get_class().get_path_name(),'import_skeletal_meshes':True,'import_static_meshes':False,
        'create_physics_asset':False,'import_animations':True,'import_bone_tracks':True,'custom_bone_animation_sample_rate':0,
        'use30_hz_to_bake_bone_animation':False,'frame_alignment':str(animation_pipeline.get_editor_property('frame_alignment')),
        'import_offset_uniform_scale':float(pipeline.get_editor_property('import_offset_uniform_scale')),
        'import_materials':False,'import_textures':False,
        'material_limit':'Official glTF material generation is disabled after preserved MF_Unlit_Body AlphaMode error; candidate binds the separately verified original Aya material after explicit source/slot checks.'}
    task=unreal.AssetImportTask()
    for key,value in {'filename':str(GLTF),'destination_path':DESTINATION,'automated':True,'replace_existing':False,'save':True,'options':stack}.items():task.set_editor_property(key,value)
    RESULT['import_attempted']=True
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported=list(task.get_objects())
    paths=[str(p)for p in ASSETS.list_assets(DESTINATION,True,False)]
    assets=[ASSETS.load_asset(path)for path in paths]
    must(all(asset is not None for asset in assets),'Some imported candidate assets cannot be loaded')
    RESULT['created_assets']=[{'asset':a.get_path_name(),'class':a.get_class().get_path_name()}for a in assets]
    RESULT['task_imported_objects']=[a.get_path_name()for a in imported]
    RESULT['native_import_completed']=bool(assets)
    meshes=[a for a in assets if isinstance(a,unreal.SkeletalMesh)]
    skeletons=[a for a in assets if isinstance(a,unreal.Skeleton)]
    animations=[a for a in assets if isinstance(a,unreal.AnimSequence)]
    RESULT['native_class_counts']={'SkeletalMesh':len(meshes),'Skeleton':len(skeletons),'AnimSequence':len(animations),'all_assets':len(assets)}
    must(meshes and skeletons and animations,'Importer did not create SkeletalMesh +Skeleton +AnimSequence; see logs/partial candidate namespace')
    RESULT['skeletal_meshes']=[inspect_mesh(mesh,gltf)for mesh in meshes]
    RESULT['animations']=[inspect_animation(animation,meshes[0],gltf)for animation in animations]
    RESULT['material_bindings']=[bind_verified_source_material(mesh,gltf)for mesh in meshes]
    saved=[]
    for a in assets:
        package=a.get_path_name().split('.',1)[0]
        must(package.startswith(DESTINATION+'/'),'Imported asset escaped isolated candidate namespace')
        file=(PROJECT/'Content'/package[len('/Game/'):]).with_suffix('.uasset')
        must(file.is_file()and file.stat().st_size>0,f'Imported native package not saved: {file}')
        saved.append({'asset':a.get_path_name(),'file':str(file),'bytes':file.stat().st_size,'sha256':digest(file)})
    RESULT['saved_native_packages']=saved
    must(before==old_packages(),'Native import changed one of the prior161 verified packages')
    RESULT['previous161_packages_unchanged']=True
    RESULT['source_inputs_unchanged']=digest(GLTF)==EXPECTED_GLTF and digest(GLTF.parent/'aya_native.bin')==EXPECTED_BIN
    RESULT['native_structure_verified']=all(m['all44_source_indices_present']and m['all44_parent_links_match']for m in RESULT['skeletal_meshes'])
    RESULT['limits']=['Built-in Interchange import and structural checks only; PMC source replay is not replaced.',
        'Native candidate binds verified original Aya material/texture; actual GPU appearance and animated vertex face shade remain unverified.',
        'Native GPU pixels, materials, culling, transparency and blend/main-depth-write equivalence are not verified under NullRHI.',
        'Imported animation may resample original irregular60 timestamps; actual imported duration/frame/track values are reported.',
        'Source glTF keyframe difference0.0174cm and C GE-affine midpoint difference3.117cm are pre-import candidate evidence, not imported UE vertex validation.',
        'Actual PSP unobserved subframe motion is not measured by C-affine interpolation comparisons.',
        'GetCPUSkinnedVertices is native C++ without UFUNCTION in the installed engine; this Python route does not claim native skinning vertex numeric acceptance.',
        'Material textures are original resolution; this is not HD texture reconstruction or a playable UE battle.']
    return RESULT


if __name__=='__main__':
    started=datetime.now(timezone.utc).isoformat()
    try:main()
    except Exception as error:
        RESULT['error']=str(error)
        raise
    finally:
        try:RESULT['previous161_packages_unchanged_final_check']=len(old_packages())==161
        except Exception as error:RESULT['previous_package_check_error']=str(error)
        RESULT.update(run_id=RUN,process_id=os.getpid(),started_utc=started,finished_utc=datetime.now(timezone.utc).isoformat(),
            project_file=unreal.Paths.get_project_file_path(),engine_version=unreal.SystemLibrary.get_engine_version(),
            command_line=unreal.SystemLibrary.get_command_line(),import_script_sha256=digest(Path(__file__)))
        OUTPUT.parent.mkdir(parents=True,exist_ok=True);OUTPUT.write_text(json.dumps(RESULT,indent=2)+'\n',encoding='utf-8')
