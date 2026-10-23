"""pkg_report.py -- one-pass tally of every self-describing entry in 3rd.pkg.

Entries are 0x800-aligned; each is self-describing, and the contiguity oracle
align_up(offset+size, 0x800) == next_offset confirms the walk.
"""
import collections
import os
import struct
import sys

ALIGN = 0x800

MAGIC = [
    (b"PSMF", "PSMF video"),
    (b"SEDBSSCF", "SEDBSSCF audio"),
    (b"RIFF", "RIFF/AT3"),
    (b"\x89PNG", "PNG"),
    (b"pack", "pack"),
]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    path = sys.argv[1]
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        # locate the pkg by scanning 0x800-aligned offsets for probable headers
        pos = 0
        tally = collections.Counter()
        bytes_by = collections.Counter()
        counted = 0
        guess = 0
        while pos + 8 <= size:
            f.seek(pos)
            head = f.read(16)
            kind = None
            for magic, name in MAGIC:
                if head.startswith(magic):
                    kind = name
                    break
            if kind == "pack":
                # pack header: "pack", u32 type, then (size, offset) pairs
                f.seek(pos + 8)
                first = struct.unpack("<I", f.read(4))[0]
            if kind is None:
                kind = "other/zero"
            # pack entries advertise their span through the pair table; fall back to next magic
            nxt = pos + ALIGN
            entry = head
            if kind == "pack":
                # read the pair table to get the true size
                f.seek(pos + 4)
                ptype = struct.unpack("<I", f.read(4))[0]
                f.seek(pos + 8)
                pairs = []
                total = 8
                while True:
                    s, o = struct.unpack("<II", f.read(8))
                    if s == 0 and o == 0:
                        break
                    pairs.append((s, o))
                    total = max(total, o + s)
                kind = f"pack type {ptype}"
                span = (total + ALIGN - 1) // ALIGN * ALIGN
            else:
                span = None
            if span is None:
                # for non-pack entries, walk forward until the next 0x800-aligned magic
                q = pos + ALIGN
                while q + 8 <= size:
                    f.seek(q)
                    h2 = f.read(8)
                    if any(h2.startswith(m) for m, _ in MAGIC) or h2 == b"\x00" * 8:
                        break
                    q += ALIGN
                span = q - pos
            tally[kind] += 1
            bytes_by[kind] += span
            counted += span
            pos += span
        print(f"{path}: {size:,} bytes")
        print(f"walked {counted:,} bytes")
        print(f"{'kind':<20}{'count':>7}{'bytes':>16}{'MB':>10}")
        for k, n in tally.most_common():
            print(f"{k:<20}{n:>7}{bytes_by[k]:>16,}{bytes_by[k]/1048576:>10.1f}")


if __name__ == "__main__":
    main()
