"""Independent known-matrix / known-pixel checks on actual GPU readbacks."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np


def check(ok, why):
    if not ok:
        raise ValueError(why)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    a = p.parse_args()
    out = a.run
    read = lambda name: json.loads((out / name).read_text(encoding='utf-8'))
    request, started, completed, gpu = [read(n) for n in
        ('request.json', 'started.json', 'completed.json', 'actual_gpu_report.json')]
    check(request['build_exit_code'] == completed['exit_code'] == 0, 'Build/run failed')
    check(started['pid'] == completed['pid'] == gpu['pid'], 'Process identity mismatch')
    for row in request['sources']:
        check(sha(Path(row['file'])) == row['sha256'], 'Frozen source changed')
    check(sha(Path(request['expanded_shader']['file'])) == request['expanded_shader']['sha256'], 'Shader changed')
    check(sha(Path(request['run_command'][0])) == request['executable_sha256'], 'Executable changed')
    original = (out / 'T3BGEOrdered.usf').read_bytes()
    expanded = original.replace(b'#include "/Engine/Public/Platform.ush"',
                                b'// Direct FXC probe: Engine Platform include omitted.').replace(
        b'#include "/T3B/Private/T3BGECommon.ush"', (out / 'T3BGECommon.ush').read_bytes())
    check(expanded == Path(request['expanded_shader']['file']).read_bytes(), 'Unexpected shader-body alteration')
    vs = {r['name']: r for r in gpu['vertex_reflection'] if r['used']}
    ps = {r['name']: r for r in gpu['pixel_reflection'] if r['used']}
    check(vs['WorldToClip']['offset'] == 0 and vs['WorldToClip']['size'] == 64 and
          vs['WorldToClip']['class'] == 2, 'Matrix must reflect as row-major 4x4')
    check(ps['ScenePreExposure']['offset'] == 64 and ps['DrawId']['offset'] == 68,
          'Pixel constants did not use the uploaded offsets')
    vertices = np.fromfile(out / 'vertex_inputs.bin', dtype='<f4').reshape(5, 9)
    expected_vertices = np.array([
        [0,0,0,0,.25,.125,.25,.5,1], [1,2,3,.5,.75,1,.5,.25,.125],
        [-17,600,88,1,-1,0,1,0,.5], [35,-600,123,.125,.375,.75,.25,.5,.25],
        [-90,3,223,.25,.5,.25,.5,.75,1]], dtype=np.float32)
    check(vertices.tobytes() == expected_vertices.tobytes(), 'Vertex fixture differs from independent inputs')
    points = np.column_stack([vertices[:, :3].astype(np.float64), np.ones(5)])
    matrices = []
    for i in range(3):
        m = np.fromfile(out / f'matrix_{i}.bin', dtype='<f4').reshape(4, 4)
        if i < 2:
            s = 1 if i == 0 else -1
            expected_m = np.zeros((4, 4), dtype=np.float32)
            expected_m[0, 0] = np.float32(s*2/180)
            expected_m[1, 2] = np.float32(s/2000)
            expected_m[2, 1] = np.float32(2/270)
            expected_m[3, 1] = np.float32(-88)*np.float32(2/270)
            expected_m[3, 2:] = [.5, 1]
        else:
            expected_m = np.array([[1.25,.125,.03125,.0625],[-.25,.75,.0625,.03125],
                                   [.5,-.125,.875,.125],[2,-3,.25,4]], dtype=np.float32)
        check(np.array_equal(m, expected_m), 'Uploaded matrix differs from independent fixture')
        actual = np.fromfile(out / f'matrix_{i}_actual.bin', dtype='<f4').reshape(5, 10)
        expected = points @ expected_m.astype(np.float64)
        error = np.abs(actual[:, :4].astype(np.float64) - expected)
        # Bound for four-term float32 dot products, derived from sum of abs products.
        bound = 8*np.finfo(np.float32).eps*(np.abs(points) @ np.abs(expected_m.astype(np.float64)))
        check(np.all(error <= bound), 'GPU projection exceeds float32 dot-product rounding bound')
        check(actual[:, 4:].tobytes() == vertices[:, 3:].tobytes(), 'VS UV/color were modified')
        transposed_error = np.max(np.abs(actual[:, :4] - points @ expected_m.T))
        check(transposed_error > 1, 'Fixture cannot distinguish matrix transposition')
        matrices.append(dict(case=i, max_absolute_error=float(error.max()),
                             max_rounding_bound=float(bound.max()), transposed_error=float(transposed_error)))
    pixels = []
    for i, exposure in enumerate((.25, 1, 2, 8, 2)):
        color = np.fromfile(out / f'pixel_{i}.rgba_f32', dtype='<f4').reshape(16, 16, 4)
        owner = np.fromfile(out / f'pixel_{i}.owner_u32', dtype='<u4').reshape(16, 16)
        # Texture=(.25,.5,.75,.5), primary=(.5,.25,.75,.5): rgb*2 clamped THEN exposed.
        expected = np.array([.25*exposure, .25*exposure, exposure, .25], dtype=np.float32)
        if i == 4:
            expected[:] = -7
        check(np.all(color == expected), 'HDR output differs from exact known pixel')
        check(np.all(owner == (0 if i == 4 else 0x12345)), 'Owner/discard differs')
        pixels.append(dict(case=i, exposure=exposure, rgba=expected.tolist(), discarded=i == 4,
                           checked_pixels=int(owner.size)))
    report = dict(schema='t3b-world-shader-body-verification/v1', passed=True, pid=gpu['pid'],
                  adapter=gpu['adapter'], matrices=matrices, pixels=pixels,
                  vertex_output_records=15, exact_pixel_checks=1280,
                  UE_module_built=False, UE_shader_compiler_used=False, UE_pass_executed=False,
                  scope='Direct FXC shader body + D3D11 SO/HDR readback; no UBT/UE/RDG/camera API acceptance')
    (out / 'independent_verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
