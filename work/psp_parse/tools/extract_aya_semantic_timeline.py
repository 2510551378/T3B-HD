"""Map per-draw GE bone palettes to four Aya semantic motion channels.

GE matrix slot numbers are local to each draw: slot 0 in a left-arm draw is
not globally the same bone as slot 0 in a leg draw.  This extractor therefore
associates each palette with its weighted vertex bbox first, then selects stable
representatives for spine, left/right arm, and legs.
"""
import argparse, json, math, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_runtime_character import read_ppdmp, layout, SCALE

CHANNELS = ('spine', 'arm_left', 'arm_right', 'legs')

def f24(x):
    return struct.unpack('<f', struct.pack('<I', (x & 0xFFFFFF) << 8))[0]

def parse_regs(push, size, ptr):
    words = struct.unpack_from(f'<{size // 4}I', push, ptr)
    vt = None; mats = []
    for j, w in enumerate(words):
        if w >> 24 == 0x12: vt = w & 0xFFFFFF
        if w >> 24 != 0x2A: continue
        vals = []; k = j + 1
        while k < len(words) and words[k] >> 24 == 0x2B and len(vals) < 12:
            vals.append(f24(words[k])); k += 1
        if len(vals) == 12: mats.append((w & 0xFFFFFF, vals))
    return vt, mats

def norm_matrix(vals):
    scale = sum(math.sqrt(sum(vals[r * 4 + c] ** 2 for c in range(3))) for r in range(3)) / 3.0
    if scale < 1e-5: scale = 1.0
    out = [0.0] * 12
    for r in range(3):
        for c in range(3): out[r * 4 + c] = vals[r * 4 + c] / scale
    return out

def bbox(push, size, ptr, vt):
    if not vt or not ((vt >> 9) & 3): return None
    try: stride, offs = layout(vt); po, ps = offs['pos']
    except (KeyError, ValueError): return None
    if ps != 6 or stride <= 0: return None
    n = (size - po) // stride
    if n < 4: return None
    pts = [struct.unpack_from('<3h', push, ptr + i * stride + po) for i in range(n)]
    lo = [min(p[k] for p in pts) * SCALE for k in range(3)]
    hi = [max(p[k] for p in pts) * SCALE for k in range(3)]
    if lo[1] < -0.05 or hi[1] > 3.25 or lo[0] < -1.35 or hi[0] > 1.35: return None
    if hi[2] - lo[2] > 1.0 or hi[0] - lo[0] > 1.8: return None
    return {'vertices': n, 'bbox': [lo, hi], 'vtype': vt, 'stride': stride, 'pos_off': po, 'weight_off': offs.get('wt')}

def classify(info):
    lo, hi = info['bbox']; cx = (lo[0] + hi[0]) * .5; cy = (lo[1] + hi[1]) * .5
    ax = abs(cx)
    if cy < 1.55 and ax < .35: return 'legs'
    if 1.45 <= cy <= 2.2 and ax < .32: return 'spine'
    if 1.55 <= cy <= 2.45 and cx < -.55: return 'arm_left'
    if 1.55 <= cy <= 2.45 and cx > .55: return 'arm_right'
    return None

def frame(path):
    cmds, push = read_ppdmp(str(path)); candidates = {k: [] for k in CHANNELS}
    for i, (typ, size, ptr) in enumerate(cmds[:-1]):
        if typ != 2 or cmds[i + 1][0] != 1: continue
        vt, mats = parse_regs(push, cmds[i + 1][1], cmds[i + 1][2])
        info = bbox(push, size, ptr, vt)
        if info is None or not mats: continue
        ch = classify(info)
        if ch is None: continue
        # Aggregate the local palette using the draw's actual vertex weights.
        # The recorder omits explicit indices for this VTYPE; the GE palette
        # order is the same order as the weight fields in each vertex record.
        nm = [norm_matrix(v) for _, v in mats]; nw = len(mats); sums = [0.0] * nw
        wt = info.get('weight_off')
        if wt and wt[1] % nw == 0:
            wb = wt[1] // nw
            for k in range(info['vertices']):
                for j in range(nw):
                    off = ptr + k * info['stride'] + wt[0] + j * wb
                    if wb == 1: q = push[off] / 128.0
                    elif wb == 2: q = struct.unpack_from('<H', push, off)[0] / 32768.0
                    elif wb == 4: q = struct.unpack_from('<f', push, off)[0]
                    else: q = 0.0
                    sums[j] += max(0.0, q)
        if not any(sums): sums = [1.0] * nw
        total = sum(sums); weights = [s / total for s in sums]
        matrix = [sum(weights[k] * nm[k][j] for k in range(nw)) for j in range(12)]
        lo, hi = info['bbox']; cx = (lo[0] + hi[0]) * .5
        score = info['vertices']
        candidates[ch].append((score, i, matrix, info, [int(s) for s, _ in mats]))
    out = {}
    for ch in CHANNELS:
        if candidates[ch]:
            score, draw, matrix, info, slots = max(candidates[ch], key=lambda x: x[0])
            out[ch] = {'matrix': matrix, 'draw': draw, 'vertices': info['vertices'],
                       'bbox': info['bbox'], 'palette_slots': slots,
                       'palette_weights': weights, 'vtype': info['vtype']}
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('capture_dir'); ap.add_argument('out_json'); ap.add_argument('out_csv')
    a = ap.parse_args(); root = Path(a.capture_dir); manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    frames = []
    for it in manifest['frames']:
        channels = frame(root / it['file']); frames.append({'frame': it['frame'], 'source': it['file'], 'channels': channels})
        print(f"frame {it['frame']:02d}: " + ', '.join(f"{k}@{v['draw']}[{','.join(map(str,v['palette_slots']))}]" for k,v in channels.items()))
    result = {'schema': 'aya-ge-semantic-timeline/v1', 'channels': list(CHANNELS),
              'source': 'PPSSPP WebSocket gpu.record.dump; per-draw weighted bbox mapping', 'frames': frames}
    Path(a.out_json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    with open(a.out_csv, 'w', encoding='utf-8', newline='') as f:
        import csv
        w = csv.writer(f); w.writerow(['frame', 'channel'] + [f'm{i}{j}' for i in range(3) for j in range(4)])
        for fr in frames:
            for ch in CHANNELS:
                if ch in fr['channels']: w.writerow([fr['frame'], ch] + [f'{x:.9f}' for x in fr['channels'][ch]['matrix']])
    print(f'wrote {a.out_json} and {a.out_csv}')

if __name__ == '__main__': main()
