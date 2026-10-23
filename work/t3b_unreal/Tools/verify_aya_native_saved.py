"""Read-only second-process reload of a freshly saved Aya native candidate."""
from datetime import datetime,timezone
import hashlib,json,os
from pathlib import Path
import unreal
PROJECT=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
RUN=os.environ['T3B_NATIVE_RUN_ID'];OUTPUT=Path(os.environ['T3B_NATIVE_REPORT_PATH']);INPUT=Path(os.environ['T3B_NATIVE_SAVED_REPORT'])
RESULT={'schema':'t3b-native-saved-reload/v1','passed':False,'ue_render_verified':False,'UE_skinning_vertex_numeric_verified':False,'source_runtime_replaced':False}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def must(v,msg):
    if not v:raise RuntimeError(msg)
def main():
    source=json.loads(INPUT.read_text(encoding='utf-8'))
    must(source['verified_source_material_bound'],'Source import did not bind verified material')
    frozen=json.loads((PROJECT/'Validation/asset_import_runs/0fac54502ca140d4accffa2e5a7bc618/ue_editor_asset_creation.json').read_text(encoding='utf-8'))
    packages=source['saved_native_packages']+frozen['saved_assets']
    def unchanged():
        for p in packages:must(digest(Path(p['file']))==p['sha256'],'Package bytes changed: '+p['file'])
    unchanged();assets=[unreal.EditorAssetLibrary.load_asset(p['asset'])for p in source['created_assets']]
    must(all(a is not None for a in assets),'Could not reload all3 native packages')
    mesh=next(a for a in assets if isinstance(a,unreal.SkeletalMesh));skeleton=next(a for a in assets if isinstance(a,unreal.Skeleton));animation=next(a for a in assets if isinstance(a,unreal.AnimSequence))
    must(mesh.get_editor_property('skeleton')==skeleton and animation.get_editor_property('skeleton')==skeleton,'Reloaded mesh/animation skeleton references differ')
    slots=list(mesh.get_editor_property('materials'));must(len(slots)==1,'Reloaded material slot count differs')
    bound=slots[0].get_editor_property('material_interface');expected=source['material_bindings'][0]
    must(bound.get_path_name()==expected['bound_material'],'Saved material binding did not persist')
    must(unreal.EditorAssetLibrary.get_metadata_tag(bound,'T3BMaterialSignature')==expected['frozen_recipe_signature'],'Reloaded verified material recipe differs')
    textures=[n.get_editor_property('texture')for n in unreal.MaterialEditingLibrary.get_material_expressions(bound)if isinstance(n,unreal.MaterialExpressionTextureSample)]
    must(len(textures)==1 and textures[0].get_path_name()==expected['texture'],'Reloaded material texture reference differs')
    must(unreal.EditorAssetLibrary.get_metadata_tag(textures[0],'T3BSourceRGBA')==expected['rgba_sha256'],'Reloaded texture RGBA provenance differs')
    component=unreal.SkeletalMeshComponent();component.set_skinned_asset_and_update(mesh,False)
    names=[str(component.get_bone_name(i))for i in range(component.get_num_bones())]
    must(names==source['skeletal_meshes'][0]['bone_names'],'Reloaded bone names/order differ')
    for row in source['skeletal_meshes'][0]['source44_mapping']:must(str(component.get_parent_bone(row['expected_name']))==row['expected_source_parent_name'],'Reloaded hierarchy differs')
    root=component.get_ref_pose_transform(0)
    scale=[root.scale3d.x,root.scale3d.y,root.scale3d.z]
    must(all(abs(s-source['animations'][0]['synthetic_root_scale'][i])<1e-9 for i,s in enumerate(scale)),'Reloaded canonical root scale differs')
    subs=unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    sections=[[subs.get_lod_material_slot(mesh,lod,s)for s in range(subs.get_num_sections(mesh,lod))]for lod in range(subs.get_lod_count(mesh))]
    must(sections==expected['actual_LOD_section_slots'],'Reloaded sections/slot mapping differs')
    model=animation.get_editor_property('data_model_interface');must(model.get_number_of_keys()==60,'Reloaded animation keycount differs')
    registry=unreal.AssetRegistryHelpers.get_asset_registry();registry.scan_paths_synchronous([source['destination']],True)
    options=unreal.AssetRegistryDependencyOptions();options.include_hard_package_references=True;options.include_soft_package_references=True
    dependencies={}
    for asset in assets:
        package=asset.get_path_name().split('.',1)[0];deps=[str(p)for p in registry.get_dependencies(package,options)]
        missing=[p for p in deps if p.startswith('/Game/')and not unreal.EditorAssetLibrary.does_asset_exist(p)]
        must(not missing,'Reloaded native package has missing Game dependencies: '+str(missing));dependencies[package]=deps
    unchanged()
    RESULT.update(passed=True,source_import_report=str(INPUT),source_import_report_sha256=digest(INPUT),native_assets=[a.get_path_name()for a in assets],
        actual_bone_count=len(names),source44_hierarchy_preserved=True,canonical_root_scale=scale,material=bound.get_path_name(),texture=textures[0].get_path_name(),
        material_recipe_signature=expected['frozen_recipe_signature'],rgba_sha256=expected['rgba_sha256'],LOD_section_material_slots=sections,
        animation_keys=model.get_number_of_keys(),animation_frames=model.get_number_of_frames(),animation_length_seconds=model.get_play_length(),
        dependencies=dependencies,previous161_and_new3_package_bytes_unchanged=True,asset_writes_performed=False,
        limits=['NullRHI reload confirms package persistence and references, not native GPU pixels or CPU-skinned vertex positions.',
            'Native importer axes are (x,z,y), while PMC axes are (z,x,y); no axis correction or runtime substitution was applied.',
            'Original main-pass blended depth writes and animated C posed-face vertex lighting remain unsupported/unverified.'])
if __name__=='__main__':
    try:main()
    except Exception as e:RESULT['error']=str(e);raise
    finally:
        RESULT.update(run_id=RUN,process_id=os.getpid(),script_sha256=digest(Path(__file__)),engine_version=unreal.SystemLibrary.get_engine_version(),finished_utc=datetime.now(timezone.utc).isoformat())
        OUTPUT.write_text(json.dumps(RESULT,indent=2)+'\n',encoding='utf-8')