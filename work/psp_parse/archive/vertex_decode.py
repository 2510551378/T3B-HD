"""Step 17: decode the 20-byte vertex records (stride confirmed by 0xCCCC ruler)."""
import os
import struct
import sys

DIR = os.path.join(os.path.dirname(__file__), "extract", "packs")


def load(fn):
    with open(os.path.join(DIR, fn), "rb") as f:
        return f.read()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t8 = load("t8_a_0x444e5000.pack")
    sec = t8[0x80:0x80 + 0x37250]
    geo = sec[0x30:0x225E8]
    pos = []
    i = 0
    while True:
        i = geo.find(b"\xcc\xcc", i)
        if i < 0:
            break
        if i % 2 == 0:
            pos.append(i)
        i += 1
    # find the longest 20-stride run
    runs = []
    cur = [pos[0]]
    for p in pos[1:]:
        if p - cur[-1] == 20:
            cur.append(p)
        else:
            runs.append(cur)
            cur = [p]
    runs.append(cur)
    runs.sort(key=len, reverse=True)
    run = runs[0]
    print(f"longest run: {len(run)} vertices, marker from 0x{run[0]:x} to 0x{run[-1]:x}")
    base = run[0] - 10          # marker sits at +10 inside the record
    print(f"record base = 0x{base:x}")
    print(f"{'idx':>4} {'off':>8}  raw 20 bytes                                        u16x5                      f32@+8?")
    for k in range(6):
        o = base + k * 20
        rec = geo[o:o + 20]
        u = struct.unpack_from("<5H", rec)
        f8 = struct.unpack_from("<f", rec, 8)[0]
        f12 = struct.unpack_from("<f", rec, 12)[0]
        f16 = struct.unpack_from("<f", rec, 16)[0]
        print(f"{k:>4} 0x{o:06x}  {rec.hex(' ')}  {str(u):<26} {f8:>10.3f} {f12:>10.3f} {f16:>10.3f}")
    # try interpreting as s16 triples at each phase
    print("\ns16 phases over 64 records:")
    for ph in range(0, 20, 2):
        vals = []
        for k in range(64):
            o = base + k * 20 + ph
            if o + 6 > len(geo):
                break
            vals.append(struct.unpack_from("<3h", geo, o))
        if len(vals) < 8:
            continue
        xs = [v[0] for v in vals]
        ys = [v[1] for v in vals]
        zs = [v[2] for v in vals]
        print(f"  +{ph:>2}: first={vals[0]} range_x={min(xs)}..{max(xs)} range_y={min(ys)}..{max(ys)} "
              f"range_z={min(zs)}..{max(zs)}")
    print("\nf32 triples at phases:")
    for ph in (0, 4, 8, 12, 16):
        vals = []
        for k in range(64):
            o = base + k * 20 + ph
            if o + 12 > len(geo):
                break
            vals.append(struct.unpack_from("<3f", geo, o))
        if len(vals) < 8:
            continue
        xs = [v[0] for v in vals]
        ys = [v[1] for v in vals]
        zs = [v[2] for v in vals]
        print(f"  +{ph:>2}: first={tuple(round(x,3) for x in vals[0])} "
              f"rx={min(xs):.2f}..{max(xs):.2f} ry={min(ys):.2f}..{max(ys):.2f}")


if __name__ == "__main__":
    main()
