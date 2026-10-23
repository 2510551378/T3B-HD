"""Test whether 3rd.fsd dwords are pkg offsets (against known signature starts)."""
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
FSD_LBA, FSD_SIZE = 59584, 7932

SIGS = [b"\x89PNG\r\n\x1a\n", b"PSMF", b"RIFF", b"SEDB", b"pack"]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    starts = {}
    with open(ISO, "rb") as f:
        f.seek(PKG_LBA * SEC)
        pos = 0
        left = PKG_SIZE
        CH = 1 << 23
        while left > 0:
            buf = f.read(min(CH, left))
            if not buf:
                break
            left -= len(buf)
            for s in SIGS:
                i = 0
                while True:
                    i = buf.find(s, i)
                    if i < 0:
                        break
                    starts.setdefault(s, []).append(pos + i)
                    i += 1
            pos += len(buf)
        f.seek(FSD_LBA * SEC)
        fsd = f.read(FSD_SIZE)

    sset = {}
    for s, arr in starts.items():
        for v in arr:
            sset[v] = s
    print(f"signature starts: " + ", ".join(f"{s.decode('latin1')!r}={len(a)}" for s, a in starts.items()))
    print(f"aligned-to-0x800 among them: "
          f"{sum(1 for v in sset if v % 0x800 == 0)}/{len(sset)}")

    dwords = [struct.unpack_from("<I", fsd, o)[0] for o in range(0, len(fsd) - 3, 4)]
    print(f"\nfsd dwords: {len(dwords)}")
    hits = {}
    for idx, v in enumerate(dwords):
        cands = {
            "v": v,
            "v&~0xff": v & 0xFFFFFF00,
            "v>>8": v >> 8,
            "v<<8": v << 8,
            "v&~0xfff": v & 0xFFFFF000,
        }
        for name, c in cands.items():
            if c in sset and c != 0:
                hits.setdefault(name, []).append((idx, hex(v), hex(c), sset[c]))
    for name, arr in hits.items():
        print(f"  {name:10} {len(arr):>4} hits; e.g. " +
              "; ".join(f"[{i}] {vv}->{cc} {s.decode('latin1')}" for i, vv, cc, s in arr[:5]))

    # offsets in fsd that look like increasing sequences
    print("\nfirst 40 dwords:", [hex(v) for v in dwords[:40]])
    # check the tail 8-byte records: count and field stats
    tail = fsd[0x70C:]
    recs = [struct.unpack_from("<II", tail, i) for i in range(0, len(tail) - 7, 8)]
    print(f"\ntail records (8B from 0x70c): {len(recs)}")
    print("  first field values:", sorted(set(r[0] for r in recs))[:10])
    v = [r[1] for r in recs]
    print("  second field: min=%#x max=%#x" % (min(v), max(v)))
    print("  low bytes sorted:", sorted(set(x & 0xFF for x in v))[:20], "... count uniq =", len(set(x & 0xFF for x in v)))
    print("  v>>8 sample:", [hex(x >> 8) for x in v[:12]])
    print("  all second fields divisible by 0x100? ", all(x % 0x100 == 0 for x in v))
    print("  (v>>8) ascending? ", [ (v[i] >> 8) < (v[i+1] >> 8) for i in range(10)])
    print("  v>>8 sorted values:", sorted(set(x >> 8 for x in v))[:10], "max", hex(max(x >> 8 for x in v)))


if __name__ == "__main__":
    main()
