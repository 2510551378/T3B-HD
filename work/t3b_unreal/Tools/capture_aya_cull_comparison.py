"""Controlled actual-RHI FullUV Aya A/B: duplicate material, change only TwoSided.

Old packages and frozen source are read-only. One new material is saved in a unique
namespace. All failures/PNGs remain. This tests culling, not pixel/HD/gameplay fidelity.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import struct
import traceback
import zlib
import unreal

PROJECT=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
OUTPUT=Path(os.environ['T3B_AYA_CAPTURE_REPORT'])
IMPORT=Path(os.environ['T3B_AYA_CAPTURE_IMPORT'])
SKINNING=Path(os.environ['T3B_AYA_CAPTURE_SKINNING'])
FULLUV=Path(os.environ['T3B_AYA_CAPTURE_FULLUV'])
RUN=os.environ['T3B_AYA_CAPTURE_RUN_ID']
WIDTH,HEIGHT=768,1024
R={'schema':'t3b-native-aya-cull-comparison/v1','passed':False,'rendered_pngs_acquired':False,
   'source_pixel_equivalence_verified':False,'HD_verified':False,'gameplay_verified':False,
   'asset_writes_performed':False,'material_substitution_performed':True,'images':[],
   'limitations':['Actual UE preview of an imported native candidate, not original pixel equivalence/HD/gameplay.',
      'Native glTF lacks animated COLOR_0 face shading. White default vertex color with original RGB*2 differs from the C posed-face shading.',
      'Controlled TwoSided false restores the evidenced source cull enable only; original translucent main-pass depth-write remains unsupported.',
      'Fixed orthographic preview camera and manual UE exposure are not the original game camera or original renderer.',
      'Saved texture sRGB=false; UE tonemapping/exposure/display gamma differ from original byte-space GE/C colors.']}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(value,message):
    if not value:raise RuntimeError(message)


def flush():
    OUTPUT.write_text(json.dumps(R,indent=2)+'\n',encoding='utf-8')


def note(stage):
    R['stage']=stage
    flush()
    unreal.log('AYA_OFFSCREEN_STAGE '+stage)


def vec(value):
    return [float(value.x),float(value.y),float(value.z)]


def package_inventory():
    paths=sorted(p for p in (PROJECT/'Content').rglob('*') if p.is_file() and p.suffix.lower() in ('.uasset','.uexp','.ubulk','.umap'))
    return [{'file':str(p),'bytes':p.stat().st_size,'sha256':digest(p)}for p in paths]


def png_pixels(path):
    """Strict stdlib decoder for non-interlaced UE-exported RGB/RGBA PNG8."""
    data=path.read_bytes()
    check(data[:8]==b'\x89PNG\r\n\x1a\n','Not a PNG export')
    at=8;packed=bytearray();header=None;ended=False
    while at+12<=len(data):
        size=struct.unpack_from('>I',data,at)[0];kind=data[at+4:at+8]
        check(at+12+size<=len(data),'Truncated PNG chunk')
        raw=data[at+8:at+8+size]
        check(zlib.crc32(kind+raw)&0xffffffff==struct.unpack_from('>I',data,at+8+size)[0],'PNG chunk CRC differs')
        if kind==b'IHDR':header=struct.unpack('>2I5B',raw)
        if kind==b'IDAT':packed.extend(raw)
        at+=size+12
        if kind==b'IEND':ended=True;break
    check(ended and header is not None,'PNG header/end missing')
    width,height,bits,kind,compress,filtering,interlace=header
    check(bits==8 and kind in (2,6) and compress==filtering==interlace==0,'Unsupported PNG pixel layout')
    check(0<width<=2048 and 0<height<=2048,'PNG dimensions outside explicit bound')
    channels=3 if kind==2 else 4;stride=width*channels
    raw=zlib.decompress(packed);check(len(raw)==height*(stride+1),'PNG scanline length differs')
    result=bytearray();previous=bytearray(stride);offset=0
    for _ in range(height):
        mode=raw[offset];row=bytearray(raw[offset+1:offset+1+stride]);offset+=stride+1
        check(mode<=4,'Unsupported PNG scanline filter')
        for i in range(stride):
            left=row[i-channels]if i>=channels else 0;up=previous[i];upper_left=previous[i-channels]if i>=channels else 0
            if mode==1:predict=left
            elif mode==2:predict=up
            elif mode==3:predict=(left+up)//2
            elif mode==4:
                p=left+up-upper_left;a=abs(p-left);b=abs(p-up);c=abs(p-upper_left)
                predict=left if a<=b and a<=c else up if b<=c else upper_left
            else:predict=0
            row[i]=(row[i]+predict)&255
        result.extend(row);previous=row
    return width,height,channels,result


def foreground(image,empty):
    w,h,c,p=png_pixels(image);bw,bh,bc,b=png_pixels(empty)
    check((w,h)==(bw,bh)==(WIDTH,HEIGHT),'Capture dimensions differ')
    count=0;visible=0;minimum=[w,h];maximum=[-1,-1];colors=set();bright=0
    for i in range(w*h):
        rgb=p[i*c:i*c+3];bg=b[i*bc:i*bc+3]
        if max(abs(rgb[j]-bg[j])for j in range(3))>8:
            x,y=i%w,i//w;count+=1
            minimum[0]=min(minimum[0],x);minimum[1]=min(minimum[1],y)
            maximum[0]=max(maximum[0],x);maximum[1]=max(maximum[1],y)
            colors.add(tuple(x//8 for x in rgb));bright+=sum(rgb)>720
            visible+=c==3 or p[i*c+3]>0
    box=minimum+maximum if count else None
    return {'method':'RGB max-component delta>8 versus same-camera hidden-actor SceneCapture PNG',
        'foreground_pixels':count,'foreground_fraction':count/(w*h),'nonzero_alpha_foreground_pixels':visible,
        'foreground_bbox_xyxy':box,'quantized_foreground_colors':len(colors),
        'near_white_foreground_fraction':bright/count if count else None,
        'foreground_present':count>=1000 and visible>=1000 and maximum[0]-minimum[0]>=40 and maximum[1]-minimum[1]>=100}


def inspect_material(material):
    lib=unreal.MaterialEditingLibrary
    result={'asset':material.get_path_name(),'two_sided':bool(material.get_editor_property('two_sided')),
        'blend_mode':str(material.get_editor_property('blend_mode')),'shading_model':str(material.get_editor_property('shading_model')),
        'used_with_skeletal_mesh':bool(material.get_editor_property('used_with_skeletal_mesh')),
        'recipe_signature':unreal.EditorAssetLibrary.get_metadata_tag(material,'T3BMaterialSignature'),'nodes':[]}
    for node in lib.get_material_expressions(material):
        item={'class':node.get_class().get_name(),'object':node.get_path_name(),
              'inputs':[x.get_path_name()if x else None for x in lib.get_inputs_for_material_expression(material,node)]}
        if isinstance(node,unreal.MaterialExpressionConstant):item['constant_r']=node.get_editor_property('r')
        if isinstance(node,unreal.MaterialExpressionTextureSample):
            texture=node.get_editor_property('texture');item['texture']=texture.get_path_name()if texture else None
            if texture:item['actual_texture_srgb']=bool(texture.get_editor_property('srgb'))
        if isinstance(node,unreal.MaterialExpressionTextureCoordinate):
            item['u_tiling']=node.get_editor_property('u_tiling');item['v_tiling']=node.get_editor_property('v_tiling')
        result['nodes'].append(item)
    for name,prop in [('emissive',unreal.MaterialProperty.MP_EMISSIVE_COLOR),('opacity',unreal.MaterialProperty.MP_OPACITY)]:
        node=lib.get_material_property_input_node(material,prop);result[name+'_input']=node.get_path_name()if node else None
    return result


def transform(value):
    return {'translation':vec(value.translation),'scale':vec(value.scale3d),
        'quaternion':[float(value.rotation.x),float(value.rotation.y),float(value.rotation.z),float(value.rotation.w)]}


def protected_unchanged():
    after=package_inventory();R['packages_after']=after
    lookup={x['file']:x for x in after}
    return all(lookup.get(x['file'])==x for x in R['protected_packages_before'])


def mirror_comparison(front,back):
    w,h,c,p=png_pixels(Path(front['png']['file']));bw,bh,bc,b=png_pixels(Path(back['png']['file']))
    _,_,ec,e=png_pixels(Path(front['empty_control']['file']))
    _,_,ebc,eb=png_pixels(Path(back['empty_control']['file']))
    check((w,h)==(bw,bh),'Paired image sizes differ')
    mirrored=plain=masked=maskcount=0
    for y in range(h):
        for x in range(w):
            i=y*w+x;j=y*w+(w-1-x)
            for channel in range(3):
                plain+=abs(p[i*c+channel]-b[i*bc+channel])
                mirrored+=abs(p[j*c+channel]-b[i*bc+channel])
            if max(abs(p[j*c+k]-e[j*ec+k])for k in range(3))>8 or max(abs(b[i*bc+k]-eb[i*ebc+k])for k in range(3))>8:
                maskcount+=1;masked+=sum(abs(p[j*c+k]-b[i*bc+k])for k in range(3))
    return {'all_pixel_rgb_mae_front_vs_back':plain/(w*h*3),
        'all_pixel_rgb_mae_mirrored_front_vs_back':mirrored/(w*h*3),
        'foreground_union_rgb_mae_mirrored_front_vs_back':masked/(maskcount*3)if maskcount else None,
        'foreground_union_pixels':maskcount,'interpretation':'Image diagnostic only; not a pixel-equivalence threshold.'}


def main():
    imported=json.loads(IMPORT.read_text(encoding='utf-8-sig'));skinning=json.loads(SKINNING.read_text(encoding='utf-8-sig'))
    fulluv=json.loads(FULLUV.read_text(encoding='utf-8-sig'))
    check(fulluv['passed'] and fulluv['run_id']=='f34679f35e3744e58f694342fba517d5' and fulluv['full_precision_UVs_expected'],'Wrong verified FullUV candidate')
    R['full_uv_report']={'file':str(FULLUV),'sha256':digest(FULLUV)}
    check(imported['run_id']=='fbcb0ef145134ee58227c6c44f4835cb' and imported['native_import_completed']and imported['verified_source_material_bound'],'Wrong explicit compact candidate')
    check(skinning['run_id']=='d3bc5af548504f8d9145f593c5e9c2fa' and skinning['passed'] and
          skinning['source_import_report']['sha256']==digest(IMPORT),'Wrong actual-skinning evidence')
    R['import_report']={'file':str(IMPORT),'sha256':digest(IMPORT)}
    R['skinning_report']={'file':str(SKINNING),'sha256':digest(SKINNING)}
    gltf_path=Path(imported['source_gltf']['file']);check(digest(gltf_path)==imported['source_gltf']['sha256'],'Source glTF differs')
    gltf=json.loads(gltf_path.read_text(encoding='utf-8'))
    R['native_COLOR_0_present']=any('COLOR_0'in p['attributes']for m in gltf['meshes']for p in m['primitives'])
    R['source_gltf']=imported['source_gltf'];R['source_material_binding']=imported['material_bindings'][0]
    for item in imported['saved_native_packages']+fulluv['saved_native_packages']:check(digest(Path(item['file']))==item['sha256'],'Candidate package differs')
    R['protected_packages_before']=package_inventory();note('loading_explicit_original_candidate')
    mesh=unreal.load_asset(fulluv['skeletal_meshes'][0]['asset']);animation=unreal.load_asset(imported['animations'][0]['asset'])
    check(mesh is not None and animation is not None,'Actual native candidate failed to load')
    R['mesh']=mesh.get_path_name();R['animation']=animation.get_path_name()
    R['API_docs']={
        'capture_scene':unreal.SceneCaptureComponent2D.capture_scene.__doc__,
        'create_render_target2d':unreal.RenderingLibrary.create_render_target2d.__doc__,
        'export_render_target':unreal.RenderingLibrary.export_render_target.__doc__,
        'finish_loading_before_screenshot':unreal.AutomationLibrary.finish_loading_before_screenshot.__doc__}
    world=unreal.EditorLoadingAndSavingUtils.new_blank_map(False);check(world is not None,'No isolated world')
    R['world']=world.get_path_name()
    sub=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor=sub.spawn_actor_from_class(unreal.SkeletalMeshActor,unreal.Vector(0,0,0),unreal.Rotator(0,0,0),True)
    check(actor is not None,'No transient skeletal actor')
    component=actor.get_component_by_class(unreal.SkeletalMeshComponent);component.set_skinned_asset_and_update(mesh,True)
    component.set_editor_property('visibility_based_anim_tick_option',unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
    R['actor']=actor.get_path_name();R['actor_transform']={'location':vec(actor.get_actor_location()),'scale':vec(actor.get_actor_scale3d()),'rotation':str(actor.get_actor_rotation())}
    check(component.get_num_bones()==45,'Unexpected compact bone count')
    material=component.get_material(0);check(material.get_path_name()=='/Game/T3B/Materials/M_Aya_000.M_Aya_000','Original saved source material not bound')
    R['actual_material']=inspect_material(material)
    check(R['actual_material']['recipe_signature']==imported['material_bindings'][0]['frozen_recipe_signature'],'Saved material recipe differs')
    check(R['actual_material']['two_sided'] is True,'Baseline must actually be TwoSided')
    check(component.get_num_materials()==1,'Expected exactly one material slot')
    destination='/Game/T3B/NativeCandidates/AyaCull/Run_'+RUN+'/M_Aya_SingleSided'
    check(not unreal.EditorAssetLibrary.does_asset_exist(destination),'Refusing existing derived material')
    derived=unreal.EditorAssetLibrary.duplicate_asset(material.get_path_name(),destination)
    check(isinstance(derived,unreal.Material),'Material duplication failed')
    derived.set_editor_property('two_sided',False)
    R['asset_writes_performed']=True
    R['derived_material']=inspect_material(derived)
    def canonical(value,path):
        renderer=dict(value);renderer.pop('recipe_signature',None)
        return json.dumps(renderer,sort_keys=True).replace(path,'<MATERIAL>')
    R['material_provenance_metadata']={'source_signature':R['actual_material']['recipe_signature'],'duplicate_signature':R['derived_material']['recipe_signature'],'note':'DuplicateAsset does not copy package metadata. Provenance is retained here; graph comparison excludes this non-renderer tag.'}
    expected=dict(R['actual_material']);expected['two_sided']=False
    check(canonical(expected,material.get_path_name())==canonical(R['derived_material'],derived.get_path_name()),'Derived graph/settings changed beyond TwoSided')
    fields=('blend_mode','shading_model','used_with_skeletal_mesh','opacity_mask_clip_value','dithered_lod_transition','cast_dynamic_shadow_as_masked','allow_negative_emissive_color','disable_depth_test','translucency_sort_priority')
    R['additional_material_properties']={}
    for field in fields:
        try:
            a=material.get_editor_property(field);b=derived.get_editor_property(field)
            R['additional_material_properties'][field]={'original':str(a),'derived':str(b),'equal':a==b}
            check(a==b,'Other material property changed: '+field)
        except Exception as error:
            if 'Other material property changed' in str(error):raise
            R['additional_material_properties'][field]={'unavailable':str(error)}
    R['derived_compile_messages']=[str(x)for x in unreal.MaterialEditingLibrary.recompile_material(derived)]
    check(unreal.EditorAssetLibrary.save_loaded_asset(derived,False),'Could not save isolated derived material')
    newfile=PROJECT/'Content'/Path(destination.removeprefix('/Game/')).with_suffix('.uasset')
    check(newfile.is_file(),'Derived package missing')
    R['new_material_package']={'file':str(newfile),'sha256':digest(newfile),'bytes':newfile.stat().st_size}
    R['only_renderer_property_changed']='two_sided: true -> false'
    R['saved_material_ready']=True;note('derived_material_saved_originals_readonly')
    R['animation_policy']={'force_raw_before':unreal.SystemLibrary.get_console_variable_int_value('a.ForceEvalRawData'),'playing':False,'looping':False}
    unreal.SystemLibrary.execute_console_command(world,'a.ForceEvalRawData 1')
    R['animation_policy']['force_raw_during']=unreal.SystemLibrary.get_console_variable_int_value('a.ForceEvalRawData')
    check(R['animation_policy']['force_raw_during']==1,'Raw source evaluation not enabled')
    capture_actor=sub.spawn_actor_from_class(unreal.SceneCapture2D,unreal.Vector(0,340,88),unreal.Rotator(0,0,0),True)
    capture=capture_actor.get_component_by_class(unreal.SceneCaptureComponent2D)
    capture.set_editor_property('capture_every_frame',False);capture.set_editor_property('capture_on_movement',False)
    capture.set_editor_property('capture_source',unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    capture.set_editor_property('projection_type',unreal.CameraProjectionMode.ORTHOGRAPHIC);capture.set_editor_property('ortho_width',180.)
    capture.set_editor_property('primitive_render_mode',unreal.SceneCapturePrimitiveRenderMode.PRM_USE_SHOW_ONLY_LIST)
    capture.show_only_actor_components(actor,False)
    settings=capture.get_editor_property('post_process_settings')
    settings.set_editor_property('override_auto_exposure_method',True);settings.set_editor_property('auto_exposure_method',unreal.AutoExposureMethod.AEM_MANUAL)
    settings.set_editor_property('override_auto_exposure_bias',True);settings.set_editor_property('auto_exposure_bias',0.)
    settings.set_editor_property('override_auto_exposure_apply_physical_camera_exposure',True);settings.set_editor_property('auto_exposure_apply_physical_camera_exposure',False)
    settings.set_editor_property('override_motion_blur_amount',True);settings.set_editor_property('motion_blur_amount',0.)
    settings.set_editor_property('override_bloom_intensity',True);settings.set_editor_property('bloom_intensity',0.)
    capture.set_editor_property('post_process_settings',settings)
    target=unreal.RenderingLibrary.create_render_target2d(world,WIDTH,HEIGHT,unreal.TextureRenderTargetFormat.RTF_RGBA8,unreal.LinearColor(.025,.025,.025,1.),False,False)
    check(target is not None,'No actual render target');capture.set_editor_property('texture_target',target)
    R['render_settings']={'width':WIDTH,'height':HEIGHT,'projection':'orthographic','ortho_width_cm':180.,
        'capture_source':str(capture.get_editor_property('capture_source')),'target_format':str(target.get_editor_property('render_target_format')),
        'target_gamma':float(target.get_editor_property('target_gamma')),
        'actual_post_process':{name:str(settings.get_editor_property(name))for name in (
          'override_auto_exposure_method','auto_exposure_method','override_auto_exposure_bias','auto_exposure_bias',
          'override_auto_exposure_apply_physical_camera_exposure','auto_exposure_apply_physical_camera_exposure',
          'override_motion_blur_amount','motion_blur_amount','override_bloom_intensity','bloom_intensity')},
        'manual_exposure_bias':0.,'physical_camera_exposure':False,'motion_blur':0.,'bloom':0.,'rhi_requested':'D3D11 real offscreen RHI'}
    note('waiting_for_actual_shader_compilation_and_texture_streaming')
    unreal.AutomationLibrary.finish_loading_before_screenshot()
    views=[('front_plus_Y',[0.,340.,88.]),('back_minus_Y',[0.,-340.,88.])]
    def export(name):
        path=OUTPUT.parent/name;check(not path.exists(),'Refusing to overwrite existing image')
        capture.capture_scene()
        unreal.RenderingLibrary.export_render_target(world,target,str(OUTPUT.parent),name)
        check(path.is_file()and path.stat().st_size>0,'PNG export missing/empty')
        return {'file':str(path),'bytes':path.stat().st_size,'sha256':digest(path)}
    component.override_animation_data(animation,False,False,0.,1.)
    for mode,active_material in [('baseline_two_sided',material),('source_single_sided',derived)]:
        component.set_material(0,active_material)
        check(component.get_material(0)==active_material,'Component material override differs')
        unreal.AutomationLibrary.finish_loading_before_screenshot()
        for view,location in views:
            camera=unreal.Vector(*location);look=unreal.Vector(0.,10.,88.)
            rotation=unreal.MathLibrary.find_look_at_rotation(camera,look)
            capture_actor.set_actor_location(camera,False,False);capture_actor.set_actor_rotation(rotation,False)
            component.set_visibility(False,True)
            empty=export(mode+'_'+view+'_empty.png')
            component.set_visibility(True,True)
            for frame in (0,30):
                time=skinning['sample_attempts'][frame]['actual_position']
                component.set_position(time,False)
                component.override_animation_data(animation,False,False,time,1.)
                check(abs(component.get_position()-time)<2e-6,'Actual animation time differs')
                item={'source_frame':frame,'requested_time':time,'actual_time':component.get_position(),'view':view,'mode':mode,
                    'camera_location_cm':location,'camera_look_at_cm':[0.,10.,88.],'camera_rotation':str(rotation),
                    'empty_control':empty,'material':active_material.get_path_name(),
                    'capture_component_world_transform':transform(capture.get_world_transform()),
                    'capture_actor_world_transform':transform(capture_actor.get_actor_transform()),
                    'skeletal_component_world_transform':transform(component.get_world_transform()),
                    'skeletal_actor_world_transform':transform(actor.get_actor_transform()),
                    'bone_world':[{'name':str(component.get_bone_name(i)),
                      'translation':vec(component.get_bone_transform(component.get_bone_name(i)).translation),
                      'quaternion':[component.get_bone_transform(component.get_bone_name(i)).rotation.x,
                        component.get_bone_transform(component.get_bone_name(i)).rotation.y,
                        component.get_bone_transform(component.get_bone_name(i)).rotation.z,
                        component.get_bone_transform(component.get_bone_name(i)).rotation.w]}for i in range(component.get_num_bones())]}
                check(item['skeletal_actor_world_transform']=={'translation':[0.,0.,0.],'scale':[1.,1.,1.],'quaternion':[0.,0.,0.,1.]},'Actor is not identity')
                check(item['capture_component_world_transform']['translation']==location,'Actual capture component camera position differs')
                R['images'].append(item);note('capturing_'+mode+'_'+view+'_frame'+str(frame))
                unreal.AutomationLibrary.finish_loading_before_screenshot()
                item['png']=export(f'{mode}_aya_f{frame:02d}_{view}.png')
                item['image_validation']=foreground(Path(item['png']['file']),Path(empty['file']));flush()
    R['paired_mirror_diagnostics']={}
    for mode in ('baseline_two_sided','source_single_sided'):
        R['paired_mirror_diagnostics'][mode]={}
        for frame in (0,30):
            pair=[x for x in R['images']if x['mode']==mode and x['source_frame']==frame]
            R['paired_mirror_diagnostics'][mode][str(frame)]=mirror_comparison(next(x for x in pair if x['view']=='front_plus_Y'),next(x for x in pair if x['view']=='back_minus_Y'))
    R['frame_pair_png_hashes_differ']={mode+'_'+view:len({x['png']['sha256']for x in R['images']if x['mode']==mode and x['view']==view and 'png'in x})==2 for mode in ('baseline_two_sided','source_single_sided')for view,_ in views}
    R['rendered_pngs_acquired']=len(R['images'])==8 and all('png'in x for x in R['images'])
    R['foreground_detected_in_all_images']=all(x.get('image_validation',{}).get('foreground_present',False)for x in R['images'])
    note('checking_all_original_package_hashes')
    R['all_original_packages_unchanged']=protected_unchanged()
    before={x['file']for x in R['protected_packages_before']}
    R['new_packages']=[x for x in R['packages_after']if x['file']not in before]
    check(len(R['new_packages'])==1 and R['new_packages'][0]['file']==R['new_material_package']['file'],'Unexpected asset additions')
    check(R['all_original_packages_unchanged'],'An original Content package hash changed')
    R['passed']=R['rendered_pngs_acquired']and R['foreground_detected_in_all_images']
    R['passed_scope']='Actual same-process controlled AB acquisition/foreground and protected package hashes; visual outcome separately reviewed.'
    check(R['passed'],'Actual PNGs lacked valid foreground; failed/black originals retained')


if __name__=='__main__':
    R.update(run_id=RUN,process_id=os.getpid(),script_sha256=digest(Path(__file__)),engine_version=unreal.SystemLibrary.get_engine_version(),started_utc=datetime.now(timezone.utc).isoformat())
    try:main()
    except Exception as error:
        R.update(error=str(error),traceback=traceback.format_exc());unreal.log_error(str(error))
    finally:
        if 'protected_packages_before'in R and 'packages_after'not in R:
            try:
                R['all_original_packages_unchanged']=protected_unchanged()
            except Exception as error:R['final_package_check_error']=str(error)
        R['finished_utc']=datetime.now(timezone.utc).isoformat();flush()
    if not R['passed']:raise RuntimeError(R.get('error','Actual offscreen preview incomplete'))
