#include "T3BGEGeometry.h"
#include <cmath>
#include <cstring>
#include <stdexcept>

namespace {
void Check(bool ok, const char* reason) { if (!ok) throw std::runtime_error(reason); }
class Reader {
    const std::vector<std::uint8_t>& b; std::size_t at = 0;
public:
    explicit Reader(const std::vector<std::uint8_t>& bytes) : b(bytes) {}
    void Need(std::size_t size) const { Check(size <= b.size() - at, "Truncated GE geometry"); }
    std::uint32_t Word() {
        Need(4); const auto* p = b.data() + at; at += 4;
        return std::uint32_t(p[0]) | std::uint32_t(p[1]) << 8 | std::uint32_t(p[2]) << 16 | std::uint32_t(p[3]) << 24;
    }
    float Float() { auto word = Word(); float v; std::memcpy(&v, &word, 4); Check(std::isfinite(v), "Nonfinite GE GPU vertex"); return v; }
    void Bytes(std::vector<std::uint8_t>& target, std::size_t size) {
        Need(size); target.assign(b.begin() + at, b.begin() + at + size); at += size;
    }
    bool End() const { return at == b.size(); }
};
}
namespace T3BGE {
GPUGeometry LoadGPUGeometry(const std::vector<std::uint8_t>& bytes) {
    Check(bytes.size() <= 128u * 1024u * 1024u, "GE geometry exceeds supported file size");
    Reader r(bytes); Check(r.Word() == 0x47423354 && r.Word() == 0x00315550, "Wrong T3BGPU1 geometry magic");
    GPUGeometry result;
    result.calibrationWidth = r.Word(); result.calibrationHeight = r.Word();
    Check(result.calibrationWidth > 0 && result.calibrationWidth <= 8192 && result.calibrationHeight > 0 &&
          result.calibrationHeight <= 8192, "Invalid GE calibration dimensions");
    const auto count = r.Word(), atlases = r.Word();
    Check(count > 0 && count <= 4096 && atlases == 2, "Unsupported GE frame/atlas contract");
    for (std::uint32_t i = 0; i < atlases; ++i) {
        GPUAtlas t; t.width = r.Word(); t.height = r.Word();
        Check(t.width > 0 && t.width <= 4096 && t.height > 0 && t.height <= 4096, "GE atlas dimensions invalid");
        r.Bytes(t.rgba, std::size_t(t.width) * t.height * 4); result.atlases.push_back(std::move(t));
    }
    for (std::uint32_t i = 0; i < count; ++i) {
        GPUFrame frame; frame.sample = r.Word(); const auto draws = r.Word();
        Check(frame.sample == i && draws > 0 && draws <= 4096, "GE frame/order invalid");
        for (std::uint32_t j = 0; j < draws; ++j) {
            GPUDraw d; d.texture = r.Word(); d.ordinal = r.Word(); const auto n = r.Word();
            Check(d.texture < atlases && d.ordinal == j && n > 0 && n <= 4096 && n % 3 == 0, "GE draw contract invalid");
            r.Need(std::size_t(n) * sizeof(GPUVertex)); d.vertices.resize(n);
            for (auto& v : d.vertices) {
                for (float& x : v.position) x = r.Float();
                for (float& x : v.uv) x = r.Float();
                for (float& x : v.color) { x = r.Float(); Check(x >= 0 && x <= 1, "GE primary vertex color outside UNORM range"); }
            }
            frame.draws.push_back(std::move(d));
        }
        result.frames.push_back(std::move(frame));
    }
    Check(r.End(), "Trailing GE geometry bytes"); return result;
}
} // namespace T3BGE
