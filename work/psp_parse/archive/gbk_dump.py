"""Dump GBK-decoded context around Chinese text hits in the tail of 3rd.pkg."""
import os
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
START = 0x4C000000  # 1.216 GiB

PAT = "的".encode("gbk")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with open(ISO, "rb") as f:
        f.seek(PKG_LBA * SEC + START)
        buf = f.read(PKG_SIZE - START)
    print(f"region 0x{START:x}..end  {len(buf):,} bytes")
    hits = []
    i = 0
    while True:
        i = buf.find(PAT, i)
        if i < 0:
            break
        hits.append(i)
        i += 1
    print(f"GBK '的' occurrences: {len(hits)}")
    for h in hits[:6]:
        lo = max(0, h - 80)
        seg = buf[lo:h + 160]
        try:
            s = seg.decode("gbk", "replace")
        except Exception:
            s = ""
        print(f"\n--- hit @0x{START + h:08x} ---")
        print("   hex:", seg[:64].hex(" "))
        print("   gbk:", s.replace("\n", "\\n")[:200])


if __name__ == "__main__":
    main()
