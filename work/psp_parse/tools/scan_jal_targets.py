from __future__ import annotations

import argparse
import struct
from pathlib import Path


BASE = 0x08804000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("module", type=Path)
    ap.add_argument("targets", nargs="+", type=lambda value: int(value, 0))
    args = ap.parse_args()
    blob = args.module.read_bytes()
    found = {target: [] for target in args.targets}
    for off in range(0, len(blob) - 4, 4):
        word = struct.unpack_from("<I", blob, off)[0]
        if word >> 26 != 3:
            continue
        pc = BASE + off
        target = ((word & 0x03FFFFFF) << 2) | ((pc + 4) & 0xF0000000)
        if target in found:
            found[target].append(pc)
    for target, sites in found.items():
        print(f"{target:#x} count={len(sites)} sites=" + ",".join(f"{x:#x}" for x in sites))


if __name__ == "__main__":
    main()
