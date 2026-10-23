#pragma once
#include <cstdint>

namespace T3BGE {
// Original numeric slices, in source time units. These functions do not supply
// a seconds conversion, lifecycle events, boundary callbacks, or property curves.
float AdvanceOriginalEffectTime(float current, float effectiveDelta);
float WrapOriginalEffectTime(float currentAfterBoundaryCallbacks,
                             std::uint16_t loopStart, std::uint16_t loopEnd);
float RelativeOriginalEffectTime(float nodeTime, bool hasStartRecord,
                                 std::int16_t signedStart);
} // namespace T3BGE
