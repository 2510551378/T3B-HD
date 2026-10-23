"""ppdmp_table.py -- hunt for a page table inside a PPSSPP frame dump.

If the dump carries guest pages it needs a table mapping guest address -> file offset, so we
look for long ascending runs of page-aligned 32-bit values inside the PSP address range.
"""
import struct
import sys

PSP_LO, PSP_HI = 0x08000000, 0x0C000000


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blob = open(sys.argv[1], "rb").read()
    n = len(blob) // 4
    w = struct.unpack_from(f"<{n}I", blob, 0)
    print(f"{len(blob):,} bytes, {n:,} words")

    for gran in (256, 4096, 65536):
        ok = [i for i, v in enumerate(w)
              if PSP_LO <= v < PSP_HI and v % gran == 0]
        if not ok:
            print(f"gran {gran}: none")
            continue
        runs = []
        s = p = ok[0]
        for i in ok[1:]:
            if i - p <= 2 and w[i] > w[p]:
                p = i
            else:
                if p - s >= 6:
                    runs.append((s, p))
                s = p = i
        if p - s >= 6:
            runs.append((s, p))
        runs.sort(key=lambda r: r[1] - r[0], reverse=True)
        print(f"gran {gran}: {len(ok)} aligned words, {len(runs)} ascending runs, "
              f"longest {runs[0][1] - runs[0][0] + 1 if runs else 0}")
        for a, b in runs[:3]:
            print(f"   words {a}..{b}  file 0x{a * 4:08x}  "
                  f"first=0x{w[a]:08x} last=0x{w[b]:08x}")
            for i in range(a, min(a + 6, b + 1)):
                print(f"      [{i}] 0x{w[i]:08x}")


if __name__ == "__main__":
    main()
