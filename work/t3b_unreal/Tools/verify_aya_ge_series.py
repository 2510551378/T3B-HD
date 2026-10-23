"""Independent actual-component/PNG check; no recovery/exporter imports."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def identity(t):
    return t == dict(translation=[0., 0., 0.], scale=[1., 1., 1.], quaternion=[0., 0., 0., 1.])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--recovered-v2', type=Path, required=True)
    a = p.parse_args(); out = a.report.parent / 'root_independent_verification.json'
    check(not out.exists(), 'Never replace an independent audit')
    r = json.loads(a.report.read_text(encoding='utf-8')); check(r['passed'], 'Actual acquisition failed')
    request = json.loads((a.report.parent / 'request.json').read_text(encoding='utf-8'))
    done = json.loads((a.report.parent / 'process_completed.json').read_text(encoding='utf-8'))
    check(done['exit_code'] == 0 and done['pid'] == r['process_id'] and request['run_id'] == r['run_id'], 'Process identity differs')
    check(sha(a.report.parent / 'capture_aya_ge_series_executed.py') == r['script_sha256'] == request['script_sha256'],
          'Executed producer identity differs')
    m_path = Path(r['input']['file']); proof_path = Path(r['runtime_proof']['file'])
    check(sha(m_path) == r['input']['sha256'] and sha(proof_path) == r['runtime_proof']['sha256'], 'Input/proof changed')
    m = json.loads(m_path.read_text(encoding='utf-8')); proof = json.loads(proof_path.read_text(encoding='utf-8'))
    v2 = json.loads(a.recovered_v2.read_text(encoding='utf-8'))
    check(v2['passed'] and v2['binary']['sha256'] == m['binary']['sha256'] == proof['input_sha256'],
          'Decode-dependency correction changes evaluated binary')
    check(v2['draws'] == m['draws'] and v2['frames'] == m['frames'] and v2['captures'] == m['captures']
          and v2['lighting_states'] == m['lighting_states'], 'Corrected CLUT verification differs from prior evaluated observations')
    check(sha(Path(v2['binary']['file'])) == v2['binary']['sha256'], 'Corrected series binary changed')
    for row in v2['captures']:
        check(sha(Path(row['path'])) == row['sha256'], 'Original GE dump changed')
    for row in v2['source_manifests']:
        check(sha(Path(row['path'])) == row['sha256'], 'Original capture manifest changed')
    for row in proof['sources']:
        check(sha(Path(row['file'])) == row['sha256'], 'Production source changed')
    paths = [Path(proof['runtime_output']['file']), Path(proof['runtime_uv']['file'])]
    for path, key in zip(paths, ('runtime_output', 'runtime_uv')):
        check(sha(path) == proof[key]['sha256'], 'Runtime output changed')
    comparison = Path(proof['comparison']['file']); check(sha(comparison) == proof['comparison']['sha256'], 'Reference report changed')
    c = json.loads(comparison.read_text(encoding='utf-8'))
    official = comparison.parent / 'official_outputs.bin'
    check(sha(official) == c['official_output_sha256'] and official.read_bytes() == paths[0].read_bytes(),
          'Production outputs differ from independent original software reference')
    source_dtype = np.dtype([('position', '<f4', 3), ('normal', '<f4', 3), ('color', 'u1', 4), ('secondary', 'u1', 3), ('pad', 'u1')])
    actual_dtype = np.dtype([('position', '<f8', 3), ('color', '<f4', 4), ('normal', '<f4', 3)])
    source = np.frombuffer(paths[0].read_bytes(), dtype=source_dtype)
    uv = paths[1].read_bytes()
    readback = Path(r['readback']['file']); check(sha(readback) == r['readback']['sha256'], 'Actual component readback changed')
    actual_bytes = readback.read_bytes(); check(len(actual_bytes) == m['total_vertices'] * 52, 'Actual readback extent differs')
    origins = {g['group']: g['fixed_PSP_world_origin'] for g in r['groups']}
    controls = {}
    for g in r['groups']:
        row = g['hidden_control']; file = Path(row['file']); check(sha(file) == row['sha256'], 'Actual hidden control changed')
        controls[g['group']] = np.asarray(Image.open(file).convert('RGB'), dtype=np.int16)
    sample_results = []; all_image_hashes = {}; max_position_error = 0.
    for frame_index, (entry, frame) in enumerate(zip(r['samples'], m['frames'])):
        check(entry['input_frame_index'] == frame_index and entry['group'] == frame['group'] and entry['sample'] == frame['sample'],
              'Actual sequence/source sample binding differs')
        check(identity(entry['actor_transform']) and identity(entry['component_transform']), 'Unexpected component/actor transform')
        camera = entry['camera_component_transform']
        check(camera['translation'] == [0., 340., 88.] and camera['scale'] == [1., 1., 1.], 'Camera position/scale changed')
        check(np.max(np.abs(np.array(camera['quaternion']) - [0, 0, -2**-.5, 2**-.5])) < 1e-14, 'Camera rotation changed')
        first = frame['first_output_vertex']; src = source[first:first + 3456]
        actual = np.frombuffer(actual_bytes, dtype=actual_dtype, count=3456, offset=entry['readback_byte_offset'])
        expected = (src['position'].astype(np.float64) - np.array(origins[frame['group']])) * r['metres_per_PSP_world_unit'] * 100
        expected = np.ascontiguousarray(expected[:, [0, 2, 1]])
        error = float(np.max(np.abs(actual['position'] - expected))); max_position_error = max(error, max_position_error)
        check(actual['position'].tobytes() == expected.tobytes(), 'Actual position double bits differ')
        expected_color = (src['color'].astype(np.float64) / 255).astype('<f4')
        check(actual['color'].tobytes() == expected_color.tobytes(), 'Actual color F32 bits differ')
        check(actual['normal'].tobytes() == np.ascontiguousarray(src['normal'][:, [0, 2, 1]]).tobytes(), 'Actual normal F32 bits differ')
        if 'topology_uv' in entry:
            for row in entry['topology_uv'].values():
                check(sha(Path(row['file'])) == row['sha256'], 'Actual topology/UV file changed')
            indices = Path(entry['topology_uv']['indices']['file']).read_bytes()
            tex = Path(entry['topology_uv']['uv']['file']).read_bytes()
            check(indices == np.arange(3456, dtype='<u4').tobytes(), 'Original triangle order/multiplicity changed')
            check(tex == uv[first * 8:(first + 3456) * 8], 'Actual original F32 UV bits differ')
        png = Path(entry['png']['file']); check(sha(png) == entry['png']['sha256'], 'Actual sample PNG changed')
        image = np.asarray(Image.open(png).convert('RGB'), dtype=np.int16)
        check(image.shape == (768, 512, 3), 'Unexpected PNG shape')
        changed = np.max(np.abs(image - controls[entry['group']]), axis=2) > 3
        foreground = int(changed.sum()); check(foreground > 1000, 'Actual image is effectively hidden control')
        pixel_sha = hashlib.sha256(image.astype('u1').tobytes()).hexdigest()
        all_image_hashes.setdefault(entry['group'], []).append(pixel_sha)
        sample_results.append(dict(group=entry['group'], sample=entry['sample'], exact_position_bits=True,
                                   exact_color_bits=True, exact_normal_bits=True, foreground_pixels=foreground, pixel_sha256=pixel_sha))
    check(len(sample_results) == len(m['frames']) == 72, 'Incomplete actual replay')
    unique = {k: len(set(v)) for k, v in all_image_hashes.items()}
    check(all(count > 1 for count in unique.values()), 'GPU captures did not visibly change with sample replay')
    check(r['packages_after'] == r['protected_packages_before'], 'Protected package inventory changed')
    for row in r['protected_packages_before']:
        check(sha(Path(row['file'])) == row['sha256'], 'Protected package changed after UE exit')
    result = dict(schema='aya-ge-series-root-independent-audit/v1', passed=True, report_sha256=sha(a.report),
                  corrected_recovery_manifest=dict(file=str(a.recovered_v2.resolve()), sha256=sha(a.recovered_v2)),
                  corrected_texture_decode_dependencies_included=True, corrected_recovery_binary_byte_identical=True,
                  samples_checked=72, vertices_checked=248832, max_position_component_error_cm=max_position_error,
                  all_position_color_normal_bits_exact=True, sampled_topology_triangles=1152, sampled_topology_uv_exact=True,
                  protected_packages=len(r['protected_packages_before']), unique_pixel_images_by_group=unique,
                  samples=sample_results, original_timing_verified=False, original_hardware_pixels_verified=False,
                  limits=['Readback is actual DynamicMeshComponent CPU data, not GPU vertex data.',
                          'Pixel changes prove visible replay, not PSP raster equivalence or known-frame GPU vertex identity.',
                          '30fps playback spacing is presentation only; weapon/native60-source-bone timeline is separate.',
                          'Single-sided translucent baseline still lacks original main depth/texture combine/output-color acceptance.'])
    out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('samples', 'limits', 'corrected_recovery_manifest')}))


if __name__ == '__main__':
    main()
