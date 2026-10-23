#pragma once
#include "T3BGELighting.h"
#include <cstddef>
#include <cstdint>
#include <vector>

// Recorded GE sample replay. There is deliberately no inferred animation clock,
// bone-name mapping, matrix interpolation, or cross-capture weapon binding.
namespace T3BGE {
struct SeriesDraw {
    Registers registers{};
    Matrix43 world{};
    std::array<Matrix43, 8> bones{};
    std::uint32_t weightCount{};
    std::vector<Vertex> vertices;
    std::vector<std::array<float, 2>> uv;
};
struct Series {
    std::uint32_t drawsPerSample{};
    std::vector<SeriesDraw> draws;
    std::size_t SampleCount() const;
};
struct LitVertex {
    Transformed transform;
    Colors colors;
    std::array<float, 2> uv{};
};
// Accepts the retained T3BLIT1 input format; bounds/truncation/float errors throw.
Series LoadSeries(const std::vector<std::uint8_t>& bytes, std::uint32_t drawsPerSample);
std::vector<LitVertex> EvaluateSample(const Series& series, std::size_t sample);
} // namespace T3BGE
