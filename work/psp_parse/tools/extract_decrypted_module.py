from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract a decrypted PSP module from a PPSSPP RAM dump")
    parser.add_argument("ram", type=Path)
    parser.add_argument("output", type=Path)
    # PPSSPP RAM image has a 0x48-byte loader/header prefix before the map's
    # 0x08804000 module base.  Removing it aligns guest symbols with live
    # memory.disasm (for example dl_write_matrix at 0x08c01088).
    parser.add_argument("--offset", type=lambda value: int(value, 0), default=0x804048)
    parser.add_argument("--size", type=lambda value: int(value, 0), default=0x4AF000)
    args = parser.parse_args()

    data = args.ram.read_bytes()
    end = args.offset + args.size
    if args.offset < 0 or end > len(data):
        raise SystemExit(f"slice 0x{args.offset:x}..0x{end:x} exceeds RAM dump size 0x{len(data):x}")
    payload = data[args.offset:end]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(f"input={args.ram}")
    print(f"output={args.output}")
    print(f"offset=0x{args.offset:x} size=0x{args.size:x} bytes={len(payload)}")
    print(f"head={payload[:32].hex()}")


if __name__ == "__main__":
    main()
