"""Step 3: find vertex-buffer stride inside a pack section (float32 and s16 hypotheses)."""
import math
import os
import struct
import sys

DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")


def load(tag):
    for fn in os.listdir(DIR):
        if fn.startswith(tag):
            with open(os.path.join(DIR, fn), "rb") as f:
                return f.read()
    raise SystemExit("missing " + tag)


def f32(b, o):
    return struct.unpack_from("<f", b, o)[0]


def plausible_pos(b, o, limit=10000.0):
    try:
        x, y, z = f32(b, o), f32(b, o + 4), f32(b, o + 8)
    except Exception:
        return False
    for v in (x, y, z):
        if math.isnan(v) or math.isinf(v) or abs(v) > limit:
            return False
    if x == 0.0 and y == 0.0 and z == 0.0:
        return False
    return True


def normalish(b, o):
    try:
        x, y, z = f32(b, o), f32(b, o + 4), f32(b, o + 8)
    except Exception:
        return False
    n = math.sqrt(x * x + y * y + z * z)
    return 0.9 < n < 1.1


def scan(body, maxstride=80, samples=600):
    best = []
    n = len(body)
    for S in range(12, maxstride + 1, 4):
        for P in range(0, min(S, 32), 4):
            if P + 8 >= n:
                continue
            cnt = ok = nrm = 0
            for i in range(samples):
                o = P + i * S
                if o + 12 > n:
                    break
                cnt += 1
                if plausible_pos(body, o):
                    ok += 1
                if o + 24 <= n and normalish(body, o + 12):
                    nrm += 1
            if cnt < 50:
                continue
            best.append((ok / cnt, nrm / cnt, S, P, cnt))
    best.sort(reverse=True)
    return best[:8]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blob = load("t8_a")
    print(f"t8_a size={len(blob):,}")
    # header pairs
    pairs = []
    for i in range(0, 15):
        sz, off = struct.unpack_from("<II", blob, 8 + i * 8)
        pairs.append((sz, off))
    print("pairs:", [(hex(a), hex(b)) for a, b in pairs])
    for idx, (sz, off) in enumerate(pairs):
        if sz == 0 or off == 0 or off + sz > len(blob):
            continue
        body = blob[off:off + sz]
        res = scan(body, 64)
        print(f"\n-- section {idx}: off={off:#x} size={sz:,}")
        print("   head:", body[:32].hex(" "))
        for pos, nrm, S, P, cnt in res[:4]:
            print(f"   stride={S:>2} phase={P:>2} pos_ok={pos:.2f} normal_ok={nrm:.2f} samples={cnt}")


if __name__ == "__main__":
    main()
