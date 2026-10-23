"""Recover a finer Aya hierarchy from draw-local GE palettes.

The frame dumps expose no original bone names, so hierarchy labels are tied to
stable weighted draw regions and retain draw/palette evidence in the JSON.
"""
import argparse, json, math, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_aya_semantic_timeline import read_ppdmp, parse_regs, bbox, norm_matrix

CHANNELS = ('spine_lower', 'spine_upper', 'head',
            'arm_left_upper', 'arm_left_forearm', 'arm_left_hand',
            'arm_right_upper', 'arm_right_forearm', 'arm_right_hand',
            'leg_left', 'leg_right')

def classify(info):
    lo, hi = info['bbox']; cx = (lo[0] + hi[0]) * .5; cy = (lo[1] + hi[1]) * .5
    ax = abs(cx)
    if cy < 1.55 and ax < .35: return 'leg_left' if cx < 0 else 'leg_right'
    if 1.55 <= cy < 2.0 and ax < .16: return 'spine_lower'
    if 2.15 <= cy <= 2.48 and ax < .22: return 'spine_upper'
    if cy > 2.58 and ax < .30: return 'head'
    if 1.65 <= cy <= 2.02 and cx < -.82: return 'arm_left_hand'
    if 2.02 < cy <= 2.34 and cx < -.55: return 'arm_left_forearm'
    if 2.15 <= cy <= 2.48 and -.60 < cx < -.25: return 'arm_left_upper'
    if 1.65 <= cy <= 2.02 and cx > .82: return 'arm_right_hand'
    if 2.02 < cy <= 2.34 and cx > .55: return 'arm_right_forearm'
    if 2.15 <= cy <= 2.48 and .25 < cx < .60: return 'arm_right_upper'
    return None

def extract(path):
    cmds, push = read_ppdmp(str(path)); candidates = {k: [] for k in CHANNELS}
    for i, (typ, size, ptr) in enumerate(cmds[:-1]):
        if typ != 2 or cmds[i + 1][0] != 1: continue
        vt, mats = parse_regs(push, cmds[i + 1][1], cmds[i + 1][2]); info = bbox(push, size, ptr, vt)
        if info is None or not mats: continue
        ch = classify(info)
        if ch is None: continue
        nm = [norm_matrix(v) for _, v in mats]; nw = len(mats); sums = [0.0] * nw; wt = info.get('weight_off')
        if wt and wt[1] % nw == 0:
            wb = wt[1] // nw
            for k in range(info['vertices']):
                for j in range(nw):
                    off = ptr + k * info['stride'] + wt[0] + j * wb
                    q = push[off] / 128.0 if wb == 1 else struct.unpack_from('<H', push, off)[0] / 32768.0 if wb == 2 else struct.unpack_from('<f', push, off)[0] if wb == 4 else 0.0
                    sums[j] += max(0.0, q)
        if not any(sums): sums = [1.0] * nw
        total = sum(sums); weights = [s / total for s in sums]
        matrix = [sum(weights[k] * nm[k][j] for k in range(nw)) for j in range(12)]
        candidates[ch].append((info['vertices'], i, matrix, info, [int(s) for s, _ in mats], weights))
    out = {}
    for ch in CHANNELS:
        if not candidates[ch]: continue
        score, draw, matrix, info, slots, weights = max(candidates[ch], key=lambda x: x[0])
        out[ch] = {'matrix': matrix, 'draw': draw, 'vertices': info['vertices'], 'bbox': info['bbox'], 'palette_slots': slots, 'palette_weights': weights, 'vtype': info['vtype']}
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('capture_dir'); ap.add_argument('out_json'); ap.add_argument('out_csv'); a = ap.parse_args()
    root = Path(a.capture_dir); manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8')); frames = []
    for it in manifest['frames']:
        ch = extract(root / it['file']); frames.append({'frame': it['frame'], 'source': it['file'], 'channels': ch})
        print(f"frame {it['frame']:02d}: " + ', '.join(f"{k}@{v['draw']}" for k,v in ch.items()))
    result = {'schema': 'aya-ge-hierarchy-timeline/v1', 'channels': list(CHANNELS), 'source': 'PPSSPP WebSocket gpu.record.dump; weighted draw hierarchy mapping', 'frames': frames}
    Path(a.out_json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    import csv
    with open(a.out_csv, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f); w.writerow(['frame', 'channel'] + [f'm{i}{j}' for i in range(3) for j in range(4)])
        for fr in frames:
            for ch in CHANNELS:
                if ch in fr['channels']: w.writerow([fr['frame'], ch] + [f'{x:.9f}' for x in fr['channels'][ch]['matrix']])
    print(f'wrote {a.out_json} and {a.out_csv}')

if __name__ == '__main__': main()
