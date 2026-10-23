#pragma once

#include <array>
#include <cstdint>
#include <stdexcept>
#include <vector>

// Engine-independent, source-preserving readers and affine skinning.
// Load failures throw FormatError. No UE types or FTransform decomposition.
namespace T3BSource {
struct Vec3 { float x{}, y{}, z{}; };
struct Vec2 { float u{}, v{}; };
struct SceneDraw { std::uint32_t first{}, count{}, material{}; };
struct SceneVertex { Vec3 position; Vec2 uv; std::array<std::uint8_t,4> rgba{}; };
struct Scene {
    std::vector<SceneDraw> draws;
    std::vector<SceneVertex> vertices;
    std::array<float,3> player{}, enemy{}; // PC x, z, yaw (radians)
    float units{}, floor{}; // metadata; positions are ALREADY in PC coordinates
    std::uint32_t materials{};
};
struct SkinPacket { std::uint32_t first{}, count{}, material{}, primitive{}; };
struct SkinVertex {
    Vec3 position; Vec2 uv; Vec3 normal;
    std::uint32_t count{};
    std::array<std::uint32_t,8> bone{};
    std::array<float,8> weight{};
};
struct Skin {
    std::uint32_t bones{}, materials{}, flags{};
    float units{}, floor{};
    std::vector<std::int32_t> parent;
    std::vector<SkinPacket> packets;
    std::vector<SkinVertex> vertices;
    std::vector<float> time; // stored seconds, strictly increasing, beginning at 0
    // Raw affine rows: matrix[(sample * bones + bone) * 12 + row * 4 + column].
    // They need not be orthonormal and must never be converted to FTransform.
    std::vector<float> matrix;
};
class FormatError : public std::runtime_error {
public: explicit FormatError(const char* message) : std::runtime_error(message) {}
};
Scene LoadScene(const std::vector<std::uint8_t>& bytes);
Skin LoadSkin(const std::vector<std::uint8_t>& bytes);
// Interpolates raw affine components at saved sample times, clamps both ends.
// Returned points are in original source units before units/floor/actor transform.
std::vector<Vec3> PoseOriginal(const Skin& skin, float seconds);
// Converts one posed original point to PC space with the exact C transform.
Vec3 ToPC(const Skin& skin, Vec3 original, float actorX, float actorZ, float yaw);
// Unreal centimeters, left-handed: (PC z, -PC x, PC y) * 100. Negating one axis
// converts the right-handed PC frame without mirroring the scene or reversing winding.
Vec3 ToUE(Vec3 pc);
} // namespace T3BSource
