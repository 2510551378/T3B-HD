"""bone_hunt.py -- find the bone matrix array in a PSP RAM image.

sceGuSetMatrix / skinning keeps boneMatrix as 8 matrices of 12 floats each (3x4, row major)
back to back: 96 floats = 384 bytes.  A valid set has unit-length rows in the rotation part,
small values, and translations that are close to each other (one character) or shared.

    python bone_hunt.py <ram.bin> [<ram2.bin>]
"""
import struct
import sys

import numpy as np


def check(m):
    if not np.isfinite(m).all():
        return False
    if np.abs(m).max() > 1e3:
        return False
    R = m[:, :3]
    n = np.linalg.norm(R, axis=1)
    return bool(np.all((n > 0.85) & (n < 1.15)))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blob = open(sys.argv[1], "rb").read()
    n = len(blob) // 4
    f = np.frombuffer(blob[:n * 4], dtype="<f4")
    hits = []
    stride_words = 1
    for start in range(0, n - 96, stride_words):
        m = f[start:start + 96].reshape(8, 3, 4)
        if not all(check(m[i]) for i in range(8)):
            continue
        t = m[:, :, 3]
        spread = np.abs(t - t.mean(axis=0)).max()
        if spread > 3.0:
            continue
        hits.append((start, spread, t.mean(axis=0)))
    print(f"{len(hits)} candidate bone arrays in {sys.argv[1]}")
    hits.sort(key=lambda h: h[1])
    for start, spread, t in hits[:10]:
        print(f"  @0x{start * 4:08x}  translation spread {spread:6.3f} m  "
              f"centre ({t[0]:7.2f},{t[1]:7.2f},{t[2]:7.2f})")


if __name__ == "__main__":
    main()
