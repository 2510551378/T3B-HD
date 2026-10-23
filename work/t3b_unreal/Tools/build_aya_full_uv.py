"""Duplicate compact Aya mesh, set official LOD build option and save new asset.
Official SetLodBuildSettings uses FScopedSkeletalMeshPostEditChange; real
RenderData precision is independently reloaded/captured in a second process.
"""
import hashlib,json,os,traceback
from pathlib import Path
import unreal
P=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve();O=Path(os.environ['T3B_NATIVE_REPORT_PATH']);INPUT=Path(os.environ['T3B_NATIVE_SAVED_REPORT']);RUN=os.environ['T3B_NATIVE_RUN_ID']
R={'schema':'t3b-full-precision-uv-build/v1','passed':False,'verified_source_material_bound':False,'rendered_pixels_verified':False,'source_runtime_replaced':False}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(v,msg):
    if not v:raise RuntimeError(msg)
def main():
    source=json.loads(INPUT.read_text(encoding='utf-8'));check(source.get('candidate_kind')=='compact','Explicit compact input required')
    protected=[{'file':str(p),'sha256':sha(p)}for p in (P/'Content').rglob('*')if p.is_file()and p.suffix.lower()in ['.uasset','.umap']]
    def unchanged():
        for p in protected:check(sha(Path(p['file']))==p['sha256'],'Preexisting package changed: '+p['file'])
    R['protected_packages']=protected
    original=unreal.load_asset(source['skeletal_meshes'][0]['asset']);check(isinstance(original,unreal.SkeletalMesh),'No compact source mesh')
    api=unreal.SkeletalMeshEditorSubsystem;before=api.get_lod_build_settings(original,0)
    field='use_full_precision_u_vs';original_flag=before.get_editor_property(field)
    check(not original_flag,'Compact source was already full precision; control differs')
    destination='/Game/T3B/NativeCandidates/AyaFullUV/Run_'+RUN+'/aya_native_full_uv'
    check(not unreal.EditorAssetLibrary.does_asset_exist(destination),'Never overwrite candidate')
    mesh=unreal.EditorAssetLibrary.duplicate_asset(original.get_path_name(),destination);check(isinstance(mesh,unreal.SkeletalMesh),'Candidate duplication failed')
    settings=api.get_lod_build_settings(mesh,0);R['settings_before']=str(settings)
    settings.set_editor_property(field,True);api.set_lod_build_settings(mesh,0,settings)
    actual=api.get_lod_build_settings(mesh,0);R['settings_after']=str(actual)
    check(actual.get_editor_property(field),'Official build settings setter/readback did not apply')
    check(not api.get_lod_build_settings(original,0).get_editor_property(field),'Source mesh setting changed')
    check(unreal.EditorAssetLibrary.save_loaded_asset(mesh,False),'New mesh save failed')
    component=unreal.SkeletalMeshComponent();component.set_skinned_asset_and_update(mesh,False)
    old_component=unreal.SkeletalMeshComponent();old_component.set_skinned_asset_and_update(original,False)
    def bones(c):return [{'index':i,'name':str(c.get_bone_name(i)),'parent':str(c.get_parent_bone(c.get_bone_name(i)))}for i in range(c.get_num_bones())]
    check(bones(component)==bones(old_component),'Copied source hierarchy changed')
    check(mesh.get_editor_property('skeleton')==original.get_editor_property('skeleton'),'Copied skeleton reference changed')
    check(component.get_material(0)==old_component.get_material(0),'Copied material changed')
    package=mesh.get_path_name().split('.')[0];file=(P/'Content'/package[len('/Game/'):]).with_suffix('.uasset');check(file.is_file(),'New fullUV package not saved')
    unchanged()
    R.update(passed=True,source_input_report=str(INPUT),source_input_report_sha256=sha(INPUT),source_mesh=original.get_path_name(),destination=destination,
        full_precision_UVs_expected=True,original_setting=False,new_setting=True,official_api='SkeletalMeshEditorSubsystem.set_lod_build_settings(mesh,0,settings)',
        official_rebuild_source='SkeletalMeshEditorSubsystem.cpp:1075-1079 uses FScopedSkeletalMeshPostEditChange; second-process RenderData F32 verification remains required.',
        skeletal_meshes=[{'asset':mesh.get_path_name()}],animations=source['animations'],source_gltf=source['source_gltf'],candidate_kind='compact_full_uv',
        saved_native_packages=[{'asset':mesh.get_path_name(),'file':str(file),'bytes':file.stat().st_size,'sha256':sha(file)}],
        actual_bone_hierarchy=bones(component),skeleton=mesh.get_editor_property('skeleton').get_path_name(),actual_material=component.get_material(0).get_path_name(),
        verified_source_material_bound=True,all_preexisting_packages_unchanged=True,render_data_precision_verified=False)
if __name__=='__main__':
    try:main()
    except Exception as e:R['error']=str(e);R['traceback']=traceback.format_exc();raise
    finally:
        R.update(run_id=RUN,process_id=os.getpid(),script_sha256=sha(Path(__file__)),engine_version=unreal.SystemLibrary.get_engine_version())
        O.write_text(json.dumps(R,indent=2)+'\n',encoding='utf-8')