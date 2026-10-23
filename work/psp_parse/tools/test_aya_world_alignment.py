"""Exercise rejection of false GE/source alignments on the real pilot capture."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parents[1]
    capture = root / "out/AYA_BONE_GE_ACTIONS/slot0_fire_world_paired5"
    original = json.loads((capture / "manifest_runtime.json").read_text(encoding="utf-8"))
    cases = [("valid", copy.deepcopy(original), True)]
    bad = copy.deepcopy(original)
    bad["frames"][1]["worldSource"]["weaponPayload"][0] ^= 1
    cases.append(("wrong_weapon_world", bad, False))
    bad = copy.deepcopy(original)
    bad["frames"][1]["records"][1]["matrix"][0] ^= 1
    cases.append(("wrong_active_bone", bad, False))
    bad = copy.deepcopy(original)
    bad["frames"].append(copy.deepcopy(bad["frames"][1]))
    cases.append(("ambiguous_duplicate", bad, False))
    for label, manifest, expected in cases:
        with tempfile.NamedTemporaryFile(prefix="alignment_check_", suffix=".json", dir=capture, delete=False) as f:
            input_path = Path(f.name)
        output_path = input_path.with_suffix(".aligned.json")
        try:
            input_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = subprocess.run([sys.executable, "-X", "utf8", str(root/"tools/align_aya_world_capture.py"),
                                     "--manifest", str(input_path), "--metadata", str(root/"out/AYA_SLOT0_SKELETON_METADATA.json"),
                                     "--out", str(output_path)], capture_output=True, text=True, encoding="utf-8")
            if (result.returncode == 0) != expected:
                raise AssertionError(f"{label}: unexpected outcome\n{result.stdout}\n{result.stderr}")
        finally:
            input_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)
    print(f"world_alignment_checks={len(cases)} failures=0")


if __name__ == "__main__":
    main()
