#pragma once
#include "T3BGEGeometry.h"
#include "T3BGEEffectVertexColor.h"
#include "T3BGELighting.h"
#include <array>

// Source-camera calibration transport, not a raw PSP format or gameplay clock.
namespace T3BGE {
struct SceneDraw {
    std::uint32_t texture{}, ordinal{}, flags{}, stencilRef{};
    std::array<float,16> localToClip{};
    std::array<float,4> fog{};
    std::array<std::uint32_t,4> fogRGB{};
    std::vector<GPUVertex> vertices;
};
struct SceneFrame { std::uint32_t sample{}; std::vector<SceneDraw> draws; };
struct SceneGeometry {
    std::uint32_t width{},height{};
    std::vector<GPUAtlas> atlases;
    std::vector<SceneFrame> frames;
};
struct SceneEffectBinding {
    SceneDraw expected;
    Registers registers{};
    std::uint32_t vtype{},count{},mode{};
    EffectRGBA source{},parent{};
    std::vector<std::uint8_t> palette,before,expectedAfter;
    std::vector<std::uint32_t> colorIndices;
};
struct SceneEffectBindings {
    std::vector<GPUAtlas> atlases;
    std::vector<std::vector<SceneEffectBinding>> frames;
};
SceneGeometry LoadSceneGeometry(const std::vector<std::uint8_t>& bytes);
SceneEffectBindings LoadSceneEffectBindings(const std::vector<std::uint8_t>& bytes);
// Evaluates source/parent/palette and patches original vertices on every call.
// The whole frame is returned atomically; rejected bindings cannot partially edit it.
SceneFrame EvaluateSceneFrame(const SceneGeometry& scene,std::uint32_t sample,
                             const SceneEffectBindings* effects=nullptr);
} // namespace T3BGE
