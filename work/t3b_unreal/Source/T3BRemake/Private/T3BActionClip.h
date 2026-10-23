#pragma once

#include "T3BSourceData.h"

#include <vector>

namespace T3BAction {
struct Pair {
    T3BSource::Skin body;
    T3BSource::Skin weapon;
};

// Loads and validates a synchronized Aya/weapon source pair.  This checks the
// capture contract only; it does not infer an original action name.
Pair LoadSynchronizedPair(const std::vector<std::uint8_t>& bodyBytes,
                          const std::vector<std::uint8_t>& weaponBytes);
// Refuse action clips that silently replace bind geometry, weights or materials.
void ValidateCompatible(const T3BSource::Skin& reference, const T3BSource::Skin& candidate);
struct Phase { float first{}, second{}, blend{}; };
// PC preview adapter: retain finite source samples, then blend last->first.
// Both actors consume this ONE phase; this does not recover a game loop/clock.
Phase PlaybackPhase(double elapsed, float duration, bool loop, float seamSeconds = 0.12f);
std::vector<T3BSource::Vec3> Pose(const T3BSource::Skin& skin, const Phase& phase);
} // namespace T3BAction
