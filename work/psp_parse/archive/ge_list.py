"""ge_list.py -- find PSP GE display-list commands inside a RAM image.

GE command word layout:  (opcode << 24) | (argument & 0xFFFFFF)
   0x01 = VADDR      vertex array address (low 24 bits of the guest pointer)
   0x02 = IADDR      index array address
   0x04 = PRIM       primitive + count
   0x12 = VTYPE      vertex format
   0x0F = BASE
   0x0B = END, 0x0C = SIGNAL, 0x0A = RET

So a VADDR for guest 0x0923_9FD4 shows up as the word 0x01239FD4, and the display list that
contains it also carries the VTYPE we need.
"""
import struct
import sys

VALID_VTYPES = {0x3002, 0x3000, 0x111E, 0x1111, 0x3012, 0x3A02, 0x2A02, 0x1202,
                0x3002 | 0x00, 0x1101, 0x1102, 0x3101, 0x3102}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blob = open(sys.argv[1], "rb").read()
    n = len(blob) // 4
    words = struct.unpack_from(f"<{n}I", blob, 0)
    print(f"{len(blob):,} bytes, {n:,} words")

    # 1) VADDR candidates: opcode 0x01, argument inside the PSP user RAM window
    addr_hits = []
    for i, w in enumerate(words):
        if (w >> 24) != 0x01:
            continue
        arg = w & 0xFFFFFF
        if 0x080000 <= arg <= 0x0A0000:      # could be anywhere in the 32 MiB image
            addr_hits.append(i)
    print(f"VADDR-like words: {len(addr_hits)}")

    # 2) VTYPE candidates
    vtype_hits = []
    for i, w in enumerate(words):
        if (w >> 24) == 0x12:
            vtype_hits.append(i)
    print(f"VTYPE-like words (0x12xxxxxx): {len(vtype_hits)}")

    # 3) show clusters: a VADDR within +-8 words of a VTYPE is a real draw
    print("\nVADDR next to VTYPE (probable draw setup):")
    shown = 0
    for i in addr_hits:
        for j in range(max(0, i - 8), min(n, i + 9)):
            if (words[j] >> 24) == 0x12:
                lo = max(0, min(i, j) - 4)
                seg = words[lo: lo + 14]
                print(f"  @file 0x{i * 4:08x} guest 0x{0x08000000 + i * 4:08x}  "
                      + " ".join(f"{x:08x}" for x in seg))
                shown += 1
                break
        if shown >= 12:
            break
    if shown == 0:
        print("  none")

    # 4) distribution of VTYPE arguments
    import collections
    args = collections.Counter(words[i] & 0xFFFFFF for i in vtype_hits)
    print("\ntop VTYPE arguments:")
    for a, c in args.most_common(10):
        print(f"  0x{a:06x} x{c}")


if __name__ == "__main__":
    main()
