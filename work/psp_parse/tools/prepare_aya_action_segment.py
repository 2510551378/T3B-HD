"""Select an explicitly reviewed original interval, preserving capture identity."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--first", type=int, required=True)
    ap.add_argument("--last", type=int, required=True)
    ap.add_argument("--reason", required=True)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    data = a.manifest.read_bytes()
    manifest = json.loads(data)
    if not 0 <= a.first < a.last < len(manifest["frames"]):
        raise ValueError("select at least two original samples within capture")
    frames = manifest["frames"][a.first:a.last + 1]
    manifest["segment_selection"] = {"source_manifest": str(a.manifest.resolve()),
                                     "source_sha256": hashlib.sha256(data).hexdigest(),
                                     "first_sample": a.first, "last_sample": a.last,
                                     "source_frame_ids": [frame["frame"] for frame in frames],
                                     "reason": a.reason,
                                     "limitation": "Reviewed pose interval, not proof of an entire original animation clip or a loop."}
    # Original raw-frame IDs and ticks are retained; exporters rebase time only.
    manifest["frames"] = frames
    a.out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest["segment_selection"]))


if __name__ == "__main__":
    main()
