#pragma once
#include <array>
#include <cstdint>
#include "T3BGEVfpuRandom.h"

namespace T3BGE {
// A retained64-byte target window, not a recovered allocation/type declaration.
using EffectModifierWindow=std::array<float,16>;
struct EffectModifierChannel {
    bool enabled{};
    std::uint8_t mode{};
    std::array<float,3> amplitude{};
};
using EffectModifierChannels=std::array<EffectModifierChannel,3>;
// The original scalar helper updates all32 seed bits, returns low31 bits.
std::uint32_t NextOriginalEffectRandom(std::uint32_t& seed);
// VFPU RCX seed state is not recovered: actual VRNDF2 vectors are explicit
// inputs. This function never substitutes an unrelated host random generator.
void ApplyOriginalType23Modifiers(EffectModifierWindow& target,const EffectModifierChannels& channels,
    const std::array<std::array<float,3>,3>& observedVRNDF2,const std::array<float,3>& vectorCenter);
// Optional exact RCX path. The caller owns the seed provenance; this function
// is never used when only post-VRNDF2 observations are available.
std::uint32_t ApplyOriginalType23ModifiersFromRCX(EffectModifierWindow& target,const EffectModifierChannels& channels,
    VFPURCXState& rcx,const std::array<float,3>& vectorCenter);
// Executes the original scalar RNG and percentile conversion in source order.
void ApplyOriginalType24Modifiers(EffectModifierWindow& target,const EffectModifierChannels& channels,
    bool independentAxes,std::uint32_t& seed);
} // namespace T3BGE
