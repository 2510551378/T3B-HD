"""Extract all SEDB files and score them for embedded text (ASCII / UTF-16LE CJK / GBK)."""
import os
import re
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
OUT = os.path.join(os.path.dirname(__file__), "extract", "sedb")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864

RE_ASCII = re.compile(rb"[\x20-\x7e]{8,}")
RE_UTF16_CJK = re.compile("[\u4e00-\u9fff]{4,}")


def find_sedb(f):
    f.seek(PKG_LBA * SEC)
    pos, left, hits = 0, PKG_SIZE, []
    CH = 1 << 23
    while left > 0:
        buf = f.read(min(CH, left))
        if not buf:
            break
        left -= len(buf)
        i = 0
        while True:
            i = buf.find(b"SEDBSSCF", i)
            if i < 0:
                break
            if (pos + i) % 0x800 == 0:
                hits.append(pos + i)
            i += 1
        pos += len(buf)
    return hits


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(OUT, exist_ok=True)
    rows = []
    with open(ISO, "rb") as f:
        hits = find_sedb(f)
        print(f"SEDB entries: {len(hits)}")
        for n, h in enumerate(hits):
            f.seek(PKG_LBA * SEC + h)
            head = f.read(0x20)
            size = int.from_bytes(head[16:20], "little")
            c = head[0x30:0x38] if False else None
            f.seek(PKG_LBA * SEC + h)
            blob = f.read(size)
            p = os.path.join(OUT, f"sedb_{n:03d}_0x{h:08x}.bin")
            if not os.path.exists(p):
                with open(p, "wb") as o:
                    o.write(blob)
            n_ascii = len(RE_ASCII.findall(blob))
            n_ascii_bytes = sum(len(m) for m in RE_ASCII.findall(blob))
            try:
                s16 = blob.decode("utf-16-le", "ignore")
                utf16 = RE_UTF16_CJK.findall(s16)
            except Exception:
                utf16 = []
            rows.append((n, h, size, n_ascii, n_ascii_bytes, len(utf16)))
        rows.sort(key=lambda r: -(r[4] + 40 * r[5]))
        print(f"\n{'idx':>3} {'offset':>12} {'size':>10} {'ascii_runs':>10} {'ascii_B':>9} {'utf16_cjk':>9}")
        for r in rows[:20]:
            print(f"{r[0]:>3} 0x{r[1]:08x} {r[2]:>10,} {r[3]:>10} {r[4]:>9,} {r[5]:>9}")
        print("\n... lowest:")
        for r in rows[-5:]:
            print(f"{r[0]:>3} 0x{r[1]:08x} {r[2]:>10,} {r[3]:>10} {r[4]:>9,} {r[5]:>9}")


if __name__ == "__main__":
    main()
