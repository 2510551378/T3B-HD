"""psp_pack.py -- reader for the 'pack' containers of The 3rd Birthday (ULJM-05798).

Header model (verified against 435/436 containers):

    +0x00  char[4]  "pack"
    +0x04  u32      type / version   (2, 4, 7, 8, 11, 12, 34 observed)
    +0x08  N x (u32 size, u32 offset)
            N = (offset_of_first_section - 8) // 8
            first offset == header size (header may be padded by up to 4 bytes)
            sections tile forward: offset[i+1] ~= offset[i] + size[i]  (gap <= 0x100)
    zero pairs are empty slots.

Usage:
    python psp_pack.py list                # inventory of all packs
    python psp_pack.py show 0x444e5000     # header + sections of one pack
    python psp_pack.py dump 0x444e5000 DIR # extract its sections
"""
import os
import struct
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
MAGIC = b"pack"


def align(v, a=0x800):
    return (v + a - 1) // a * a


class Pack:
    __slots__ = ("offset", "type", "count", "hdr_size", "sections", "span")

    def __init__(self, offset, type_, count, hdr_size, sections, span):
        self.offset = offset
        self.type = type_
        self.count = count
        self.hdr_size = hdr_size
        self.sections = sections          # list of (size, offset) with size>0
        self.span = span

    def __repr__(self):
        return (f"<Pack 0x{self.offset:08x} type={self.type} hdr=0x{self.hdr_size:x} "
                f"sections={len(self.sections)} span={self.span:,}>")


def parse_pack(buf, offset=0, span=None):
    """Parse a pack header from a bytes buffer holding the whole container."""
    if buf[:4] != MAGIC:
        raise ValueError("not a pack container")
    type_ = struct.unpack_from("<I", buf, 4)[0]
    first_size, first_off = struct.unpack_from("<II", buf, 8)
    hdr_size = first_off
    count = (hdr_size - 8) // 8
    sections = []
    for i in range(count):
        sz, off = struct.unpack_from("<II", buf, 8 + i * 8)
        if sz == 0 or off == 0:
            continue
        sections.append((sz, off))
    if span is None:
        end = max(off + sz for sz, off in sections) if sections else hdr_size
        span = align(end)
    else:
        # keep the container honest: never claim past the last section
        end = max(off + sz for sz, off in sections) if sections else hdr_size
        span = min(span, align(end))
    return Pack(offset, type_, count, hdr_size, sections, span)


def iter_pack_offsets(f):
    f.seek(PKG_LBA * SEC)
    pos, left = 0, PKG_SIZE
    CH = 1 << 23
    hits = []
    carry = b""
    keep = 3
    while left > 0:
        chunk = f.read(min(CH, left))
        if not chunk:
            break
        left -= len(chunk)
        buf = carry + chunk
        base = pos - len(carry)
        i = 0
        while True:
            i = buf.find(MAGIC, i)
            if i < 0:
                break
            if (base + i) % 0x800 == 0:
                hits.append(base + i)
            i += 1
        carry = buf[-keep:]
        pos += len(chunk)
    return hits


def open_pack(f, offset, span):
    f.seek(PKG_LBA * SEC + offset)
    return f.read(span)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmd = argv[1] if len(argv) > 1 else "list"
    with open(ISO, "rb") as f:
        offs = iter_pack_offsets(f)
        spans = {o: (offs[i + 1] if i + 1 < len(offs) else PKG_SIZE) - o for i, o in enumerate(offs)}
        if cmd == "list":
            total = 0
            for o in offs:
                p = parse_pack(open_pack(f, o, spans[o]), o, spans[o])
                total += p.span
                print(f"  {p!r} sections={[hex(s) for s, _ in p.sections][:8]}")
            print(f"packs={len(offs)} bytes={total:,}")
        elif cmd in ("show", "dump"):
            o = int(argv[2], 0)
            p = parse_pack(open_pack(f, o, spans[o]), o, spans[o])
            print(p)
            for i, (sz, off) in enumerate(p.sections):
                f.seek(PKG_LBA * SEC + o + off)
                head = f.read(min(32, sz))
                print(f"  [{i:>2}] off=0x{off:06x} size={sz:>9,} head={head.hex(' ')}")
            if cmd == "dump":
                outdir = argv[3] if len(argv) > 3 else "."
                os.makedirs(outdir, exist_ok=True)
                for i, (sz, off) in enumerate(p.sections):
                    f.seek(PKG_LBA * SEC + o + off)
                    data = f.read(sz)
                    fn = os.path.join(outdir, f"0x{o:08x}_s{i:02d}_0x{off:06x}.bin")
                    with open(fn, "wb") as out:
                        out.write(data)
                print(f"  dumped {len(p.sections)} sections to {outdir}")
        else:
            print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
