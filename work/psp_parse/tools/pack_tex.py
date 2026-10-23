"""pack_tex.py -- extract the palette-indexed textures stored inside type-8 'pack' containers.

Texture table lives at blob+0x20 (blob = biggest section of the pack).
Each entry is 16 bytes:

    +0x00  u16 width, u16 height
    +0x04  u32 bpp (4 or 8)
    +0x08  u32 CLUT offset  (16 colours x RGBA for 4bpp, 256 for 8bpp)
    +0x0C  u32 pixel offset (w*h*bpp/8 bytes, PSP swizzled)

usage:
    python pack_tex.py <pack_offset> <out_dir>
"""
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864


def unswizzle4(src, w, h):
    out = bytearray(w * h // 2)
    bw, bh = 32, 8
    brow = bw // 2
    nbx = w // bw
    for by in range(0, h, bh):
        for bx in range(0, w, bw):
            base = ((by // bh) * nbx + (bx // bw)) * (brow * bh)
            for y in range(bh):
                o = ((by + y) * w + bx) // 2
                out[o:o + brow] = src[base + y * brow:base + y * brow + brow]
    return bytes(out)


def unswizzle8(src, w, h):
    out = bytearray(w * h)
    bw, bh = 16, 8
    nbx = w // bw
    for by in range(0, h, bh):
        for bx in range(0, w, bw):
            base = ((by // bh) * nbx + (bx // bw)) * (bw * bh)
            for y in range(bh):
                o = (by + y) * w + bx
                out[o:o + bw] = src[base + y * bw:base + y * bw + bw]
    return bytes(out)


def unpack4(packed, n):
    out = bytearray(n)
    for i in range(n):
        b = packed[i >> 1]
        out[i] = (b & 0x0F) if (i & 1) == 0 else (b >> 4)
    return bytes(out)


def roughness(pix, w, h):
    s = 0
    cnt = 0
    for y in range(0, h, 2):
        row = y * w
        for x in range(0, w - 1, 2):
            s += abs(pix[row + x] - pix[row + x + 1])
            cnt += 1
    return s / max(1, cnt)


def build_rgba(idx, n, clut):
    px = bytearray(n * 4)
    for i in range(n):
        v = idx[i]
        px[i * 4:i * 4 + 4] = clut[v * 4:v * 4 + 4]
    return bytes(px)


def extract_pack(blob, outdir, tag):
    from PIL import Image
    # only vertex-pool sections carry a texture table we understand
    if struct.unpack_from("<I", blob, 4)[0] != 0x3002:
        return 0
    tbl = struct.unpack_from("<I", blob, 0x20)[0]
    n = 0
    while tbl + 16 * (n + 1) <= len(blob):
        o = tbl + n * 16
        w, h, code, coff, poff = struct.unpack_from("<HHIII", blob, o)
        if w == 0 or h == 0 or w > 1024 or h > 1024 or code not in (4, 8):
            break
        if coff + 64 > len(blob) or poff + w * h * code // 8 > len(blob):
            break
        ncl = 16 if code == 4 else 256
        clut = blob[coff:coff + ncl * 4]
        psize = w * h * code // 8
        raw = blob[poff:poff + psize]
        if code == 4:
            lin = unpack4(raw, w * h)
            sw = unpack4(unswizzle4(raw, w, h), w * h)
        else:
            lin, sw = raw, unswizzle8(raw, w, h)
        rl, rs = roughness(lin, w, h), roughness(sw, w, h)
        use_sw = rs <= rl
        idx = sw if use_sw else lin
        rgba = build_rgba(idx, w * h, clut)
        img = Image.frombytes("RGBA", (w, h), rgba)
        fn = os.path.join(outdir, f"{tag}_tex{n:02d}_{w}x{h}.png")
        img.save(fn)
        n += 1
    return n


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from psp_pack import parse_pack, iter_pack_offsets, open_pack
    global Image
    from PIL import Image

    target = argv[1]
    outdir = argv[2]
    os.makedirs(outdir, exist_ok=True)
    total = packs = 0
    with open(ISO, "rb") as f:
        offs = iter_pack_offsets(f)
        spans = {o: (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - o for i, o in enumerate(offs)}
        sel = offs if target == "all" else [int(target, 0)]
        for off in sel:
            buf = open_pack(f, off, spans[off])
            p = parse_pack(buf, off, spans[off])
            if not p.sections:
                continue
            big = max(p.sections, key=lambda s: s[0])
            blob = buf[big[1]:big[1] + big[0]]
            tag = f"p{off:08x}"
            n = extract_pack(blob, outdir, tag)
            if n:
                packs += 1
                total += n
                print(f"  pack 0x{off:08x} type={p.type}: {n} textures", flush=True)
    print(f"\n{packs} packs, {total} textures -> {outdir}")


if __name__ == "__main__":
    main(sys.argv)
