"""Look at SEDB internals: ASCII identifiers and the record area."""
import glob
import os
import re
import sys

SEQ = os.path.join(os.path.dirname(__file__), "extract", "sedb")
RE_ASCII = re.compile(rb"[\x20-\x7e]{6,}")


def load(n):
    p = glob.glob(os.path.join(SEQ, f"sedb_{n:03d}_*.bin"))[0]
    with open(p, "rb") as f:
        return os.path.basename(p), f.read()


def hexdump(d, base, limit):
    for i in range(0, min(len(d), limit), 16):
        c = d[i:i + 16]
        hx = " ".join(f"{b:02x}" for b in c)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in c)
        print(f"  {base + i:08x}  {hx:<47}  |{asc}|")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for n in (0, 1, 28):
        name, blob = load(n)
        print(f"===== {name}  {len(blob):,} bytes")
        strs = RE_ASCII.findall(blob)
        print(f"  ASCII strings>=6: {len(strs)}")
        for s in strs[:25]:
            print("    ", s.decode("latin1"))
        print("  first data at 0xc0:")
        hexdump(blob[0xC0:], 0xC0, 0xC0)
        print("  at 0x150:")
        hexdump(blob[0x150:], 0x150, 0x60)
        print()


if __name__ == "__main__":
    main()
