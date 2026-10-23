#pragma once
#include <array>
#include <cstdint>
namespace T3BGE {
struct VFPURCXState { std::array<std::uint32_t,8> words{}; };
void InitOriginalVFPURCXDefault(VFPURCXState& state);
void InitOriginalVFPURCXSeed(VFPURCXState& state,std::uint32_t seed);
std::uint32_t GenerateOriginalVFPURandom(VFPURCXState& state);
std::uint32_t GenerateOriginalVRNDI(VFPURCXState& state);
std::uint32_t GenerateOriginalVRNDF1(VFPURCXState& state);
std::uint32_t GenerateOriginalVRNDF2(VFPURCXState& state);
} // namespace T3BGE
