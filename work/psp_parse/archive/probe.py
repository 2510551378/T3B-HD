"""Deeper look: EBOOT.BIN encryption state, ICON0/PIC1 bytes, 3rd.fsd structure, 3rd.pkg scan."""
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048

LBA = {
    "SYSDIR/EBOOT.BIN": (544, 5660624),
    "SYSDIR/BOOT.BIN": (56576, 5660285),
    "SYSDIR/UPDATE/EBOOT.BIN": (3328, 5540576),
    "SYSDIR/UPDATE/DATA.BIN": (7424, 26120416),
    "ICON0.PNG": (59360, 5825),
    "PIC1.PNG": (59376, 51717),
    "3rd.fsd": (59584, 7932),
    "3rd.pkg": (59600, 1344292864),
}


def hexdump(data, limit=256, base=0):
    out = []
    for i in range(0, min(len(data), limit), 16):
        chunk = data[i:i + 16]
        hx = " ".join(f"{b:02x}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        out.append(f"  {base + i:08x}  {hx:<47}  |{asc}|")
    return "\n".join(out)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with open(ISO, "rb") as f:
        print("### header probes")
        for name in ("SYSDIR/EBOOT.BIN", "SYSDIR/BOOT.BIN", "SYSDIR/UPDATE/EBOOT.BIN",
                     "SYSDIR/UPDATE/DATA.BIN", "ICON0.PNG", "PIC1.PNG"):
            lba, size = LBA[name]
            f.seek(lba * SEC)
            d = f.read(64)
            print(f"  {name:26} size={size:>10,}  {d[:16].hex(' ')}")
            if d[:4] == b"\x7fELF":
                print("      -> plain ELF (not encrypted)")
            elif d[:4] == b"\x7ePSP":
                print("      -> ~PSP encrypted PRX")
            elif d[:4] == b"\x89PNG":
                print("      -> PNG")
            elif d[:4] == b"RIFF":
                print("      -> RIFF")
            else:
                print("      -> unknown")

        # 3rd.fsd: dump every byte as dwords, 16 per line
        lba, size = LBA["3rd.fsd"]
        f.seek(lba * SEC)
        fsd = f.read(size)
        print(f"\n### 3rd.fsd dwords (size {size})")
        for off in range(0, len(fsd), 64):
            chunk = fsd[off:off + 64]
            vals = [struct.unpack_from("<I", chunk, i)[0] for i in range(0, len(chunk), 4)]
            print(f"  {off:04x}: " + " ".join(f"{v:08x}" for v in vals))

        # scan 3rd.pkg for signatures
        lba, size = LBA["3rd.pkg"]
        f.seek(lba * SEC)
        sigs = {
            b"\x89PNG\r\n\x1a\n": "PNG",
            b"RIFF": "RIFF",
            b"GIM\x20\x00\x00\x00": "GIM?",   # placeholder
            b"OMG.00": "GMO",
            b"PSMF": "PSMF",
            b"PSAR": "PSAR",
        }
        print("\n### 3rd.pkg scan for signatures (chunked, up to 400 MB)")
        counts = {}
        found_at = {}
        left = min(size, 400 * 1024 * 1024)
        pos = 0
        CH = 1 << 22
        f.seek(lba * SEC)
        while left > 0:
            buf = f.read(min(CH, left))
            if not buf:
                break
            left -= len(buf)
            for sig, tag in sigs.items():
                start = 0
                while True:
                    i = buf.find(sig, start)
                    if i < 0:
                        break
                    counts[tag] = counts.get(tag, 0) + 1
                    if len(found_at.setdefault(tag, [])) < 6:
                        found_at[tag].append(pos + i)
                    start = i + 1
            pos += len(buf)
        for tag in sorted(counts):
            print(f"  {tag:6} count={counts[tag]:<6} first_at={[hex(x) for x in found_at[tag]][:6]}")


if __name__ == "__main__":
    main()
