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
} // namespace T3BAction
