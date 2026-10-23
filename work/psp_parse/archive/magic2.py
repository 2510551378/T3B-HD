"""Correct-magic scan: GIM ('MIG.00'), GMO ('OMG.00'), TIM2, FTEX and other PSP containers."""
import os
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864

SIGS = [
    (b"MIG.00", "GIM texture"),
    (b"OMG.00", "GMO model"),
    (b"OMG.01", "GMO v1"),
    (b"TIM2", "TIM2"),
    (b"FTEX", "FTEX"),
    (b"GTF\x00", "GTF"),
    (b"SEDB", "SEDB"),
    (b"pack", "pack"),
    (b"RIFF", "RIFF"),
    (b"PSMF", "PSMF"),
    (b"\x00\x00\x01\xba", "MPEG-PS pack"),
]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    counts = {tag: 0 for _, tag in SIGS}
    first = {tag: [] for _, tag in SIGS}
    with open(ISO, "rb") as f:
        f.seek(PKG_LBA * SEC)
        pos, left = 0, PKG_SIZE
        CH = 1 << 23
        carry = b""
        keep = max(len(s) for s, _ in SIGS) - 1
        while left > 0:
            chunk = f.read(min(CH, left))
            if not chunk:
                break
            left -= len(chunk)
            buf = carry + chunk
            base = pos - len(carry)
            for sig, tag in SIGS:
                i = 0
                while True:
                    i = buf.find(sig, i)
                    if i < 0:
                        break
                    counts[tag] += 1
                    if len(first[tag]) < 4:
                        first[tag].append(base + i)
                    i += 1
            carry = buf[-keep:]
            pos += len(chunk)
    for tag in counts:
        print(f"  {tag:14} count={counts[tag]:<6} first={[hex(x) for x in first[tag]]}")


if __name__ == "__main__":
    main()
