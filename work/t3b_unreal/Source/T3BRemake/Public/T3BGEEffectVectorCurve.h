#pragma once
#include <array>
namespace T3BGE {
// Original type6 source units. XYZ helper updates and quad evaluation have
// different W behavior; these are not named bones, angles or world positions.
struct EffectVectorState {
    std::array<float,4> Current,Base,Velocity,Acceleration;
};
struct EffectVectorKey {
    std::array<float,3> Base,Velocity,Acceleration;
};
EffectVectorState ChangeOriginalEffectVector(const EffectVectorState& state,
    const EffectVectorKey& previous,const EffectVectorKey& current,float time);
EffectVectorState WrapOriginalEffectVector(const EffectVectorState& state,
    const EffectVectorKey& previous,const EffectVectorKey& current,float time,float previousTime);
EffectVectorState EvaluateOriginalEffectVector(const EffectVectorState& state,float time);
} // namespace T3BGE
