"""Focused probes: pkg entropy map + signature scan, first-PNG walk, own EBOOT DATA.PSP header, fsd strings."""
import math
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
PBP_PROJ = os.path.join(ROOT, r"work\psp_game\EBOOT.PBP")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
FSD_LBA, FSD_SIZE = 59584, 7932


def entropy(b):
    if not b:
        return 0.0
    c = [0] * 256
    for x in b:
        c[x] += 1
    n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c if v)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with open(ISO, "rb") as f:
        # 1) entropy map of pkg: 64 samples of 64 KiB spread over the file
        print("### 3rd.pkg entropy map (64 KiB samples)")
        row = []
        for k in range(64):
            off = k * (PKG_SIZE // 64)
            f.seek(PKG_LBA * SEC + off)
            d = f.read(65536)
            row.append(f"{off:>10}:{entropy(d):.2f}")
            if len(row) == 8:
                print("   " + "  ".join(row))
                row = []
        # 2) signature scan over whole pkg
        print("\n### 3rd.pkg signature scan (whole file)")
        sigs = {
            b"\x89PNG\r\n\x1a\n": "PNG",
            b"OMG.00": "GMO",
            b"GIM\x00": "GIM?",
            b"PSMF": "PSMF",
            b"RIFF": "RIFF",
            b"SEDB": "SEDB",
            b"pack": "pack",
        }
        f.seek(PKG_LBA * SEC)
        counts = {k: 0 for k in sigs}
        first = {k: [] for k in sigs}
        pos = 0
        left = PKG_SIZE
        CH = 1 << 23
        while left > 0:
            buf = f.read(min(CH, left))
            if not buf:
                break
            left -= len(buf)
            for sig in sigs:
                i = 0
                while True:
                    i = buf.find(sig, i)
                    if i < 0:
                        break
                    counts[sig] += 1
                    if len(first[sig]) < 5:
                        first[sig].append(pos + i)
                    i += 1
            pos += len(buf)
        for sig in sigs:
            print(f"  {sigs[sig]:6} {sig!r:22} count={counts[sig]:<6} first={[hex(x) for x in first[sig]]}")

        # 3) walk the leading PNG(s) at pkg offset 0
        print("\n### leading PNG walk from pkg offset 0")
        off = 0
        for _ in range(6):
            f.seek(PKG_LBA * SEC + off)
            d = f.read(33)
            if d[:8] != b"\x89PNG\r\n\x1a\n":
                print(f"  off {off:#x}: not PNG -> {d[:8].hex(' ')}")
                break
            w, h = struct.unpack_from(">II", d, 16)
            # walk chunks to IEND
            f.seek(PKG_LBA * SEC + off)
            p = 8
            while True:
                f.seek(PKG_LBA * SEC + off + p)
                hdr = f.read(8)
                if len(hdr) < 8:
                    p = None
                    break
                ln, typ = struct.unpack(">I4s", hdr)
                p += 12 + ln
                if typ == b"IEND":
                    break
            print(f"  off {off:#010x}: PNG {w}x{h}  size={p}  end={off + p:#010x}")
            off += p

        # 4) fsd printable strings
        f.seek(FSD_LBA * SEC)
        fsd = f.read(FSD_SIZE)
        print("\n### 3rd.fsd printable runs (>=4)")
        i = 0
        n = 0
        while i < len(fsd):
            if 32 <= fsd[i] < 127:
                j = i
                while j < len(fsd) and 32 <= fsd[j] < 127:
                    j += 1
                if j - i >= 4:
                    print(f"  {i:#06x}  {fsd[i:j].decode('ascii')}")
                    n += 1
                i = j
            else:
                i += 1
        print(f"  ({n} runs)")

    # 5) own EBOOT DATA.PSP
    print("\n### work/psp_game/EBOOT.PBP -> DATA.PSP header")
    with open(PBP_PROJ, "rb") as f:
        head = f.read(40)
        offs = struct.unpack_from("<8I", head, 8)
        f.seek(offs[6])
        d = f.read(0x200)
    print(f"  {d[:16].hex(' ')}")
    if d[:4] == b"\x7fELF":
        e_type = struct.unpack_from("<H", d, 16)[0]
        e_machine = struct.unpack_from("<H", d, 18)[0]
        e_entry = struct.unpack_from("<I", d, 24)[0]
        print(f"  ELF e_type={e_type} (0xFFA0=PRX) e_machine={e_machine} entry={e_entry:#x}")
        if e_type == 0xFFA0:
            # PRX module info: at 0xD0+? use psp structure: e_shoff? Standard: PRX header at 0xD0
            mod_attr = struct.unpack_from("<H", d, 0xD4)[0] if len(d) > 0xD8 else 0
            print(f"  PRX module_attribute={mod_attr:#x} name_ptr={struct.unpack_from('<I', d, 0xD0)[0]:#x}")
    print(f"  len={len(d)}  first bytes as u32: {struct.unpack_from('<4I', d, 0)}")


if __name__ == "__main__":
    main()
