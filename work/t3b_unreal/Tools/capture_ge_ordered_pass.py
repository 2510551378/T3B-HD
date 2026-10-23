"""Actual UE ordered-pass acceptance producer; requires a real compiled module.

This file is prepared while MSVC/SDK authorization is pending. It has not run.
"""
import hashlib,json,os,struct,traceback
from pathlib import Path
import unreal

P=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
O=Path(os.environ['T3B_GE_PASS_REPORT']);BUNDLE=Path(os.environ['T3B_GE_PASS_BUNDLE'])
R=dict(schema='t3b-ue-ordered-main-depth-acceptance/v1',passed=False,samples=[],
       original_PSP_pixels_verified=False,original_timing_verified=False,full_M1_verified=False)


def check(ok,reason):
    if not ok:raise RuntimeError(reason)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def flush():O.write_text(json.dumps(R,indent=2)+'\n',encoding='utf-8')
def inventory():return[dict(file=str(p),bytes=p.stat().st_size,sha256=sha(p))for p in sorted((P/'Content').rglob('*'))if p.is_file()and p.suffix.lower()in('.uasset','.umap','.uexp','.ubulk')]
def vec(v):return[v.x,v.y,v.z]
def transform(t):return dict(translation=vec(t.translation),scale=vec(t.scale3d),quaternion=[t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w])


def main():
    check(hasattr(unreal,'T3BGEReplayActor'),'Compiled T3B GE replay class missing; UBT build is required')
    R['protected_packages_before']=inventory();R['bundle']=dict(file=str(BUNDLE),sha256=sha(BUNDLE))
    sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world();check(world is not None,'Editor world missing')
    for a in sub.get_all_level_actors():sub.destroy_actor(a)
    actor=sub.spawn_actor_from_class(unreal.T3BGEReplayActor,unreal.Vector(0,0,0),unreal.Rotator(0,0,0),True)
    check(actor.load_original_ge_bundle(str(BUNDLE)),'Actual C++ GE loader rejected original bundle')
    check(actor.get_editor_property('source_ready')and actor.get_editor_property('captured_sample_count')==12,'Incomplete original source series')
    camera=sub.spawn_actor_from_class(unreal.SceneCapture2D,unreal.Vector(0,340,88),unreal.Rotator(0,0,0),True)
    capture=camera.get_component_by_class(unreal.SceneCaptureComponent2D)
    for prop,value in dict(capture_every_frame=False,capture_on_movement=False,capture_source=unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR,
                           projection_type=unreal.CameraProjectionMode.ORTHOGRAPHIC,ortho_width=180.,
                           primitive_render_mode=unreal.SceneCapturePrimitiveRenderMode.PRM_RENDER_SCENE_PRIMITIVES).items():capture.set_editor_property(prop,value)
    settings=capture.get_editor_property('post_process_settings')
    for prop,value in dict(override_auto_exposure_method=True,auto_exposure_method=unreal.AutoExposureMethod.AEM_MANUAL,
                           override_auto_exposure_bias=True,auto_exposure_bias=0.,
                           override_auto_exposure_apply_physical_camera_exposure=True,auto_exposure_apply_physical_camera_exposure=False,
                           override_motion_blur_amount=True,motion_blur_amount=0.,override_bloom_intensity=True,bloom_intensity=0.).items():settings.set_editor_property(prop,value)
    capture.set_editor_property('post_process_settings',settings)
    target=unreal.RenderingLibrary.create_render_target2d(world,512,768,unreal.TextureRenderTargetFormat.RTF_RGBA8,
        unreal.LinearColor(0,0,0,1),False,False);capture.set_editor_property('texture_target',target)
    R['render_settings']=dict(width=512,height=768,ortho_width=180.,target_gamma=target.get_editor_property('target_gamma'),
        auto_calculate_ortho_planes=capture.get_editor_property('auto_calculate_ortho_planes'),
        update_ortho_planes=capture.get_editor_property('update_ortho_planes'),manual_exposure=0.,RHI='D3D11')
    def image(name):
        path=O.parent/name;check(not path.exists(),'Never overwrite capture PNG')
        unreal.AutomationLibrary.finish_loading_before_screenshot();capture.capture_scene()
        unreal.RenderingLibrary.export_render_target(world,target,str(O.parent),name)
        check(path.is_file(),'Actual UE image export missing');return dict(file=str(path),bytes=path.stat().st_size,sha256=sha(path))
    for sample in range(12):
        actor.set_captured_sample(sample)
        file=O.parent/('sample_'+str(sample)+'_submitted.bin')
        check(actor.write_submitted_frame(str(file)),'Actual C++ submitted-frame dump failed')
        entry=dict(sample=sample,actor_transform=transform(actor.get_actor_transform()),
                   submitted=dict(file=str(file),sha256=sha(file),scope='Actual actor CPU submission, not GPU readback'),views={})
        for view,y in [('positive_y',340.),('negative_y',-340.)]:
            location=unreal.Vector(0,y,88);camera.set_actor_location(location,False,False)
            camera.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(location,unreal.Vector(0,0,88)),False)
            entry['views'][view]=dict(camera_component_transform=transform(capture.get_world_transform()),images={})
            if sample==0:
                actor.set_editor_property('enable_ge_pass',False);actor.set_captured_sample(sample)
                entry['views'][view]['hidden_control']=image(view+'_hidden_control.png')
                actor.set_editor_property('enable_ge_pass',True);actor.set_captured_sample(sample)
            for depth_write in(0,1):
                unreal.SystemLibrary.execute_console_command(world,'r.T3BGE.DepthWrite '+str(depth_write))
                entry['views'][view]['images'][str(depth_write)]=image('%02d_%s_depth%d.png'%(sample,view,depth_write))
        R['samples'].append(entry);R['stage']='sample_'+str(sample);flush()
    unreal.SystemLibrary.execute_console_command(world,'r.T3BGE.DepthWrite 1')
    R['passed']=True


if __name__=='__main__':
    R.update(run_id=os.environ['T3B_GE_PASS_RUN'],process_id=os.getpid(),script_sha256=sha(Path(__file__)),
             engine_version=unreal.SystemLibrary.get_engine_version())
    try:main()
    except Exception as error:R.update(error=str(error),traceback=traceback.format_exc());unreal.log_error(str(error))
    finally:
        if 'protected_packages_before'in R:
            R['packages_after']=inventory();R['all_original_packages_unchanged']=R['packages_after']==R['protected_packages_before']
            if not R['all_original_packages_unchanged']:R['passed']=False
        flush()
    if not R['passed']:raise RuntimeError(R.get('error','UE GE pass acceptance failed'))
