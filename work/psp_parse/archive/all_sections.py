"""Step 25: scan EVERY section of EVERY pack for 20-byte vertex records (not just the biggest)."""
import os
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
sys.path.insert(0, os.path.dirname(__file__))
from psp_pack import parse_pack, iter_pack_offsets, open_pack  # noqa: E402
from pack_export import find_runs  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = []
    with open(ISO, "rb") as f:
        offs = iter_pack_offsets(f)
        spans = {o: (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - o for i, o in enumerate(offs)}
        for o in offs:
            buf = open_pack(f, o, spans[o])
            p = parse_pack(buf, o, spans[o])
            for si, (sz, so) in enumerate(p.sections):
                if sz < 4096:
                    continue
                blob = buf[so:so + sz]
                runs = [r for r in find_runs(blob) if len(r) >= 30]
                nv = sum(len(r) for r in runs)
                if nv >= 100:
                    rows.append((nv, o, p.type, si, sz, len(runs)))
    rows.sort(reverse=True)
    print(f"{'pack':>12} {'type':>4} {'sec':>3} {'sec_size':>10} {'verts':>8} {'runs':>5}")
    for nv, o, t, si, sz, nr in rows[:25]:
        print(f"0x{o:08x} {t:>4} {si:>3} {sz:>10,} {nv:>8} {nr:>5}")
    print(f"\n{len(rows)} geometry sections in {len(set(r[1] for r in rows))} packs; "
          f"{sum(r[0] for r in rows):,} verts total")
    packs = {}
    for nv, o, t, si, sz, nr in rows:
        packs.setdefault(o, []).append(si)
    multi = {k: v for k, v in packs.items() if len(v) > 1}
    print(f"packs with more than one geometry section: {len(multi)}")
    for k, v in list(multi.items())[:10]:
        print(f"  0x{k:08x}: sections {v}")


if __name__ == "__main__":
    main()
