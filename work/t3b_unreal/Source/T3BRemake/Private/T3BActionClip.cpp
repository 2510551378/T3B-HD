#include "T3BActionClip.h"

#include <cmath>

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
} // namespace T3BAction
