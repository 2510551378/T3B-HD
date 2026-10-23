"""Extract PSP GE float24 BONE matrices from consecutive .ppdmp captures.

PPSSPP's recorder stores incremental REGISTERS commands. Replay them up to
each PRIM; later commands in that block may prepare another draw.
BONE0.. commands are encoded as command 0x2A (matrix slot, in units of
12) followed by twelve 0x2B float24 payloads.  We retain the largest human-sized
weighted draw for each slot, giving a deterministic per-frame motion sample.
"""
import argparse, json, math, struct
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from extract_runtime_character import read_ppdmp, layout, SCALE
from replay_ge_draws import iter_ge_draws


def float24(payload: int) -> float:
    """GE float24: standard IEEE float with its low 8 mantissa bits removed."""
    return struct.unpack('<f', struct.pack('<I', (payload & 0xFFFFFF) << 8))[0]


def register_state(push: bytes, size: int, ptr: int):
    """Decode writes in one block only; this is NOT a per-draw state snapshot.

    New consumers must use iter_ge_draws for PRIM-time state. Retained for
    callers that intentionally inspect raw command blocks.
    """
    words = struct.unpack_from(f'<{size // 4}I', push, ptr)
    vtype = None
    matrices = []
    for j, word in enumerate(words):
        cmd = word >> 24
        if cmd == 0x12:
            vtype = word & 0xFFFFFF
        if cmd != 0x2A:
            continue
        vals = []
        k = j + 1
        while k < len(words) and words[k] >> 24 == 0x2B and len(vals) < 12:
            vals.append(float24(words[k] & 0xFFFFFF))
            k += 1
        if len(vals) == 12:
            matrices.append({'slot': int(word & 0xFFFFFF), 'values': vals})
    return vtype, matrices


def human_weighted(push: bytes, size: int, ptr: int, vtype: int):
    if not vtype or not ((vtype >> 9) & 3):
        return None
    try:
        stride, offs = layout(vtype)
        po, ps = offs['pos']
    except (KeyError, ValueError):
        return None
    if ps != 6 or stride <= 0 or ptr + size > len(push):
        return None
    count = size // stride
    if count < 4:
        return None
    arr = []
    for i in range(count):
        off = ptr + i * stride + po
        x, y, z = struct.unpack_from('<3h', push, off)
        arr.append((x * SCALE, y * SCALE, z * SCALE))
    lo = [min(v[k] for v in arr) for k in range(3)]
    hi = [max(v[k] for v in arr) for k in range(3)]
    dx, dy, dz = [hi[k] - lo[k] for k in range(3)]
    # Aya's weighted draws are in a ~3.1-unit local body; discard environment,
    # UI and giant enemy buffers while retaining small limbs.
    if lo[1] < -0.05 or hi[1] > 3.25 or lo[0] < -1.35 or hi[0] > 1.35:
        return None
    if dz > 1.0 or dx > 1.8 or dy > 3.3:
        return None
    return {'vertices': count, 'bbox': [lo, hi], 'vtype': int(vtype)}


def extract_frame(path: Path):
    cmds, push = read_ppdmp(str(path))
    best = {}
    for draw in iter_ge_draws(cmds, push):
        i, size, ptr, vtype = draw['draw'], draw['size'], draw['pointer'], draw['vtype']
        mats = [{'slot': slot * 12, 'values': [float24(w) for w in words]}
                for slot, words in draw['palette_payloads'].items()]
        info = human_weighted(push, size, ptr, vtype)
        if info is None:
            continue
        for mat in mats:
            slot = mat['slot']
            candidate = dict(info)
            candidate.update({'slot': slot, 'matrix': mat['values'], 'draw': i})
            if slot not in best or candidate['vertices'] > best[slot]['vertices']:
                best[slot] = candidate
    bones = {}
    for slot, item in sorted(best.items()):
        bones[str(slot // 12)] = item
    return bones, len(cmds), len(push)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('capture_dir')
    ap.add_argument('out')
    a = ap.parse_args()
    root = Path(a.capture_dir)
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    frames = []
    for item in manifest['frames']:
        p = root / item['file']
        bones, commands, push = extract_frame(p)
        frames.append({'frame': item['frame'], 'source': item['file'],
                       'commands': commands, 'pushbuf_bytes': push, 'bones': bones})
        print(f"frame {item['frame']:02d}: bones={','.join(bones) or '-'} draws={len(bones)}")
    result = {
        'schema': 'aya-ge-timeline/v1',
        'source': 'PPSSPP WebSocket gpu.record.dump; GE BONE float24 commands',
        'layout': '3x4 row-major; slot index / 12',
        'frames': frames,
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'wrote {out} ({len(frames)} frames)')


if __name__ == '__main__':
    main()
