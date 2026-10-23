"""Extract the small ISO members and dump the 3rd.pkg / 3rd.fsd headers."""
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
OUT = os.path.join(os.path.dirname(__file__), "extract")
SEC = 2048

MEMBERS = {
    "PARAM.SFO": (59344, 560),
    "3rd.fsd": (59584, 7932),
    "3rd.pkg": (59600, 1344292864),
    "ICON0.PNG": (59360, 5825),
    "PIC1.PNG": (59376, 51717),
    "SND0.AT3": (59440, 265104),
    "UMD_DATA.BIN": (27, 48),
}


def read_member(f, lba, size, head=None):
    f.seek(lba * SEC)
    if head:
        return f.read(min(size, head))
    return f.read(size)


def hexdump(data, limit=1024, base=0):
    out = []
    for i in range(0, min(len(data), limit), 16):
        chunk = data[i:i + 16]
        hx = " ".join(f"{b:02x}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        out.append(f"  {base + i:08x}  {hx:<47}  |{asc}|")
    return "\n".join(out)


def entropy(data):
    import collections
    import math
    if not data:
        return 0.0
    c = collections.Counter(data)
    n = len(data)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def sfo(data):
    if data[:4] != b"\x00PSF":
        return None
    ver, key_start, val_start, count = struct.unpack_from("<IIII", data, 4)
    out = []
    for i in range(count):
        ko, fmt, ln, mx, do = struct.unpack_from("<HHIII", data, 20 + i * 16)
        key = data[key_start + ko:].split(b"\0", 1)[0].decode("utf-8", "replace")
        raw = data[val_start + do: val_start + do + ln]
        val = struct.unpack("<I", raw)[0] if fmt == 0x0404 else raw.split(b"\0", 1)[0].decode("utf-8", "replace")
        out.append((key, val))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(OUT, exist_ok=True)
    with open(ISO, "rb") as f:
        for name, (lba, size) in MEMBERS.items():
            data = read_member(f, lba, size, head=None if size < 40_000_000 else 1 << 20)
            print("=" * 78)
            print(f"{name}  LBA {lba}  size={size:,}  read={len(data):,}  entropy={entropy(data[:65536]):.2f}")
            print("=" * 78)
            if name == "PARAM.SFO":
                for k, v in sfo(data):
                    print(f"  {k:24} = {v!r}")
            elif name.endswith(".PNG"):
                print(f"  PNG signature ok={data[:8] == b'\\x89PNG\\r\\n\\x1a\\n'}")
            elif name.endswith(".AT3"):
                print(f"  RIFF={data[0:4]!r} type={data[8:12]!r} wave_fmt={data[20:22].hex()}")
            else:
                print(hexdump(data, 512))
            if name in ("PARAM.SFO", "3rd.fsd", "3rd.pkg"):
                path = os.path.join(OUT, name)
                if name == "3rd.pkg":
                    with open(path, "wb") as o:
                        f.seek(lba * SEC)
                        left = 1 << 20
                        while left > 0:
                            b = f.read(min(1 << 16, left))
                            if not b:
                                break
                            o.write(b)
                            left -= len(b)
                else:
                    with open(path, "wb") as o:
                        o.write(data)
                print(f"  -> extracted {os.path.relpath(path, ROOT)} ({os.path.getsize(path):,} bytes)")
            print()


if __name__ == "__main__":
    main()
