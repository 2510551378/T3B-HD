"""Pull SEDB entries out of 3rd.pkg and probe their internal layout / text encoding."""
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
OUT = os.path.join(os.path.dirname(__file__), "extract", "sedb")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864


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


def hexdump(d, base=0, limit=256):
    for i in range(0, min(len(d), limit), 16):
        c = d[i:i + 16]
        hx = " ".join(f"{b:02x}" for b in c)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in c)
        print(f"  {base + i:08x}  {hx:<47}  |{asc}|")


def classify_text(d):
    n_utf8 = n_gbk = n_ascii = 0
    i = 0
    while i < len(d):
        b = d[i]
        if 0xE4 <= b <= 0xE9 and i + 2 < len(d) and 0x80 <= d[i + 1] <= 0xBF and 0x80 <= d[i + 2] <= 0xBF:
            n_utf8 += 1
            i += 3
            continue
        if 0x81 <= b <= 0xFE and i + 1 < len(d) and (0x40 <= d[i + 1] <= 0xFE and d[i + 1] != 0x7F):
            n_gbk += 1
            i += 2
            continue
        if 32 <= b < 127:
            n_ascii += 1
        i += 1
    return n_utf8, n_gbk, n_ascii


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(OUT, exist_ok=True)
    with open(ISO, "rb") as f:
        hits = find_sedb(f)
        print(f"SEDB entries (0x800 aligned): {len(hits)}")
        print("first offsets:", [hex(h) for h in hits[:8]])
        for n, h in enumerate(hits[:3]):
            f.seek(PKG_LBA * SEC + h)
            head = f.read(0x20)
            ver = struct.unpack_from("<I", head, 8)[0]
            f4 = struct.unpack_from("<I", head, 12)[0]
            size = struct.unpack_from("<I", head, 16)[0]
            f.seek(PKG_LBA * SEC + h)
            blob = f.read(size)
            p = os.path.join(OUT, f"sedb_{n:03d}_0x{h:08x}.bin")
            with open(p, "wb") as o:
                o.write(blob)
            u8, gb, asc = classify_text(blob)
            print(f"\n[sedb {n}] off=0x{h:08x} ver={ver} f4={f4:#x} size={size:,}")
            print(f"  text guess: utf8_cjk={u8}  gbk={gb}  ascii={asc}")
            hexdump(blob, 0, 256)

        # padding check after first entry
        h, size = hits[0], None
        f.seek(PKG_LBA * SEC + h)
        size = struct.unpack_from("<I", f.read(0x14), 16)[0]
        f.seek(PKG_LBA * SEC + h + size)
        pad = f.read(min(0x800, hits[1] - (h + size)))
        print(f"\npadding after entry 0: {len(pad)} bytes, all zero = {not any(pad)}")

        # look for UTF-8 CJK runs in the first entry
        f.seek(PKG_LBA * SEC + h)
        blob = f.read(size)
        print("\nsample UTF-8 CJK runs (>=3 chars):")
        runs, cur, i = [], [], 0
        while i < len(blob):
            b = blob[i]
            if 0xE4 <= b <= 0xE9 and i + 2 < len(blob):
                ch = blob[i:i + 3]
                if 0x80 <= ch[1] <= 0xBF and 0x80 <= ch[2] <= 0xBF:
                    cur.append(ch)
                    i += 3
                    continue
            if cur:
                runs.append(b"".join(cur))
                cur = []
            i += 1
        if cur:
            runs.append(b"".join(cur))
        for r in runs[:10]:
            try:
                print("   ", r.decode("utf-8"))
            except Exception:
                print("   ", r.hex())
        print(f"  ({len(runs)} runs)")


if __name__ == "__main__":
    main()
