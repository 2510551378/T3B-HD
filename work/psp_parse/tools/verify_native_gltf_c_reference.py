"""Decode native glTF independently and measure all keyframes against frozen C.

No exporter code or candidate verification output is imported. Selected glTF
scope: one indexed skin, FLOAT TRS animation, shared primitive attributes.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np


def check(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def trs(translation, quaternion, scale):
    x, y, z, w = map(float, quaternion)
    check(abs(x*x+y*y+z*z+w*w-1) < 2e-6, 'rotation quaternion is not normalized')
    rotation = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                         [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                         [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]], dtype=np.float64)
    result = np.eye(4)
    result[:3, :3] = rotation @ np.diag(scale)
    result[:3, 3] = translation
    return result


def verify(gltf_path, probe_path, clip_path):
    document = json.loads(gltf_path.read_bytes())
    check(document['asset']['version'] == '2.0', 'wrong interchange version')
    root = gltf_path.resolve().parent
    buffers = []
    for buffer in document['buffers']:
        path = (root / buffer['uri']).resolve()
        check(path.is_relative_to(root), 'external buffer path escapes artifact directory')
        data = path.read_bytes()
        check(len(data) == buffer['byteLength'], 'buffer length differs')
        buffers.append(data)
    types = {5121:np.dtype('<u1'), 5123:np.dtype('<u2'), 5125:np.dtype('<u4'), 5126:np.dtype('<f4')}
    widths = {'SCALAR':1, 'VEC2':2, 'VEC3':3, 'VEC4':4, 'MAT4':16}

    def accessor(index):
        item = document['accessors'][index]
        check('sparse' not in item, 'sparse accessors outside this verifier scope')
        view = document['bufferViews'][item['bufferView']]
        dtype, width = types[item['componentType']], widths[item['type']]
        count = item['count']
        stride = view.get('byteStride', width*dtype.itemsize)
        begin = view.get('byteOffset', 0)+item.get('byteOffset', 0)
        end = begin+(count-1)*stride+width*dtype.itemsize
        check(count > 0 and stride >= width*dtype.itemsize and begin % dtype.itemsize == 0, 'invalid accessor shape/alignment')
        check(end <= view.get('byteOffset', 0)+view['byteLength'] <= len(buffers[view['buffer']]), 'accessor exceeds buffer view')
        result = np.ndarray((count, width), dtype=dtype, buffer=buffers[view['buffer']],
                            offset=begin, strides=(stride, dtype.itemsize)).copy()
        check(not item.get('normalized', False), 'normalized integer accessor outside selected scope')
        return result

    check(len(document['skins']) == 1 and len(document['meshes']) == 1, 'one skin/mesh required')
    skin = document['skins'][0]
    primitives = document['meshes'][0]['primitives']
    attributes = primitives[0]['attributes']
    check(all(p['attributes'] == attributes and p.get('mode', 4) == 4 for p in primitives), 'primitive attribute/topology layout differs')
    position = accessor(attributes['POSITION']).astype(np.float64)
    joints = accessor(attributes['JOINTS_0']).astype(np.int64)
    weights = accessor(attributes['WEIGHTS_0']).astype(np.float64)
    check('JOINTS_1' not in attributes and 'WEIGHTS_1' not in attributes, 'second influence set outside selected scope')
    check(joints.shape == weights.shape and len(position) == len(weights), 'skin attribute lengths differ')
    check(joints.min() >= 0 and joints.max() < len(skin['joints']), 'joint index out of range')
    check(np.all(weights >= 0) and np.max(np.abs(weights.sum(axis=1)-1)) < 1e-6, 'native weights not normalized')
    ordered = np.concatenate([accessor(p['indices']).reshape(-1) for p in primitives])
    check(np.array_equal(ordered, np.arange(len(position))), 'source triangle/vertex order differs')
    inverse_bind = accessor(skin['inverseBindMatrices']).astype(np.float64).reshape(-1,4,4).transpose(0,2,1)
    check(len(inverse_bind) == len(skin['joints']), 'inverse bind count differs')
    nodes = document['nodes']
    parent = [-1]*len(nodes)
    for i, node in enumerate(nodes):
        for child in node.get('children', []):
            check(0 <= child < len(nodes) and parent[child] == -1, 'invalid/shared-parent graph')
            parent[child] = i
    animation = document['animations'][0]
    channels = []
    times = None
    for channel in animation['channels']:
        sampler = animation['samplers'][channel['sampler']]
        check(sampler.get('interpolation', 'LINEAR') == 'LINEAR', 'only keyframes from LINEAR channels are verified')
        channel_times = accessor(sampler['input']).reshape(-1)
        if times is None:
            times = channel_times
        check(np.array_equal(times, channel_times), 'TRS channels have different sample clocks')
        values = accessor(sampler['output'])
        check(len(values) == len(times), 'animation value/time counts differ')
        channels.append((channel['target']['node'], channel['target']['path'], values))
    check(np.all(np.diff(times) > 0), 'animation times not increasing')
    clip = clip_path.read_bytes()
    check(clip[:8] == b'T3BSKN2\0', 'wrong source reference clip')
    version, bones, packets, vertices, frames = struct.unpack_from('<5I', clip, 8)
    check(version == 2 and vertices == len(position) and frames == len(times), 'clip/asset dimensions differ')
    time_offset = 56+4*bones+16*packets+100*vertices
    source_times = np.frombuffer(clip, dtype='<f4', count=frames, offset=time_offset)
    check(np.array_equal(source_times, times), 'native/source keyframe times differ')
    units, floor = struct.unpack_from('<2f', clip, 44)
    frozen = np.loadtxt(probe_path, delimiter=',', dtype=np.float64)
    check(frozen.shape == (frames*vertices,5), 'frozen C probe shape differs')
    check(np.array_equal(frozen[:,0],np.repeat(np.arange(frames),vertices)) and
          np.array_equal(frozen[:,1],np.tile(np.arange(vertices),frames)), 'frozen C sample order differs')
    expected = frozen[:,2:5].astype(np.float32).reshape(frames,vertices,3)
    expected[:,:,0] *= np.float32(units)
    expected[:,:,1] = (expected[:,:,1]-np.float32(floor))*np.float32(units)
    expected[:,:,2] *= np.float32(units)
    homogeneous = np.column_stack((position,np.ones(vertices)))
    per_frame = []
    for sample in range(frames):
        properties = [{key:node.get(key,default) for key,default in
                       [('translation',[0,0,0]),('rotation',[0,0,0,1]),('scale',[1,1,1])]} for node in nodes]
        for node, path, values in channels:
            check(path in ('translation','rotation','scale'), 'unsupported animation target')
            properties[node][path] = values[sample]
        local = []
        for node, prop in zip(nodes,properties):
            check('matrix' not in node, 'matrix/TRS mixed graph outside selected scope')
            local.append(trs(prop['translation'],prop['rotation'],prop['scale']))
        world, visiting = {}, set()

        def global_matrix(index):
            if index not in world:
                check(index not in visiting, 'node graph contains a cycle')
                visiting.add(index)
                world[index] = local[index] if parent[index] < 0 else global_matrix(parent[index]) @ local[index]
                visiting.remove(index)
            return world[index]

        transforms = np.stack([global_matrix(node) @ inverse_bind[j] for j,node in enumerate(skin['joints'])])
        result = np.zeros((vertices,4),dtype=np.float64)
        for influence in range(weights.shape[1]):
            moved = np.einsum('nij,nj->ni',transforms[joints[:,influence]],homogeneous)
            result += moved*weights[:,influence,None]
        check(np.all(np.isfinite(result)), 'nonfinite native positions')
        delta = result[:,:3]-expected[sample].astype(np.float64)
        lengths = np.linalg.norm(delta,axis=1)
        worst = int(np.argmax(lengths))
        per_frame.append({'sample':sample,'time':float(times[sample]),'max_euclidean_pc':float(lengths[worst]),
                          'rms_pc':float(np.sqrt(np.mean(lengths*lengths))), 'worst_vertex':worst,
                          'candidate_pc':result[worst,:3].tolist(),'frozen_C_pc':expected[sample,worst].astype(float).tolist()})
    return {'schema':'native-gltf-independent-frozen-C-comparison/v1',
        'structural_checks_passed':True, 'keyframe_comparison_executed':True,
        'gltf':str(gltf_path.resolve()),'gltf_sha256':digest(gltf_path),
        'frozen_C_probe':str(probe_path.resolve()),'frozen_C_probe_sha256':digest(probe_path),
        'source_clip':str(clip_path.resolve()),'source_clip_sha256':digest(clip_path),
        'vertices':vertices,'frames':frames,'points_compared':vertices*frames,
        'max_euclidean_pc':max(r['max_euclidean_pc'] for r in per_frame),'per_frame':per_frame,
        'unreal_importer_executed':False,
        'limits':['This independently decodes the serialized native candidate and measures keyframes; it does not certify zero error.',
                  'Subframe interpolation, materials, normals and rendered pixels are outside this comparison.',
                  'The native candidate normalizes weights; the exact affine source runtime remains the reference.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gltf',type=Path,required=True)
    parser.add_argument('--c-probe',type=Path,required=True)
    parser.add_argument('--source-clip',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    result = verify(args.gltf,args.c_probe,args.source_clip)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('structural_checks_passed','points_compared','max_euclidean_pc')}))


if __name__ == '__main__':
    main()
