"""Actual UE RHI A/B of one recorded static pose, white versus GE vertex light.

Not an animation/gameplay replacement. Original packages/materials are read-only;
only two isolated calibration StaticMeshes may be saved.
"""
import hashlib,json,os,struct,traceback
from pathlib import Path
import unreal

P=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
O=Path(os.environ['T3B_LIGHT_REPORT']);INPUT=Path(os.environ['T3B_LIGHT_INPUT']);RUN=os.environ['T3B_LIGHT_RUN']
R={'schema':'aya-ge-lighting-calibration-rhi/v1','passed':False,'images':[],'meshes':[],
   'static_snapshot_only':True,'animation_replaced':False,'original_pixels_verified':False}


def check(ok,message):
    if not ok:raise RuntimeError(message)


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def flush():O.write_text(json.dumps(R,indent=2)+'\n',encoding='utf-8')
def note(stage):R['stage']=stage;flush();unreal.log('T3B_GE_LIGHT '+stage)
def vec(v):return [v.x,v.y,v.z]
def transform(t):return dict(translation=vec(t.translation),scale=vec(t.scale3d),quaternion=[t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w])
def inventory():return [dict(file=str(p),bytes=p.stat().st_size,sha256=sha(p))for p in sorted((P/'Content').rglob('*'))if p.is_file()and p.suffix.lower()in('.uasset','.umap','.uexp','.ubulk')]


def main():
    pair=json.loads(INPUT.read_text(encoding='utf-8'));check(pair['passed'],'Unverified lighting calibration input')
    R['input']=dict(file=str(INPUT),sha256=sha(INPUT));R['protected_packages_before']=inventory()
    reuse=None
    if os.environ.get('T3B_LIGHT_REUSE_REPORT'):
        reuse_path=Path(os.environ['T3B_LIGHT_REUSE_REPORT']);reuse=json.loads(reuse_path.read_text(encoding='utf-8'))
        check(reuse['input']['sha256']==sha(INPUT),'Reused calibration has different inputs')
        for saved in reuse['new_packages']:check(sha(Path(saved['file']))==saved['sha256'],'Reused calibration package changed')
        R['reused_saved_calibration']=dict(report=str(reuse_path),sha256=sha(reuse_path),prior_passed=reuse['passed'])
    material=unreal.load_asset('/Game/T3B/NativeCandidates/AyaCull/Run_8198e8faa071458c834fa911389cc582/M_Aya_SingleSided')
    check(isinstance(material,unreal.Material)and material.get_editor_property('two_sided')is False,'Missing tested single-sided source material')
    R['material']=dict(asset=material.get_path_name(),two_sided=False,blend_mode=str(material.get_editor_property('blend_mode')),
                       shading_model=str(material.get_editor_property('shading_model')))
    R['query_API_docs']={name:getattr(unreal.GeometryScript_VertexColors,name).__doc__ for name in ['get_mesh_per_vertex_colors']}
    actors={};world=unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
    sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for item in pair['snapshots']:
        mode=item['mode'];file=Path(item['gltf']);check(sha(file)==item['gltf_sha256']and sha(file.parent/'pose.bin')==item['binary_sha256'],'Calibration source changed')
        if reuse:
            matches=[x for x in reuse['meshes']if x['mode']==mode];check(len(matches)==1,'Ambiguous reused calibration mesh')
            mesh=unreal.load_asset(matches[0]['asset']);check(isinstance(mesh,unreal.StaticMesh),'Reused calibration did not reload')
            if os.environ.get('T3B_LIGHT_DISABLE_NANITE')=='1':
                destination='/Game/T3B/NativeCandidates/AyaLightingNoNanite/Run_'+RUN+'/'+mode+'/aya_'+mode+'_calibration'
                check(not unreal.EditorAssetLibrary.does_asset_exist(destination),'Never replace Nanite control')
                mesh=unreal.EditorAssetLibrary.duplicate_asset(mesh.get_path_name(),destination)
                before=mesh.get_editor_property('nanite_settings')
                check(before.get_editor_property('enabled')is True,'Expected actual Nanite-enabled control')
                editor=unreal.StaticMeshEditorSubsystem()
                settings=editor.get_nanite_settings(mesh);settings.set_editor_property('enabled',False)
                editor.set_nanite_settings(mesh,settings,True)
                check(mesh.get_editor_property('nanite_settings').get_editor_property('enabled')is False,'Nanite disable readback failed')
                check(unreal.EditorAssetLibrary.save_loaded_asset(mesh,False),'Isolated non-Nanite save failed')
                R.setdefault('nanite_changes',[]).append(dict(mode=mode,source=matches[0]['asset'],derived=mesh.get_path_name(),
                    before_enabled=True,after_enabled=False,official_setter='StaticMeshEditorSubsystem.set_nanite_settings'))
        else:
            destination='/Game/T3B/NativeCandidates/AyaLighting/Run_'+RUN+'/'+mode
            check(not unreal.EditorAssetLibrary.does_directory_exist(destination),'Never overwrite calibration asset')
            pipeline=unreal.InterchangeGenericAssetsPipeline();mp=pipeline.get_editor_property('mesh_pipeline')
            mp.set_editor_property('import_skeletal_meshes',False);mp.set_editor_property('import_static_meshes',True)
            pipeline.get_editor_property('animation_pipeline').set_editor_property('import_animations',False)
            mat=pipeline.get_editor_property('material_pipeline');mat.set_editor_property('import_materials',False)
            mat.get_editor_property('texture_pipeline').set_editor_property('import_textures',False)
            stack=unreal.InterchangePipelineStackOverride();stack.add_pipeline(pipeline)
            task=unreal.AssetImportTask()
            for key,value in dict(filename=str(file),destination_path=destination,automated=True,replace_existing=False,save=True,options=stack).items():task.set_editor_property(key,value)
            note('import_'+mode);unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
            assets=[unreal.load_asset(x)for x in unreal.EditorAssetLibrary.list_assets(destination,True,False)]
            check(len(assets)==1 and isinstance(assets[0],unreal.StaticMesh),'Expected exactly one isolated StaticMesh')
            mesh=assets[0];check(len(mesh.get_editor_property('static_materials'))==1,'Expected one uniquely bound source material')
            mesh.set_material(0,material);check(unreal.EditorAssetLibrary.save_loaded_asset(mesh,False),'Calibration mesh save failed')
        actor=sub.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(0,0,0),unreal.Rotator(0,0,0),True)
        comp=actor.get_component_by_class(unreal.StaticMeshComponent);comp.set_static_mesh(mesh);comp.set_visibility(False,True)
        check(comp.get_material(0)==material,'Saved default material differs')
        actors[mode]=(actor,comp)
        R['meshes'].append(dict(mode=mode,asset=mesh.get_path_name(),actor_transform=transform(actor.get_actor_transform())))
    capture_actor=sub.spawn_actor_from_class(unreal.SceneCapture2D,unreal.Vector(0,340,88),unreal.Rotator(0,0,0),True)
    capture=capture_actor.get_component_by_class(unreal.SceneCaptureComponent2D)
    for prop,val in dict(capture_every_frame=False,capture_on_movement=False,capture_source=unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR,
                         projection_type=unreal.CameraProjectionMode.ORTHOGRAPHIC,ortho_width=180.,primitive_render_mode=unreal.SceneCapturePrimitiveRenderMode.PRM_USE_SHOW_ONLY_LIST).items():capture.set_editor_property(prop,val)
    for actor,_ in actors.values():capture.show_only_actor_components(actor,False)
    settings=capture.get_editor_property('post_process_settings')
    for prop,val in dict(override_auto_exposure_method=True,auto_exposure_method=unreal.AutoExposureMethod.AEM_MANUAL,
                         override_auto_exposure_bias=True,auto_exposure_bias=0.,override_auto_exposure_apply_physical_camera_exposure=True,
                         auto_exposure_apply_physical_camera_exposure=False,override_motion_blur_amount=True,motion_blur_amount=0.,override_bloom_intensity=True,bloom_intensity=0.).items():settings.set_editor_property(prop,val)
    capture.set_editor_property('post_process_settings',settings)
    target=unreal.RenderingLibrary.create_render_target2d(world,768,1024,unreal.TextureRenderTargetFormat.RTF_RGBA8,unreal.LinearColor(0,0,0,1),False,False)
    capture.set_editor_property('texture_target',target)
    R['render_settings']=dict(width=768,height=1024,capture_source=str(capture.get_editor_property('capture_source')),
        target_format=str(target.get_editor_property('render_target_format')),target_gamma=target.get_editor_property('target_gamma'),
        manual_exposure=0.,physical_camera_exposure=False,bloom=0.,motion_blur=0.,RHI='D3D11')
    note('wait_for_actual_shader_compilation');unreal.AutomationLibrary.finish_loading_before_screenshot()
    def export(name):
        file=O.parent/name;check(not file.exists(),'Never replace capture PNG')
        capture.capture_scene();unreal.RenderingLibrary.export_render_target(world,target,str(O.parent),name)
        check(file.is_file(),'Actual capture did not export');return dict(file=str(file),bytes=file.stat().st_size,sha256=sha(file))
    for view,location in [('front',[0.,340.,88.]),('back',[0.,-340.,88.])]:
        v=unreal.Vector(*location);rotation=unreal.MathLibrary.find_look_at_rotation(v,unreal.Vector(0,10,88))
        capture_actor.set_actor_location(v,False,False);capture_actor.set_actor_rotation(rotation,False)
        empty=export(view+'_hidden_control.png')
        for mode,(actor,component)in actors.items():
            component.set_visibility(True,True);note('capture_'+mode+'_'+view)
            unreal.AutomationLibrary.finish_loading_before_screenshot()
            item=dict(mode=mode,view=view,camera_component_transform=transform(capture.get_world_transform()),
                      actor_transform=transform(actor.get_actor_transform()),empty_control=empty,png=export(mode+'_'+view+'.png'))
            R['images'].append(item);component.set_visibility(False,True);flush()
    # Read actual RenderData color overlays after image acquisition, retaining any
    # API failure rather than substituting source COLOR_0 as an imported result.
    for entry in R['meshes']:
        component=actors[entry['mode']][1];dm=unreal.DynamicMesh()
        options=unreal.GeometryScriptCopyMeshFromComponentOptions();lod=unreal.GeometryScriptMeshReadLOD()
        lod.set_editor_property('lod_type',unreal.GeometryScriptLODType.RENDER_DATA);lod.set_editor_property('lod_index',0)
        options.set_editor_property('requested_lod',lod)
        _,_,outcome=unreal.GeometryScript_SceneUtils.copy_mesh_from_component(component,dm,options,False)
        check(outcome==unreal.GeometryScriptOutcomePins.SUCCESS,'Actual static render-data copy failed')
        query=unreal.GeometryScript_VertexColors.get_mesh_per_vertex_colors(dm,False)
        R['color_query_return_types']=[type(x).__name__ for x in query];flush()
        _,colors,valid,gaps=query
        entry.update(actual_color_overlay_valid=valid,actual_color_vertex_id_gaps=gaps)
        if entry['mode']=='white'and not valid:
            entry['color_readback_boundary']='White control has no exported RenderData color overlay; no colors synthesized into this report.'
            continue
        check(valid and not gaps,'Invalid/gapped reconstructed-light color overlay')
        array=unreal.GeometryScript_List.convert_color_list_to_array(colors)
        rows=[[c.r,c.g,c.b,c.a]for c in array]
        path=O.parent/(entry['mode']+'_actual_vertex_colors.f32');path.write_bytes(b''.join(struct.pack('<4f',*r)for r in rows))
        entry.update(actual_converted_vertex_count=unreal.GeometryScript_MeshQueries.get_vertex_count(dm),
                     actual_converted_triangles=sum(bool(unreal.GeometryScript_MeshQueries.get_triangle_indices(dm,i)[1])
                         for i in range(unreal.GeometryScript_MeshQueries.get_num_triangle_i_ds(dm))),
                     actual_vertex_colors=dict(file=str(path),bytes=path.stat().st_size,sha256=sha(path),count=len(rows)))
    check(len(R['images'])==4,'Incomplete actual calibration images')
    R['passed']=True


if __name__=='__main__':
    R.update(run_id=RUN,process_id=os.getpid(),script_sha256=sha(Path(__file__)),engine_version=unreal.SystemLibrary.get_engine_version())
    try:main()
    except Exception as error:R.update(error=str(error),traceback=traceback.format_exc());unreal.log_error(str(error))
    finally:
        if 'protected_packages_before'in R:
            after=inventory();R['packages_after']=after;lookup={i['file']:i for i in after}
            R['all_original_packages_unchanged']=all(lookup.get(i['file'])==i for i in R['protected_packages_before'])
            R['new_packages']=[i for i in after if i['file']not in {j['file']for j in R['protected_packages_before']}]
            if not R['all_original_packages_unchanged']:R['passed']=False
        flush()
    if not R['passed']:raise RuntimeError(R.get('error','Lighting calibration capture failed'))
