"""Save/reload a new FullUV native Aya with the observed single-sided material.

Existing mesh/material/skeleton/animation packages are protected. This candidate
has corrected default culling; it is not complete original rendering or gameplay.
"""
import hashlib
import json
import os
from pathlib import Path
import traceback

import unreal

P = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
O = Path(os.environ['T3B_CULL_BIND_OUTPUT'])
REQUEST = Path(os.environ['T3B_CULL_BIND_REQUEST'])
R = {'schema':'t3b-aya-native-source-cull-binding/v1','passed':False,
     'original_pixels_verified':False,'gameplay_verified':False,'production_runtime_replaced':False}


def check(value,message):
    if not value:
        raise RuntimeError(message)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def package(asset):
    return (P/'Content'/asset.split('.')[0].removeprefix('/Game/')).with_suffix('.uasset')


def inventory():
    return [{'file':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}
            for p in sorted((P/'Content').rglob('*')) if p.is_file() and
            p.suffix.lower() in ('.uasset','.umap','.uexp','.ubulk')]


def snapshot(mesh):
    component = unreal.SkeletalMeshComponent()
    component.set_skinned_asset_and_update(mesh,False)
    slots = mesh.get_editor_property('materials')
    check(len(slots) == component.get_num_materials() == 1,'Expected one original material slot')
    material = component.get_material(0)
    settings = unreal.SkeletalMeshEditorSubsystem.get_lod_build_settings(mesh,0)
    fields = ('recompute_normals','recompute_tangents','use_mikk_t_space','compute_weighted_normals',
              'remove_degenerates','use_high_precision_tangent_basis','use_high_precision_skin_weights',
              'use_full_precision_u_vs','use_backwards_compatible_f16_trunc_u_vs','optimize_for_instancing',
              'threshold_position','threshold_tangent_normal','threshold_uv','morph_threshold_position',
              'bone_influence_limit')
    return dict(asset=mesh.get_path_name(),skeleton=mesh.get_editor_property('skeleton').get_path_name(),
                material=material.get_path_name(),two_sided=bool(material.get_editor_property('two_sided')),
                blend_mode=str(material.get_editor_property('blend_mode')),
                bone_hierarchy=[{'name':str(component.get_bone_name(i)),
                    'parent':str(component.get_parent_bone(component.get_bone_name(i)))}
                    for i in range(component.get_num_bones())],
                lod0_build_settings={field:settings.get_editor_property(field) for field in fields},
                full_precision_uvs=bool(unreal.SkeletalMeshEditorSubsystem.get_lod_build_settings(mesh,0).get_editor_property('use_full_precision_u_vs')),
                raw_lod0_vertices=unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem).get_num_verts(mesh,0),
                material_slot_name=str(slots[0].get_editor_property('material_slot_name')))


def main():
    q = json.loads(REQUEST.read_text(encoding='utf-8'))
    R.update(run_id=q['run_id'],mode=q['mode'],request_sha256=sha(REQUEST))
    for item in q['inputs']:
        check(sha(Path(item['file'])) == item['sha256'],'Frozen binding input changed')
    protected = inventory()
    R['protected_packages_before'] = protected
    source = unreal.load_asset(q['source_mesh'])
    material = unreal.load_asset(q['source_cull_material'])
    check(isinstance(source,unreal.SkeletalMesh) and isinstance(material,unreal.Material),'Missing actual inputs')
    before = snapshot(source)
    check(before['full_precision_uvs'] and before['two_sided'] and before['raw_lod0_vertices'] == 3449,
          'Expected measured FullUV baseline')
    check(material.get_editor_property('two_sided') is False,'Expected actual tested source-cull material')
    check(str(material.get_editor_property('blend_mode')) == before['blend_mode'],'Blend mode changed')
    if q['mode'] == 'build':
        check(not unreal.EditorAssetLibrary.does_asset_exist(q['destination']),'Refusing existing candidate')
        mesh = unreal.EditorAssetLibrary.duplicate_asset(source.get_path_name(),q['destination'])
        check(isinstance(mesh,unreal.SkeletalMesh),'Mesh duplication failed')
        slots = list(mesh.get_editor_property('materials'))
        check(len(slots) == 1,'Unexpected duplicated slots')
        slots[0].set_editor_property('material_interface',material)
        mesh.set_editor_property('materials',slots)
        R['material_slot_after_setter'] = mesh.get_editor_property('materials')[0].get_editor_property('material_interface').get_path_name()
        check(R['material_slot_after_setter'] == material.get_path_name(),'Mesh material array setter did not apply')
        check(unreal.EditorAssetLibrary.save_loaded_asset(mesh,False),'Candidate save failed')
    else:
        check(q['mode'] == 'reload','Unknown mode')
        mesh = unreal.load_asset(q['destination'])
        check(isinstance(mesh,unreal.SkeletalMesh),'Saved candidate did not reload')
    actual = snapshot(mesh)
    R['source'] = before
    R['actual'] = actual
    check(actual['material'] == material.get_path_name() and actual['two_sided'] is False,
          'Candidate default material was not bound')
    for field in ('skeleton','bone_hierarchy','lod0_build_settings','full_precision_uvs',
                  'raw_lod0_vertices','material_slot_name','blend_mode'):
        check(actual[field] == before[field],'Geometry/skeleton/build setting changed: '+field)
    check(len(actual['bone_hierarchy']) == 45,'Expected preserved 45-bone hierarchy')
    check(snapshot(source) == before,'Source mesh was modified in memory')
    after = inventory()
    lookup = {i['file']:i for i in after}
    check(all(lookup.get(i['file']) == i for i in protected),'Preexisting package changed')
    new = [i for i in after if i['file'] not in {b['file'] for b in protected}]
    file = package(mesh.get_path_name())
    if q['mode'] == 'build':
        check(len(new) == 1 and new[0]['file'] == str(file),'Unexpected new packages')
    else:
        check(not new,'Read-only reload created packages')
    R.update(passed=True,source=before,actual=actual,all_preexisting_packages_unchanged=True,
             new_packages=new,skeletal_meshes=[{'asset':mesh.get_path_name()}],
             saved_package={'file':str(file),'bytes':file.stat().st_size,'sha256':sha(file)},
             limitations=['Only the default material binding is changed; original blended main-depth writes remain unimplemented.',
                          'Original three-light shading and output color are not yet restored.',
                          'No new rendered pose, pixel match, formal replay or combat acceptance is claimed by this save/reload.'])


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        R.update(error=str(e),traceback=traceback.format_exc())
        raise
    finally:
        if 'protected_packages_before' in R:
            after = {i['file']:i for i in inventory()}
            R['all_preexisting_packages_unchanged'] = all(after.get(i['file']) == i for i in R['protected_packages_before'])
        R.update(process_id=os.getpid(),engine_version=unreal.SystemLibrary.get_engine_version(),
                 script_sha256=sha(Path(__file__)))
        O.write_text(json.dumps(R,indent=2)+'\n',encoding='utf-8')
