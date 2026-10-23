"""Extract the 11-channel Aya hierarchy from the multi-pose GE capture."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from extract_aya_hierarchy_timeline import CHANNELS, extract


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("capture_dir", type=Path)
    ap.add_argument("out_json", type=Path)
    ap.add_argument("out_csv", type=Path)
    args = ap.parse_args()
    manifest = json.loads((args.capture_dir / "manifest.json").read_text(encoding="utf-8"))
    frames = []
    for item in manifest["frames"]:
        ch = extract(args.capture_dir / item["file"])
        frames.append({"pose": item["pose"], "frame": item["frame"], "source": item["file"], "channels": ch})
        print(f"{item['pose']} frame {item['frame']:02d}: " + ", ".join(f"{k}@{v['draw']}" for k, v in ch.items()))
    result = {
        "schema": "aya-ge-pose-variants/v1",
        "channels": list(CHANNELS),
        "source": "PPSSPP WebSocket gpu.record.dump; weighted draw hierarchy mapping",
        "frames": frames,
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    with args.out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["pose", "frame", "channel"] + [f"m{i}{j}" for i in range(3) for j in range(4)])
        for item in frames:
            for channel in CHANNELS:
                if channel in item["channels"]:
                    writer.writerow([item["pose"], item["frame"], channel] + [f"{x:.9f}" for x in item["channels"][channel]["matrix"]])
    print(f"wrote {args.out_json} and {args.out_csv}")


if __name__ == "__main__":
    main()
