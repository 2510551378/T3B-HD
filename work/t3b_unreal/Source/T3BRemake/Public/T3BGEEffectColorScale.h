#pragma once
#include <array>

namespace T3BGE {
// Source units, finite values, canonical/default-entry VFPU prefix arithmetic.
// These structures model only the observed type16/type7 fields, not allocation
// ownership: original definitions23/24 share their parameter blocks.
struct EffectColorState {
    std::array<float,4> Color,Base,Velocity;
};
struct EffectColorKey {
    std::array<float,4> Base,Velocity;
};
struct EffectPercentScaleState {
    std::array<float,4> Scale,Percent;
};

EffectColorState ChangeOriginalEffectColor(const EffectColorState& state,
    const EffectColorKey& previous,const EffectColorKey& current,float time);
EffectColorState EvaluateOriginalEffectColor(const EffectColorState& state,float time);
EffectColorState WrapOriginalEffectColor(const EffectColorState& state,
    const EffectColorKey& previous,const EffectColorKey& current,float time,float previousTime);
EffectPercentScaleState ChangeOriginalEffectPercentScale(const EffectPercentScaleState& state,
    const std::array<float,4>& previous,const std::array<float,4>& current);
EffectPercentScaleState ResetOriginalEffectPercentScale(const EffectPercentScaleState& state);
} // namespace T3BGE
