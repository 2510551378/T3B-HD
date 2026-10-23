"""ppdmp_pages.py -- look for the page table inside a PPSSPP frame dump.

The dump embeds the guest memory pages the frame touched.  Each page is almost certainly
prefixed with its guest address (0x08xxxxxx), so a run of ascending addresses in that range
reveals the table: address -> file offset.
"""
import struct
import sys


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blob = open(sys.argv[1], "rb").read()
    n = len(blob) // 4
    w = struct.unpack_from(f"<{n}I", blob, 0)
    print(f"{len(blob):,} bytes, {n:,} words")

    # words that look like PSP user RAM addresses
    cand = [i for i, v in enumerate(w) if 0x08000000 <= v <= 0x0A000000]
    print(f"words in 0x08000000..0x0A000000: {len(cand)}")
    if not cand:
        return

    # find ascending runs of >=4 such words with a regular stride in *bytes*
    runs = []
    start = cand[0]
    prev = cand[0]
    for i in cand[1:]:
        if i - prev <= 3:
            prev = i
        else:
            if prev - start >= 3:
                runs.append((start, prev))
            start = i
            prev = i
    if prev - start >= 3:
        runs.append((start, prev))
    print(f"ascending runs: {len(runs)}")

    for a, b in runs[:8]:
        print(f"\n  table words [{a}..{b}]  file 0x{a * 4:08x}..0x{b * 4:08x}")
        for i in range(a, min(a + 10, b + 1)):
            print(f"    [{i:>7}] 0x{w[i]:08x}  (file 0x{i * 4:08x})")


if __name__ == "__main__":
    main()
