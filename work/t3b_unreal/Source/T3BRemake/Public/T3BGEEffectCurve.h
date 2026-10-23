#pragma once
#include <array>
#include <cstdint>

namespace T3BGE {
// Original type155 parameter +8..+1c and record +10..+24. Source units;
// rendering/material interpretation and timeline selection remain external.
struct EffectCurve2D {
    float Position[2];
    float Velocity[2];
    float Acceleration[2];
};

EffectCurve2D ChangeOriginalEffectCurve(const EffectCurve2D& state,
    const EffectCurve2D& previousKey, const EffectCurve2D& currentKey,
    float relativeTime);

EffectCurve2D WrapOriginalEffectCurve(const EffectCurve2D& state,
    const EffectCurve2D& previousKey, const EffectCurve2D& currentKey,
    float relativeTime, float previousRelativeTime);

std::array<float,2> EvaluateOriginalEffectCurve(const EffectCurve2D& state,
    float relativeTime);

// The original binder preserves a pixel offset equal to width/height. Thus
// exactly width maps to1 rather than0 before adding the per-group offset.
std::array<float,2> BindOriginalEffectUV(const std::array<float,2>& pixelOffset,
    std::int32_t width, std::int32_t height,
    const std::array<float,2>& groupOffset);
} // namespace T3BGE
