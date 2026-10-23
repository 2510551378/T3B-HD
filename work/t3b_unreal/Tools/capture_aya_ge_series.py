"""Actual UE DynamicMesh replay of retained GE samples, without saved asset edits.

This uses evaluated production-series outputs. It does not replace the native
skeletal/weapon timeline, infer original timing, or claim original GPU pixels.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import traceback
import unreal

P = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
O = Path(os.environ['T3B_SERIES_REPORT'])
INPUT = Path(os.environ['T3B_SERIES_INPUT'])
PROOF = Path(os.environ['T3B_SERIES_RUNTIME'])
R = dict(schema='aya-ge-series-actual-ue-replay/v1', passed=False, samples=[], images=[], groups=[],
         original_timing_verified=False, original_hardware_pixels_verified=False,
         production_skeletal_timeline_replaced=False, saved_assets_changed=False)


def check(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def flush():
    O.write_text(json.dumps(R, indent=2) + '\n', encoding='utf-8')


def note(stage):
    R['stage'] = stage; flush(); unreal.log('T3B_GE_SERIES ' + stage)


def inventory():
    return [dict(file=str(p), bytes=p.stat().st_size, sha256=sha(p)) for p in sorted((P / 'Content').rglob('*'))
            if p.is_file() and p.suffix.lower() in ('.uasset', '.umap', '.uexp', '.ubulk')]


def vec(v):
    return [v.x, v.y, v.z]


def transform(t):
    return dict(translation=vec(t.translation), scale=vec(t.scale3d),
                quaternion=[t.rotation.x, t.rotation.y, t.rotation.z, t.rotation.w])


def main():
    m = json.loads(INPUT.read_text(encoding='utf-8')); proof = json.loads(PROOF.read_text(encoding='utf-8'))
    check(m['passed'] and proof['passed'] and proof['all_transform_color_bytes_equal'], 'Unverified source/adapter')
    check(sha(INPUT) == proof['input_manifest']['sha256'], 'Runtime proof has different input manifest')
    R['input'] = dict(file=str(INPUT), sha256=sha(INPUT)); R['runtime_proof'] = dict(file=str(PROOF), sha256=sha(PROOF))
    for row in proof['sources']:
        check(sha(Path(row['file'])) == row['sha256'], 'Evaluated production source changed')
    output = Path(proof['runtime_output']['file']); uv_file = Path(proof['runtime_uv']['file'])
    check(sha(output) == proof['runtime_output']['sha256'] and sha(uv_file) == proof['runtime_uv']['sha256'],
          'Evaluated output identity changed')
    data = output.read_bytes(); uvraw = uv_file.read_bytes()
    check(len(data) == m['total_vertices'] * 32 and len(uvraw) == m['total_vertices'] * 8, 'Invalid evaluated extent')
    check(all(data[i:i + 3] == b'\0\0\0' for i in range(28, len(data), 32)), 'Secondary specular shader required')
    R['protected_packages_before'] = inventory()
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    check(world is not None, 'No actual editor world')
    for existing in sub.get_all_level_actors():
        sub.destroy_actor(existing)
    actor = sub.spawn_actor_from_class(unreal.DynamicMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), True)
    comp = actor.get_dynamic_mesh_component(); dm = comp.get_dynamic_mesh()
    material = unreal.load_asset('/Game/T3B/NativeCandidates/AyaCull/Run_8198e8faa071458c834fa911389cc582/M_Aya_SingleSided')
    check(isinstance(material, unreal.Material) and material.get_editor_property('two_sided') is False,
          'Missing tested single-sided source material')
    comp.set_material(0, material)
    comp.set_vertex_color_space_transform_mode(unreal.DynamicMeshVertexColorTransformMode.NO_TRANSFORM)
    R['material'] = dict(asset=material.get_path_name(), two_sided=False, blend_mode=str(material.get_editor_property('blend_mode')),
                         vertex_color_space=str(comp.get_vertex_color_space_transform_mode()), rgb_scale=2,
                         original_main_depth_write_verified=False)
    R['API_docs'] = {name: getattr(unreal.GeometryScript_MeshEdits, name).__doc__ for name in
                     ('append_buffers_to_mesh', 'set_all_mesh_vertex_positions')}
    camera = sub.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(0, 340, 88), unreal.Rotator(0, 0, 0), True)
    capture = camera.get_component_by_class(unreal.SceneCaptureComponent2D)
    for prop, value in dict(capture_every_frame=False, capture_on_movement=False,
                            capture_source=unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR,
                            projection_type=unreal.CameraProjectionMode.ORTHOGRAPHIC, ortho_width=180.,
                            primitive_render_mode=unreal.SceneCapturePrimitiveRenderMode.PRM_USE_SHOW_ONLY_LIST).items():
        capture.set_editor_property(prop, value)
    capture.show_only_actor_components(actor, False)
    settings = capture.get_editor_property('post_process_settings')
    for prop, value in dict(override_auto_exposure_method=True, auto_exposure_method=unreal.AutoExposureMethod.AEM_MANUAL,
                            override_auto_exposure_bias=True, auto_exposure_bias=0.,
                            override_auto_exposure_apply_physical_camera_exposure=True, auto_exposure_apply_physical_camera_exposure=False,
                            override_motion_blur_amount=True, motion_blur_amount=0., override_bloom_intensity=True, bloom_intensity=0.).items():
        settings.set_editor_property(prop, value)
    capture.set_editor_property('post_process_settings', settings)
    target = unreal.RenderingLibrary.create_render_target2d(world, 512, 768, unreal.TextureRenderTargetFormat.RTF_RGBA8,
                                                          unreal.LinearColor(0, 0, 0, 1), False, False)
    capture.set_editor_property('texture_target', target)
    R['render_settings'] = dict(width=512, height=768, RHI='D3D11', target_gamma=target.get_editor_property('target_gamma'),
                                capture_source=str(capture.get_editor_property('capture_source')), manual_exposure=0.,
                                physical_camera_exposure=False, motion_blur=0., bloom=0.)
    # Same units as the canonical native Aya export; one fixed origin per capture group.
    source_gltf = P.parent / 'psp_parse/out/AYA_NATIVE_GLTF_20261020/aya_native.gltf'
    units = json.loads(source_gltf.read_text(encoding='utf-8'))['nodes'][0]['scale'][0]
    R['metres_per_PSP_world_unit'] = units
    R['coordinate_contract'] = 'UEcm = ((world.x-origin.x),(world.z-origin.z),(world.y-origin.y))*units*100; no actor transform'
    Q = unreal.GeometryScript_MeshQueries; L = unreal.GeometryScript_List
    C = unreal.GeometryScript_VertexColors; N = unreal.GeometryScript_Normals; E = unreal.GeometryScript_MeshEdits
    triangles = [unreal.IntVector(i, i + 1, i + 2) for i in range(0, 3456, 3)]
    readback = O.parent / 'actual_component_samples.bin'
    active_group = None; built = False

    def export(name):
        file = O.parent / name; check(not file.exists(), 'Never replace sample PNG')
        unreal.AutomationLibrary.finish_loading_before_screenshot()
        capture.capture_scene(); unreal.RenderingLibrary.export_render_target(world, target, str(O.parent), name)
        check(file.is_file(), 'Actual PNG capture missing')
        return dict(file=str(file), bytes=file.stat().st_size, sha256=sha(file))

    def topology_uv(label):
        check(Q.get_num_triangle_i_ds(comp.get_dynamic_mesh()) == 1152, 'Original triangle multiplicity changed')
        inds = bytearray(); tex = bytearray()
        for ti in range(1152):
            index, valid = Q.get_triangle_indices(comp.get_dynamic_mesh(), ti)
            check(valid, 'Triangle ID missing')
            inds += struct.pack('<3I', index.x, index.y, index.z)
            a, b, c, valid_uv = Q.get_triangle_u_vs(comp.get_dynamic_mesh(), 0, ti)
            check(valid_uv, 'Original UV overlay missing')
            for v in (a, b, c):
                tex += struct.pack('<2f', v.x, v.y)
        index_path = O.parent / (label + '_actual_indices.u32'); uv_path = O.parent / (label + '_actual_uv.f32')
        index_path.write_bytes(inds); uv_path.write_bytes(tex)
        return dict(indices=dict(file=str(index_path), sha256=sha(index_path)), uv=dict(file=str(uv_path), sha256=sha(uv_path)))

    with readback.open('wb') as saved:
        for frame_index, frame in enumerate(m['frames']):
            group = frame['group']; sample = frame['sample']; first = frame['first_output_vertex']
            raw = data[first * 32:(first + 3456) * 32]
            rows = list(struct.iter_unpack('<6f4B3Bx', raw))
            tex = list(struct.iter_unpack('<2f', uvraw[first * 8:(first + 3456) * 8]))
            if group != active_group:
                active_group = group
                origin = [(min(v[0] for v in rows) + max(v[0] for v in rows)) / 2,
                          min(v[1] for v in rows), (min(v[2] for v in rows) + max(v[2] for v in rows)) / 2]
                R['groups'].append(dict(group=group, fixed_PSP_world_origin=origin, preview_fps=30,
                                        actual_original_clock_verified=False))
                camera.set_actor_location(unreal.Vector(0, 340, 88), False, False)
                camera.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(unreal.Vector(0, 340, 88), unreal.Vector(0, 0, 88)), False)
                comp.set_visibility(False, True)
                R['groups'][-1]['hidden_control'] = export(group + '_hidden.png')
                comp.set_visibility(True, True)
            positions = [unreal.Vector((v[0] - origin[0]) * units * 100, (v[2] - origin[2]) * units * 100,
                                       (v[1] - origin[1]) * units * 100) for v in rows]
            normals = [unreal.Vector(v[3], v[5], v[4]) for v in rows]
            colors = [unreal.LinearColor(*[b / 255 for b in v[6:10]]) for v in rows]
            if not built:
                buffers = unreal.GeometryScriptSimpleMeshBuffers()
                for prop, value in dict(vertices=positions, normals=normals, uv0=[unreal.Vector2D(*v) for v in tex],
                                        vertex_colors=colors, triangles=triangles).items():
                    buffers.set_editor_property(prop, value)
                E.append_buffers_to_mesh(dm, buffers, 0, False)
                built = True
            else:
                E.set_all_mesh_vertex_positions(dm, L.convert_array_to_vector_list(positions))
                N.set_mesh_per_vertex_normals(dm, L.convert_array_to_vector_list(normals))
                C.set_mesh_per_vertex_colors(dm, L.convert_array_to_color_list(colors))
            actual = comp.get_dynamic_mesh()
            check(actual == dm and Q.get_vertex_count(actual) == 3456, 'Actual dynamic component topology changed')
            _, pos_list, p_gaps = Q.get_all_vertex_positions(actual, False)
            _, color_list, c_valid, c_gaps = C.get_mesh_per_vertex_colors(actual, False)
            _, normal_list, n_valid, n_gaps = N.get_mesh_per_vertex_normals(actual, False)
            check(c_valid and n_valid and not (p_gaps or c_gaps or n_gaps), 'Incomplete actual component overlays')
            actual_pos = L.convert_vector_list_to_array(pos_list)
            actual_color = L.convert_color_list_to_array(color_list)
            actual_normal = L.convert_vector_list_to_array(normal_list)
            check(len(actual_pos) == len(actual_color) == len(actual_normal) == 3456, 'Readback count differs')
            byte_offset = saved.tell()
            for v, c, n in zip(actual_pos, actual_color, actual_normal):
                saved.write(struct.pack('<3d4f3f', v.x, v.y, v.z, c.r, c.g, c.b, c.a, n.x, n.y, n.z))
            result = dict(group=group, sample=sample, input_frame_index=frame_index, readback_byte_offset=byte_offset,
                          vertices=3456, actor_transform=transform(actor.get_actor_transform()),
                          component_transform=transform(comp.get_world_transform()),
                          camera_component_transform=transform(capture.get_world_transform()))
            if sample in (0, 11, 59):
                result['topology_uv'] = topology_uv(group + '_' + str(sample))
            result['png'] = export(group + '_%04d.png' % sample)
            R['samples'].append(result); R['images'].append(result['png']); note(group + '_' + str(sample))
    R['readback'] = dict(file=str(readback), bytes=readback.stat().st_size, sha256=sha(readback),
                          record_format='<3d4f3f', stride=52, scope='Actual DynamicMeshComponent CPU arrays; not GPU vertex readback')
    check(len(R['samples']) == 72, 'Incomplete dynamic UE series')
    R['passed'] = True


if __name__ == '__main__':
    R.update(run_id=os.environ['T3B_SERIES_RUN'], process_id=os.getpid(), script_sha256=sha(Path(__file__)),
             engine_version=unreal.SystemLibrary.get_engine_version())
    try:
        main()
    except Exception as error:
        R.update(error=str(error), traceback=traceback.format_exc()); unreal.log_error(str(error))
    finally:
        if 'protected_packages_before' in R:
            R['packages_after'] = inventory()
            R['all_original_packages_unchanged'] = R['packages_after'] == R['protected_packages_before']
            if not R['all_original_packages_unchanged']:
                R['passed'] = False
        flush()
    if not R['passed']:
        raise RuntimeError(R.get('error', 'Dynamic GE series replay failed'))
