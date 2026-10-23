#include "T3BActionClip.h"

#include <cmath>
#include <algorithm>

namespace {
void Need(bool ok, const char* message) {
    if (!ok) throw T3BSource::FormatError(message);
}
bool Same(float a, float b) { return a == b; }
}

namespace T3BAction {
Pair LoadSynchronizedPair(const std::vector<std::uint8_t>& bodyBytes,
                          const std::vector<std::uint8_t>& weaponBytes) {
    Pair pair{T3BSource::LoadSkin(bodyBytes), T3BSource::LoadSkin(weaponBytes)};
    const auto& body = pair.body;
    const auto& weapon = pair.weapon;
    Need(body.bones == 44 && body.packets.size() == 106 && body.vertices.size() == 3456,
         "unexpected Aya action clip contract");
    Need(weapon.bones == 1 && weapon.packets.size() == 1 && weapon.vertices.size() == 243,
         "unexpected weapon action clip contract");
    Need(body.time.size() == 60 && weapon.time.size() == body.time.size(),
         "action clip sample count mismatch");
    Need(Same(body.units, weapon.units) && Same(body.floor, weapon.floor) && body.flags == weapon.flags,
         "action clip metadata mismatch");
    Need(body.time.front() == 0.0f && weapon.time.front() == 0.0f,
         "action clip does not start at zero");
    for (std::size_t i = 0; i < body.time.size(); ++i) {
        Need(std::isfinite(body.time[i]) && std::isfinite(weapon.time[i]), "nonfinite action clip time");
        Need(body.time[i] == weapon.time[i], "Aya/weapon sample times differ");
        if (i) Need(body.time[i] > body.time[i - 1], "action clip times not increasing");
    }
    return pair;
}
void ValidateCompatible(const T3BSource::Skin& a, const T3BSource::Skin& b) {
    Need(a.bones == b.bones && a.materials == b.materials && a.flags == b.flags &&
         a.units == b.units && a.floor == b.floor && a.parent == b.parent &&
         a.packets.size() == b.packets.size() && a.vertices.size() == b.vertices.size(),
         "action clip changes reference skin contract");
    for (std::size_t i = 0; i < a.packets.size(); ++i) {
        const auto& x=a.packets[i]; const auto& y=b.packets[i];
        Need(x.first==y.first && x.count==y.count && x.material==y.material && x.primitive==y.primitive,
             "action clip changes packet/material binding");
    }
    for (std::size_t i = 0; i < a.vertices.size(); ++i) {
        const auto& x=a.vertices[i]; const auto& y=b.vertices[i];
        Need(x.position.x==y.position.x && x.position.y==y.position.y && x.position.z==y.position.z &&
             x.normal.x==y.normal.x && x.normal.y==y.normal.y && x.normal.z==y.normal.z &&
             x.uv.u==y.uv.u && x.uv.v==y.uv.v && x.count==y.count && x.bone==y.bone && x.weight==y.weight,
             "action clip changes geometry/UV/normal/influences");
    }
}
Phase PlaybackPhase(double elapsed, float duration, bool loop, float seamSeconds) {
    Need(std::isfinite(elapsed) && std::isfinite(duration) && duration > 0 &&
         std::isfinite(seamSeconds) && seamSeconds > 0, "invalid shared playback clock");
    if (!loop) return {static_cast<float>(std::clamp(elapsed, 0.0, double(duration))), 0, 0};
    const double at=std::fmod(std::max(0.0, elapsed), double(duration)+seamSeconds);
    if (at <= duration) return {static_cast<float>(at), 0, 0};
    // Smoothstep keeps the seam's blend velocity zero at each endpoint.
    const float u=static_cast<float>((at-duration)/seamSeconds);
    return {duration, 0, u*u*(3.f-2.f*u)};
}
std::vector<T3BSource::Vec3> Pose(const T3BSource::Skin& skin, const Phase& phase) {
    Need(std::isfinite(phase.first) && std::isfinite(phase.second) &&
         std::isfinite(phase.blend) && phase.blend>=0 && phase.blend<=1,
         "invalid paired playback phase");
    auto points=T3BSource::PoseOriginal(skin, phase.first);
    if (phase.blend > 0) {
        const auto next=T3BSource::PoseOriginal(skin, phase.second);
        for (std::size_t i=0; i<points.size(); ++i) {
            auto& p=points[i]; const auto& q=next[i];
            p.x+=(q.x-p.x)*phase.blend; p.y+=(q.y-p.y)*phase.blend; p.z+=(q.z-p.z)*phase.blend;
        }
    }
    return points;
}
} // namespace T3BAction
