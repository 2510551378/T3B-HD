#pragma once
#include <cstdint>
#include <vector>

// Exported, source-verified compatibility geometry, not a raw PSP format.
// T3BGPU1 has one fixed verified shader/depth/blend contract and no source clock.
namespace T3BGE {
struct GPUVertex { float position[3], uv[2], color[4]; };
static_assert(sizeof(GPUVertex) == 36, "GE GPU stream must have no implicit padding");
struct GPUDraw { std::uint32_t texture{}, ordinal{}; std::vector<GPUVertex> vertices; };
struct GPUFrame { std::uint32_t sample{}; std::vector<GPUDraw> draws; };
struct GPUAtlas { std::uint32_t width{}, height{}; std::vector<std::uint8_t> rgba; };
struct GPUGeometry {
    std::uint32_t calibrationWidth{}, calibrationHeight{};
    std::vector<GPUAtlas> atlases;
    std::vector<GPUFrame> frames;
};
GPUGeometry LoadGPUGeometry(const std::vector<std::uint8_t>& bytes);
} // namespace T3BGE
