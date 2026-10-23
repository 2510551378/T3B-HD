"""Step 7: derive each pack's section count by scoring tiling consistency, then re-validate."""
import collections
import json
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
OUT = os.path.join(os.path.dirname(__file__), "extract", "packs")


def align(v, a=0x800):
    return (v + a - 1) // a * a


def find_packs(f):
    f.seek(PKG_LBA * SEC)
    pos, left, out = 0, PKG_SIZE, []
    CH = 1 << 23
    while left > 0:
        buf = f.read(min(CH, left))
        if not buf:
            break
        left -= len(buf)
        i = 0
        while True:
            i = buf.find(b"pack", i)
            if i < 0:
                break
            if (pos + i) % 0x800 == 0:
                out.append(pos + i)
            i += 1
        pos += len(buf)
    return out


def score(pairs):
    """How many consecutive sections tile exactly; also require monotonic growth."""
    good = 0
    end = None
    for sz, off in pairs:
        if sz == 0 and off == 0:
            continue
        if off == 0 or sz > 1 << 30:
            return -1
        if end is not None:
            if off == end:
                good += 1
            elif 0 < off - end <= 0x100:
                good += 0.5
            else:
                return good - 1
        end = off + sz
    return good


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(OUT, exist_ok=True)
    with open(ISO, "rb") as f:
        starts = find_packs(f)
        nxt = {starts[i]: (starts[i + 1] if i + 1 < len(starts) else PKG_SIZE)
               for i in range(len(starts))}
        by_type = collections.Counter()
        counts_by_type = collections.defaultdict(collections.Counter)
        rows = []
        for h in starts:
            f.seek(PKG_LBA * SEC + h)
            hdr = f.read(0x100)
            typ = struct.unpack_from("<I", hdr, 4)[0]
            span = nxt[h] - h
            best = None
            for n in range(1, 17):
                pairs = [struct.unpack_from("<II", hdr, 8 + i * 8) for i in range(n)]
                s = score(pairs)
                if s < 0:
                    continue
                ends = [off + sz for sz, off in pairs if sz]
                if not ends:
                    continue
                end = max(ends)
                if align(end) > span:
                    continue
                if best is None or s > best[1]:
                    best = (n, s, end)
            if best is None:
                by_type[(typ, "none")] += 1
                continue
            n, s, end = best
            by_type[(typ, "ok")] += 1
            counts_by_type[typ][n] += 1
            rows.append({"offset": h, "type": typ, "n": n, "tile_score": s,
                         "end": end, "span": span, "size": span})
        print("per type (ok/none):", dict(by_type))
        print("\nsection-count distribution per type:")
        for typ in sorted(counts_by_type):
            print(f"  type {typ:>2}: {dict(counts_by_type[typ])}")
        with open(os.path.join(OUT, "packs_index.json"), "w", encoding="utf-8") as o:
            json.dump(rows, o, indent=0)
        print(f"\nwrote {len(rows)} rows -> extract/packs/packs_index.json")
        print("total pack bytes:", sum(r["size"] for r in rows))


if __name__ == "__main__":
    main()
