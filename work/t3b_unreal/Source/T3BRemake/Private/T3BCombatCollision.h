#pragma once

#include "T3BSourceData.h"

// PC collision adapter built from the visible source mesh, in PC metres with
// Y up. This does not claim to decode the original game's collision format.
namespace T3BCombat {
using Vec3 = T3BSource::Vec3;
struct RayHit {
    bool hit{};
    float distance{};
    Vec3 position{}, normal{}; // normal faces against the incoming ray
    std::uint32_t triangle{}, material{};
};
struct MoveResult {
    Vec3 position{}; // feet, not capsule centre
    bool grounded{}, wallBlocked{}, floorBlocked{}, stepped{};
};
class CollisionWorld {
public:
    // Caller proves texture alpha > 0 everywhere and blend off/depth write on.
    // Triangles with any zero vertex alpha are also excluded here. Build has a
    // strong failure guarantee; invalid data throws T3BSource::FormatError.
    void Build(const T3BSource::Scene& scene, const std::vector<bool>& materialSolid);
    RayHit Raycast(Vec3 start, Vec3 end) const;
    // Grounded kinematic movement: <=45 degree upward floors, nine disc support
    // samples, capsule/triangle wall checks, bounded substeps and axis sliding.
    // A small step is an adapter policy, not a recovered original-game rule.
    MoveResult MoveCapsule(Vec3 feet, Vec3 delta, float radius=.28f,
                           float height=1.84f, float stepHeight=.25f) const;
    bool FindGround(Vec3 feet, float maxRise, float maxDrop, float& height) const;
    std::size_t SolidTriangleCount() const { return triangles_.size(); }
    std::size_t FloorTriangleCount() const { return floors_.size(); }
    std::size_t ExcludedVertexAlphaCount() const { return excludedVertexAlpha_; }
private:
    struct Triangle {
        Vec3 a{}, b{}, c{}, low{}, high{}, normal{};
        std::uint32_t source{}, material{};
        bool floor{};
    };
    bool Supported(Vec3 feet, float radius, float rise, float drop, float& y) const;
    bool Blocked(Vec3 feet, float radius, float height) const;
    std::vector<Triangle> triangles_;
    std::vector<std::uint32_t> floors_;
    std::size_t excludedVertexAlpha_{};
};
} // namespace T3BCombat
