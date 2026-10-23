"""Scan the whole pkg for long printable ASCII runs (resource names / metadata)."""
import collections
import os
import re
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864

RE_STR = re.compile(rb"[\x20-\x7e]{12,}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    seen = collections.Counter()
    first = {}
    with open(ISO, "rb") as f:
        f.seek(PKG_LBA * SEC)
        pos, left = 0, PKG_SIZE
        CH = 1 << 23
        carry = b""
        while left > 0:
            chunk = f.read(min(CH, left))
            if not chunk:
                break
            left -= len(chunk)
            buf = carry + chunk
            base = pos - len(carry)
            for m in RE_STR.finditer(buf):
                s = m.group()
                seen[s] += 1
                first.setdefault(s, base + m.start())
            carry = buf[-32:]
            pos += len(chunk)
    print(f"distinct ASCII runs>=12: {len(seen):,}  total occurrences: {sum(seen.values()):,}")
    print("top 30:")
    for s, n in seen.most_common(30):
        print(f"  {n:>5}  @0x{first[s]:08x}  {s[:70].decode('latin1')}")
    print("\nruns containing letters and underscores (likely identifiers):")
    k = 0
    for s, n in seen.most_common(4000):
        if b"_" in s and any(65 <= b <= 90 or 97 <= b <= 122 for b in s) and not set(s) <= set(b"UuDdWwFfEeTt\"'?."):
            print(f"  {n:>5}  @0x{first[s]:08x}  {s[:70].decode('latin1')}")
            k += 1
            if k >= 25:
                break


if __name__ == "__main__":
    main()
