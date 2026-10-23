#pragma once
#include <array>
#include <cstdint>
#include <vector>

namespace T3BGE {
using EffectRGBA=std::array<float,4>;
EffectRGBA ModulateOriginalEffectRGBA(const EffectRGBA& source,const EffectRGBA& parent);
EffectRGBA ProcessOriginalEffectColorMode(const EffectRGBA& rgba,std::uint8_t mode);
bool NeedsOriginalEffectColorUpdate(const EffectRGBA& previous,const EffectRGBA& current,
    std::uint32_t pending,std::uint32_t capacity);
// This is a vertex-color palette, independent of the texture CLUT.
std::vector<std::uint8_t> ModulateOriginalEffectVertexPalette(
    const std::vector<std::uint8_t>& source,const EffectRGBA& rgba);
void PatchOriginalEffectVertexColors(std::uint32_t vtype,std::vector<std::uint8_t>& vertices,
    const std::vector<std::uint32_t>& colorIndices,const std::vector<std::uint8_t>& palette);
} // namespace T3BGE
