#pragma once

#include <cstdint>
#include <vector>

#include "T3BSourceData.h"

// Engine-independent, source-preserving structural reader for raw 3rd.fsd.
// The second record field remains opaque until an independent semantic join.
namespace T3BFSD {
struct Record {
    std::uint32_t tag{};
    std::uint32_t value{};
};
struct Index {
    std::uint32_t version{};
    std::uint32_t headerBytes{};
    std::uint32_t declaredRecordCount{};
    std::uint32_t declaredRecordStride{};
    std::uint32_t declaredBytes{};
    std::uint32_t packageSize{};
    std::uint32_t recordStart{};
    std::uint32_t sentinel{};
    std::vector<Record> records;
};

Index Load(const std::vector<std::uint8_t>& bytes);
} // namespace T3BFSD
