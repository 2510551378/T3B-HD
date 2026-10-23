"""ram_diff.py -- what changes between two RAM snapshots, and does any of it look like
animated vertex data?

Static level geometry does not change; a character's skinned vertex buffer does.  So we
diff two snapshots, keep blocks that changed by a moderate amount, and check whether the
changed bytes form coherent s16 or f32 vertex triples.
"""
import sys

import numpy as np

BLOCK = 4096
SCALE = 9.5367431640625e-05


def triple_score(buf, stride):
    n = len(buf) // stride
    if n < 32:
        return None
    v = np.frombuffer(buf[: n * stride], dtype="<i2")
    v = v[: n * (stride // 2)].reshape(n, stride // 2)[:, :3].astype(np.float64) * SCALE
    d = np.linalg.norm(np.diff(v, axis=0), axis=1)
    span = float(np.linalg.norm(v.max(axis=0) - v.min(axis=0)))
    if span <= 0:
        return None
    med = float(np.median(d))
    good = float(np.mean((d > 1e-6) & (d < max(0.5, med * 3))))
    return good, med / span, span


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a = open(sys.argv[1], "rb").read()
    b = open(sys.argv[2], "rb").read()
    n = min(len(a), len(b))
    print(f"comparing {n:,} bytes")
    A = np.frombuffer(a[:n], dtype=np.uint8)
    B = np.frombuffer(b[:n], dtype=np.uint8)
    blocks = n // BLOCK
    A = A[: blocks * BLOCK].reshape(blocks, BLOCK)
    B = B[: blocks * BLOCK].reshape(blocks, BLOCK)
    frac = (A != B).mean(axis=1)
    changed = frac > 0.05
    print(f"blocks changed >5%: {int(changed.sum())} / {blocks}")

    runs = []
    start = None
    for i, c in enumerate(changed):
        if c and start is None:
            start = i
        elif not c and start is not None:
            runs.append((i - start, start, i))
            start = None
    if start is not None:
        runs.append((blocks - start, start, blocks))
    runs.sort(reverse=True)
    print(f"\ntop {min(10, len(runs))} changed regions:")
    for ln, s, e in runs[:10]:
        seg = b[s * BLOCK:e * BLOCK]
        notes = []
        for stride in (12, 16, 20, 24, 28, 32):
            sc = triple_score(seg, stride)
            if sc and sc[0] > 0.5 and sc[1] < 0.2:
                notes.append(f"s16x{stride}(good={sc[0]:.2f},ratio={sc[1]:.2f},span={sc[2]:.1f}m)")
        print(f"  0x{s * BLOCK:08x}..0x{e * BLOCK:08x}  {ln * BLOCK / 1024:8.1f} KiB  "
              f"change {float(frac[s:e].mean()) * 100:5.1f}%  " + (", ".join(notes) or "-"))


if __name__ == "__main__":
    main()
