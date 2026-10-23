"""Check original +5 offset against GE float24 uncertainty, without fitting.

Component-wise interval overlap is consistency evidence, not a simultaneous
solution for correlated source matrices and not a same-invocation identity.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def check(value, why):
    if not value:
        raise ValueError(why)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def checked_file(item):
    path = Path(item['file'])
    check(sha(path) == item['sha256'], 'Evidence changed')
    return path


def f24_affine_interval(payload):
    # GE discarded the low8 IEEE bits. Sign is retained, so negative endpoints
    # reverse order. Both endpoints are actual finite float32 values.
    words = np.array(payload, dtype='<u4') << 8
    a, b = words.view('<f4').astype(float), (words | 255).view('<f4').astype(float)
    check(np.isfinite(a).all() and np.isfinite(b).all(), 'Nonfinite GE uncertainty interval')
    lo, hi = np.eye(4), np.eye(4)
    lo[:, :3], hi[:, :3] = np.minimum(a, b).reshape(4, 3), np.maximum(a, b).reshape(4, 3)
    return lo, hi


def rounded_matmul(a, b):
    """Monotone F32 interval multiply/add in retained non-fused dot order."""
    lo = np.zeros((a[0].shape[0], b[0].shape[1]))
    hi = lo.copy()
    for k in range(a[0].shape[1]):
        products = np.array([a[x][:, k:k+1]*b[y][k:k+1, :] for x, y in ((0, 0), (0, 1), (1, 0), (1, 1))])
        pmin = products.min(0).astype('<f4').astype(float)
        pmax = products.max(0).astype('<f4').astype(float)
        lo = (lo+pmin).astype('<f4').astype(float)
        hi = (hi+pmax).astype('<f4').astype(float)
    check(np.isfinite(lo).all() and np.isfinite(hi).all(), 'Unbounded F32 interval')
    return lo, hi


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recovery', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    check(not args.out.exists(), 'Never replace interval evidence')
    args.out.mkdir(parents=True)
    recovery = read(args.recovery)
    weapon = read(checked_file(recovery['weapon']))
    scene = read(checked_file(recovery['scene']))
    raw = checked_file(weapon['binary']).read_bytes()
    markers = checked_file(recovery['original_marker']['binary']).read_bytes()
    root = np.frombuffer(markers, dtype='<u4', count=16, offset=16).reshape(4, 4)
    source1 = np.frombuffer(markers, dtype='<f4', count=16, offset=80).reshape(4, 4).astype(float)
    binding_checks, rows = [], []
    for i, frame in enumerate(scene['frames']):
        d = weapon['draws'][weapon['frames'][i]['first_draw']]
        at = d['binary_byte_offset']
        bone = np.frombuffer(raw, dtype='<u4', count=12, offset=at+1072).reshape(4, 3)
        check(np.array_equal(root[:, :3] >> 8, bone >> 8), 'Original source0 root skin does not reproduce observed BONE payload')
        binding_checks.append(dict(sample=i, original_source0_full_F32_high24_equals_GE_BONE=True))
        world = np.frombuffer(raw, dtype='<u4', count=12, offset=at+1024) >> 8
        main = next(x for x in frame['draws'] if x['category'] == 'body')
        marker_world = rounded_matmul((source1, source1), f24_affine_interval(world))
        selected = [x for x in frame['draws'] if x['category'] == 'unweighted_strip_fx' and x['vtype'] == 0x11e and x['source_vertices'] in (14, 15)]
        for fx in selected:
            observed = f24_affine_interval(fx['VIEW_payload'])
            # FX WORLD is identity in these six draws; otherwise origin differs.
            wlo, _ = f24_affine_interval(fx['WORLD_payload'])
            check(np.array_equal(wlo, np.eye(4)), 'Candidate FX WORLD is not exact identity payload')
            tests = []
            for offset in (0, 5, 7):
                point = np.array([[0., 0., float(offset), 1.]])
                expected = rounded_matmul(rounded_matmul((point, point), marker_world), f24_affine_interval(main['VIEW_payload']))
                overlaps = (expected[1][0, :3] >= observed[0][3, :3]) & (expected[0][0, :3] <= observed[1][3, :3])
                tests.append(dict(original_offset_or_control=offset, overlaps_each_view_component=overlaps.tolist(),
                    all_three_component_intervals_overlap=bool(overlaps.all()),
                    predicted_VIEW_translation_min=expected[0][0, :3].tolist(), predicted_VIEW_translation_max=expected[1][0, :3].tolist()))
            check(tests[1]['all_three_component_intervals_overlap'], 'Original +5 prediction inconsistent with retained GE')
            check(not tests[0]['all_three_component_intervals_overlap'] and not tests[2]['all_three_component_intervals_overlap'], 'Offset controls do not discriminate these observations')
            rows.append(dict(sample=i, record=fx['register_record'], word=fx['register_word'], source_vertices=fx['source_vertices'],
                observed_VIEW_translation_min=observed[0][3, :3].tolist(), observed_VIEW_translation_max=observed[1][3, :3].tolist(), tests=tests))
    check(len(rows) == 6, 'Expected three pairs, not six independent emitter origins')
    result = dict(schema='source-marker-FX-float24-interval-consistency/v1', passed=True,
        recovery=dict(file=str(args.recovery.resolve()), sha256=sha(args.recovery)), source0_binding_checks=binding_checks,
        rows=rows, distinct_origin_samples=3, geometric_offset_fitted=False, same_invocation_confirmed=False,
        producer=dict(file=str(Path(__file__).resolve()), sha256=sha(Path(__file__))),
        limits=['F32 input values range over all256 low-byte possibilities consistent with each F24 payload; source1 and the observed offset5 are unchanged original data.',
                'Intervals use separate rounded F32 multiply/add and default-prefix behavior; this is a scoped arithmetic model, not all PPSSPP JIT/prefix paths.',
                'Repeated matrix elements are correlated. Component interval overlap does not prove one jointly realizable full-matrix solution or the emitter identity.',
                'Offset0 and offset7 are diagnostic counterfactuals for this14/15-vertex cluster. Offset7 is a real input of another captured effect and is not globally wrong.',
                'No exact CPU/GE same-frame marker, named muzzle or gameplay hit origin is established.'])
    (args.out/'verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(passed=True, source0_high24_matches=12, observations=6, independent_origin_samples=3,
                         offset5_intersections=6, offset0_intersections=0, offset7_intersections=0)))


if __name__ == '__main__':
    main()
