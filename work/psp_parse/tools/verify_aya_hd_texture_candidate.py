from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[3]
ORIGINAL = ROOT / "work/psp_parse/out/AYA_EXACT_MATERIALS/aya_506dc44780fe0539.png"
CANDIDATE = ROOT / "work/t3b_unreal/Content/SourceData/textures/aya_506dc44780fe0539_hd_candidate.png"
UVSAFE = ROOT / "work/t3b_unreal/Content/SourceData/textures/aya_506dc44780fe0539_hd_uvsafe_candidate.png"
CONSERVATIVE = ROOT / "work/t3b_unreal/Content/SourceData/textures/aya_506dc44780fe0539_hd_conservative_candidate.png"
OUT = ROOT / "work/t3b_unreal/Validation/aya_hd_texture_candidate_v1.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mask(image: Image.Image, threshold: int = 16) -> list[bool]:
    rgb = image.convert("RGB")
    return [max(pixel) > threshold for pixel in rgb.getdata()]


def main() -> None:
    original = Image.open(ORIGINAL).convert("RGBA")
    candidate = Image.open(CANDIDATE).convert("RGBA")
    # The source atlas is 256x256. Downsample only for layout auditing; the
    # candidate itself remains at its generated resolution and is never used
    # to overwrite the exact source texture.
    reduced = candidate.resize(original.size, Image.Resampling.LANCZOS)
    original_mask = mask(original)
    candidate_mask = mask(reduced)
    intersection = sum(a and b for a, b in zip(original_mask, candidate_mask))
    union = sum(a or b for a, b in zip(original_mask, candidate_mask))
    changed = sum(a != b for a, b in zip(original_mask, candidate_mask))

    # Make a non-destructive UV-safe sibling: candidate RGB detail is kept,
    # while the original atlas occupancy mask is upscaled with nearest-neighbor
    # and reapplied. This preserves empty regions and UV island boundaries.
    scale = 4
    uv_candidate = candidate.resize((original.width * scale, original.height * scale), Image.Resampling.LANCZOS)
    # Build the 4x occupancy map explicitly so the downsample audit does not
    # depend on PIL's pixel-center rounding.
    original_rgb = original.convert("RGB")
    occupancy = Image.new("RGB", uv_candidate.size)
    original_pixels = list(original_rgb.getdata())
    background = (3, 2, 2)
    occupancy_pixels = []
    for y in range(original.height):
        row = original_pixels[y * original.width : (y + 1) * original.width]
        expanded_row = [pixel for pixel in row for _ in range(scale)]
        for _ in range(scale):
            occupancy_pixels.extend(expanded_row)
    occupancy.putdata(occupancy_pixels)
    uv_pixels = []
    candidate_pixels = list(uv_candidate.convert("RGB").getdata())
    occupancy_pixels = list(occupancy.getdata())
    for rgb, occ in zip(candidate_pixels, occupancy_pixels):
        if occ == background:
            uv_pixels.append((0, 0, 0))
        elif max(rgb) <= 16:
            # Keep the original non-black texel when the AI candidate moved
            # an island boundary or painted it black.
            uv_pixels.append(occ)
        else:
            uv_pixels.append(rgb)
    uv_safe = Image.new("RGB", uv_candidate.size)
    uv_safe.putdata(uv_pixels)
    uv_safe.save(UVSAFE, format="PNG", optimize=False)
    uv_safe_pixels = list(uv_safe.getdata())
    uv_safe_mask_equal = all(
        (uv_safe_pixels[(y * scale) * uv_safe.width + x * scale] != (0, 0, 0)) == (original_pixels[y * original.width + x] != background)
        for y in range(original.height)
        for x in range(original.width)
    )

    # Conservative detail-only variant: keep the exact atlas's low-frequency
    # color identity and inject only high-frequency residuals from the AI
    # candidate. This avoids changing eye/skin hue while still adding detail.
    base = original.resize((original.width * scale, original.height * scale), Image.Resampling.LANCZOS).convert("RGB")
    detail = uv_candidate.convert("RGB")
    low = detail.resize(original.size, Image.Resampling.LANCZOS).resize(detail.size, Image.Resampling.LANCZOS)
    base_pixels = list(base.getdata())
    detail_pixels = list(detail.getdata())
    low_pixels = list(low.getdata())
    conservative_pixels = []
    for b, d, l, occ in zip(base_pixels, detail_pixels, low_pixels, occupancy_pixels):
        if occ == background:
            conservative_pixels.append((0, 0, 0))
            continue
        # 0.35 residual gain is intentionally conservative; each channel is
        # rounded and clamped to the valid byte range.
        conservative_pixels.append(tuple(max(0, min(255, round(bc + 0.35 * (dc - lc)))) for bc, dc, lc in zip(b, d, l)))
    conservative = Image.new("RGB", detail.size)
    conservative.putdata(conservative_pixels)
    conservative.save(CONSERVATIVE, format="PNG", optimize=False)
    conservative_reduced = conservative.resize(original.size, Image.Resampling.LANCZOS)
    conservative_diff = sum(
        abs(int(a) - int(b)) for pa, pb in zip(original_rgb.getdata(), conservative_reduced.getdata()) for a, b in zip(pa, pb)
    )
    conservative_max = max(
        max(abs(int(a) - int(b)) for a, b in zip(pa, pb))
        for pa, pb in zip(original_rgb.getdata(), conservative_reduced.getdata())
    )
    report = {
        "schema": "t3b-aya-hd-texture-candidate/v1",
        "status": "review_required",
        "original": {"file": str(ORIGINAL.relative_to(ROOT)), "size": list(original.size), "sha256": sha(ORIGINAL)},
        "candidate": {"file": str(CANDIDATE.relative_to(ROOT)), "size": list(candidate.size), "sha256": sha(CANDIDATE)},
        "uvsafe_candidate": {"file": str(UVSAFE.relative_to(ROOT)), "size": list(uv_safe.size), "sha256": sha(UVSAFE)},
        "conservative_candidate": {"file": str(CONSERVATIVE.relative_to(ROOT)), "size": list(conservative.size), "sha256": sha(CONSERVATIVE)},
        "layout_audit": {
            "downsampled_to": list(reduced.size),
            "nonblack_mask_iou": intersection / union if union else 0.0,
            "changed_mask_pixels": changed,
            "mask_pixels_original": sum(original_mask),
            "mask_pixels_candidate": sum(candidate_mask),
            "uvsafe_mask_exact_after_nearest_roundtrip": uv_safe_mask_equal,
            "conservative_downsample_total_abs_rgb_error": conservative_diff,
            "conservative_downsample_max_channel_error": conservative_max,
        },
        "visual_review": {
            "face_identity_verified": False,
            "material_island_semantics_verified": False,
            "notes": "Candidate visibly changes eye/skin appearance and some island boundaries; keep it as a review asset only.",
        },
        "production_gate": {
            "exact_source_preserved": True,
            "candidate_reprojection_approved": False,
            "reason": "AI texture candidate must pass UV-island alignment and render comparison before runtime use; UV-safe sibling only freezes the original occupancy mask.",
        },
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
