#pragma once

#include <array>
#include <cstdint>

// CPU Gouraud inputs in original PSP world units, before PC/UE axis conversion.
// This deliberately scoped kernel supports the observed Aya directional/point
// lights and no input COLOR_0. It does not implement rasterization or blending.
namespace T3BGE {
using V3 = std::array<float,3>;
using Matrix43 = std::array<float,12>;
using Registers = std::array<std::uint32_t,256>;
struct Colors { std::array<std::uint8_t,4> primary; std::array<std::uint8_t,3> secondary; };
struct Vertex { V3 position; V3 normal; std::array<float,8> weights; };
struct Transformed { V3 worldPosition; V3 unitWorldNormal; };

Transformed Transform(const Vertex& vertex, const std::array<Matrix43,8>& bones,
                      unsigned weightCount, const Matrix43& world, bool reverseNormal);
Colors Light(const Registers& registers, const V3& worldPosition, const V3& unitWorldNormal);
}
