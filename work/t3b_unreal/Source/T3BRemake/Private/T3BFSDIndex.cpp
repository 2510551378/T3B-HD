#include "T3BFSDIndex.h"

#include <cstring>

namespace {
std::uint32_t U32(const std::vector<std::uint8_t>& bytes, std::size_t off) {
    if (off > bytes.size() || bytes.size() - off < 4) throw T3BSource::FormatError("truncated 3rd.fsd field");
    const auto* p = bytes.data() + off;
    return std::uint32_t(p[0]) | (std::uint32_t(p[1]) << 8) |
        (std::uint32_t(p[2]) << 16) | (std::uint32_t(p[3]) << 24);
}
}

namespace T3BFSD {
Index Load(const std::vector<std::uint8_t>& bytes) {
    if (bytes.size() < 0x40 || U32(bytes, 0) != 1) throw T3BSource::FormatError("invalid 3rd.fsd version");
    Index result;
    result.version = U32(bytes, 0);
    result.headerBytes = U32(bytes, 4);
    result.declaredRecordCount = U32(bytes, 8);
    result.declaredRecordStride = U32(bytes, 0x0c);
    result.declaredBytes = U32(bytes, 0x14);
    result.packageSize = U32(bytes, 0x18);
    if (result.headerBytes != 64 || result.declaredRecordCount != 761 || result.declaredBytes != bytes.size())
        throw T3BSource::FormatError("unexpected 3rd.fsd header contract");
    result.recordStart = 0x730;
    const std::size_t recordBytes = std::size_t(result.declaredRecordCount) * 8;
    if (result.recordStart > bytes.size() || recordBytes > bytes.size() - result.recordStart)
        throw T3BSource::FormatError("3rd.fsd record table outside file");
    result.records.reserve(result.declaredRecordCount);
    for (std::uint32_t i = 0; i < result.declaredRecordCount; ++i) {
        const std::size_t off = result.recordStart + std::size_t(i) * 8;
        Record row{U32(bytes, off), U32(bytes, off + 4)};
        if (row.tag != 1) throw T3BSource::FormatError("3rd.fsd record tag mismatch");
        result.records.push_back(row);
    }
    const std::size_t sentinelOffset = result.recordStart + recordBytes;
    result.sentinel = U32(bytes, sentinelOffset);
    if (result.sentinel != 1 || sentinelOffset + 4 != bytes.size())
        throw T3BSource::FormatError("3rd.fsd sentinel/extent mismatch");
    return result;
}
} // namespace T3BFSD
