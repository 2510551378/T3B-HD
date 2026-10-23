#pragma once
#include <array>
#include <cstdint>
namespace T3BGE {
using OriginalMatrix16=std::array<float,16>;
struct OriginalMatrixInput {
    std::uint32_t mode{}; // original wrapper mode after its unsigned-minus-one conversion
    float scalar{};       // original COP1 f12, source units
    std::array<float,3> p30{};
    OriginalMatrix16 input{};
    OriginalMatrix16 parent{}; // effective L (P+60 or node-parent path)
    OriginalMatrix16 global{}; // G from original global slot
};
// Modes 0 and 1 are the only paths with complete retained runtime coverage.
OriginalMatrix16 ComputeOriginalMatrixMode0(const OriginalMatrixInput&);
OriginalMatrix16 ComputeOriginalMatrixMode1(const OriginalMatrixInput&);
OriginalMatrix16 ComputeOriginalMatrix(const OriginalMatrixInput&);
} // namespace T3BGE
