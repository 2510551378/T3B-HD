#pragma once
#include "T3BGELighting.h"
#include <vector>

namespace T3BGE {
struct EffectVertex {
    V3 position{}; // Original normalized PSP local coordinates.
    std::array<float,2> uv{}; // Source GE scale/offset already applied once.
    std::array<std::uint8_t,4> color{};
};
struct EffectGeometry {
    std::vector<EffectVertex> vertices;
    std::vector<std::uint32_t> triangleIndices;
};
// Observed unweighted/unlit PRIM4 VTYPE102/11e. Keeps original strip topology,
// including degenerate triangles. Does not infer effect timing or transforms.
EffectGeometry DecodeOriginalEffectStrip(std::uint32_t vtype, std::uint32_t count,
    const std::vector<std::uint8_t>& sourceBytes, const Registers& registers);
} // namespace T3BGE
