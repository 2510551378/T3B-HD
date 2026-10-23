"""Independent serialized glTF UV multiset and measured-position check.

Does not use the UV build script, RenderData comparator or inferred vertex IDs.
"""
import collections
import hashlib
import json
from pathlib import Path
import struct


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(uvs):
    bits = [struct.pack('<2f',*uv) for uv in uvs]
    return min(b''.join(bits[i:]+bits[:i]) for i in range(3))


def main():
    project = Path(__file__).resolve().parents[1]
    gltf_path = project.parent/'psp_parse/out/AYA_NATIVE_GLTF_20261020/aya_native.gltf'
    assert digest(gltf_path) == '93c78d4014a2255b15915f8150868d1654718b256a72995f25966581a578a4f7'
    gltf = json.loads(gltf_path.read_text(encoding='utf-8'))
    buffer_path = gltf_path.parent/gltf['buffers'][0]['uri']
    assert digest(buffer_path) == '8ce1805dcaf6cdb8f73c0d2d2784a8d20f0e611fbb2d144d0a2d025d839d8454'
    data = buffer_path.read_bytes()
    def values(index, components):
        accessor = gltf['accessors'][index]
        view = gltf['bufferViews'][accessor['bufferView']]
        code,size = {5126:('f',4),5123:('H',2)}[accessor['componentType']]
        stride = view.get('byteStride',components*size)
        offset = view.get('byteOffset',0)+accessor.get('byteOffset',0)
        return [struct.unpack_from('<'+code*components,data,offset+i*stride) for i in range(accessor['count'])]
    source = collections.Counter()
    for primitive in gltf['meshes'][0]['primitives']:
        uv = values(primitive['attributes']['TEXCOORD_0'],2)
        indices = [x[0] for x in values(primitive['indices'],1)]
        assert len(indices)%3 == 0
        for offset in range(0,len(indices),3):
            source[key([uv[i] for i in indices[offset:offset+3]])] += 1
    run = project/'Validation/native_render_data_runs/3a5b71bdf90d4ba9af564917577ff0a7'
    current = json.loads((run/'ue_render_data_probe.json').read_text(encoding='utf-8'))
    old_run = project/'Validation/native_render_data_runs/550c3d234d124e0382d260212efc1d35'
    old = json.loads((old_run/'ue_render_data_probe.json').read_text(encoding='utf-8'))
    actual = collections.Counter(key(uv) for uv in current['triangle_uvs'])
    extras,missing = actual-source,source-actual
    assert sum(source.values()) == 1152 and sum(actual.values()) == 1151
    assert not extras and len(missing) == sum(missing.values()) == 1
    for report in (old,current):
        points = report['point_file']
        path = Path(points['file'])
        assert path.stat().st_size == points['bytes'] and digest(path) == points['sha256']
        assert report['requested_sample_indices'] == [0,30,59]
    before = Path(old['point_file']['file']).read_bytes()
    after = Path(current['point_file']['file']).read_bytes()
    assert before == after and len(after) == 3449*3*3*8
    assert old['used_vertex_ids'] == current['used_vertex_ids'] and old['triangles'] == current['triangles']
    result = {'schema':'root-independent-full-UV-serialized-source-verification/v1','passed':True,
              'source_triangles':1152,'actual_DynamicMesh_triangles':1151,
              'actual_UV_triplets_are_exact_original_F32_values_with_cyclic_orientation':True,
              'extra_UV_multiset_entries':0,'missing_UV_multiplicity':1,
              'missing_UV_triplet_f32_le_hex':next(iter(missing)).hex(),
              'actual3frame_positions_bit_identical_to_old':True,'points_compared':3449*3,
              'point_file_sha256':digest(Path(current['point_file']['file'])),
              'source_gltf_sha256':digest(gltf_path),'source_bin_sha256':digest(buffer_path),
              'new_UE_report_sha256':digest(run/'ue_render_data_probe.json'),
              'old_UE_report_sha256':digest(old_run/'ue_render_data_probe.json'),
              'global_per_vertex_identity_verified':False,'GPU_pixels_verified':False,
              'limits':['UV multiset correspondence does not resolve repeated UV layouts or prove each vertex identity.',
                        'One source duplicate multiplicity remains absent from the converted DynamicMesh.',
                        'Only three actual sample times were compared; no full-motion or GPU visual acceptance.']}
    output = run/'root_independent_full_uv_verification.json'
    assert not output.exists()
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'actual_triangles':1151,'exact_F32_UV_multiset':True,
                      'position_bit_mismatches':0,'global_per_vertex_identity_verified':False}))


if __name__ == '__main__':
    main()
