#pragma once
#include "T3BGESeries.h"
#include <array>

namespace T3BGE {
// Source indices1/2, without inferred anatomical or gameplay names. These
// definitions apply only to the recovered rifle. Matrices are column-major.
using MarkerMatrix = std::array<double,16>;
struct WeaponMarkerDefinitions {
    float originalVertexWeight{};
    Matrix43 expectedGEroot{};
    std::array<MarkerMatrix,2> originalLocalMatrices{};
};
struct WeaponMarkerPose {
    MarkerMatrix world{};
    std::array<double,3> unitPlusZ{};
};
// T3BWMK1 stores original source0+80 and source1/2+40 F32 matrices, unchanged.
WeaponMarkerDefinitions LoadWeaponMarkers(const std::vector<std::uint8_t>& bytes);
// Original full-F32 WORLD x source40, using separate rounded multiplies/adds.
// Only the captured default-prefix source1 path has actual CPU bit validation.
std::array<float,16> ComposeOriginalWeaponMarker(
    const WeaponMarkerDefinitions& definitions, unsigned sourceIndex,
    const std::array<float,16>& fullOriginalWorld);
// Compose original source1/2 directly with current GE WORLD, as the original
// helper does. BONE is checked only for this rifle's bind identity. GE WORLD is
// quantized; these are not same-frame unquantized CPU source1/2 snapshots.
std::array<WeaponMarkerPose,2> EvaluateWeaponMarkers(
    const WeaponMarkerDefinitions& definitions, const SeriesDraw& rifle);
} // namespace T3BGE
