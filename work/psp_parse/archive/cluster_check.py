"""Step 33: characters may be split into several runs -- look for clusters of small runs
that together form a human-sized volume."""
import collections
import csv
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
INDEX = os.path.join(os.path.dirname(__file__), "runs", "runs_index.csv")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = list(csv.DictReader(open(INDEX, encoding="utf-8")))
    print(f"{len(rows)} runs")
    by_pack = collections.defaultdict(list)
    for r in rows:
        by_pack[r["pack"]].append(r)
    print(f"{len(by_pack)} packs")
    # bbox-size histogram
    small = [r for r in rows if float(r["dy"]) < 1.2 and float(r["dx"]) < 1.2 and float(r["dz"]) < 1.2
             and int(r["verts"]) >= 30]
    print(f"runs smaller than 1.2 m in every axis: {len(small)}")
    sizes = collections.Counter()
    for r in rows:
        dy = float(r["dy"])
        sizes[round(dy)] += 1
    print("dy histogram:", dict(sorted(sizes.items())[:10]))
    # per-pack: how many runs per pack
    cnt = collections.Counter(r["pack"] for r in rows)
    print("runs per pack (top):", cnt.most_common(5))
    print("runs per pack (min):", cnt.most_common()[-5:])


if __name__ == "__main__":
    main()
