#include "T3BGESeries.h"
#include <cmath>
#include <cstring>
#include <stdexcept>

namespace {
void Check(bool ok, const char* reason) { if (!ok) throw std::runtime_error(reason); }
class Reader {
    const std::vector<std::uint8_t>& bytes;
    std::size_t at = 0;
public:
    explicit Reader(const std::vector<std::uint8_t>& source) : bytes(source) {}
    std::uint32_t Word() {
        Check(bytes.size() - at >= 4, "Truncated GE series word");
        const auto* p = bytes.data() + at; at += 4;
        return std::uint32_t(p[0]) | (std::uint32_t(p[1]) << 8) |
            (std::uint32_t(p[2]) << 16) | (std::uint32_t(p[3]) << 24);
    }
    float Float() {
        const std::uint32_t word = Word(); float v;
        std::memcpy(&v, &word, 4);
        Check(std::isfinite(v), "Nonfinite GE series float"); return v;
    }
    bool End() const { return at == bytes.size(); }
};
}
namespace T3BGE {
std::size_t Series::SampleCount() const {
    Check(drawsPerSample != 0 && draws.size() % drawsPerSample == 0, "Invalid GE sample boundaries");
    return draws.size() / drawsPerSample;
}
Series LoadSeries(const std::vector<std::uint8_t>& bytes, std::uint32_t drawsPerSample) {
    Check(drawsPerSample > 0 && drawsPerSample <= 1024, "Invalid GE draws per sample");
    Check(bytes.size() <= 128u * 1024u * 1024u, "GE series size exceeds supported replay bounds");
    Reader r(bytes);
    Check(r.Word() == 0x4c423354 && r.Word() == 0x00315449, "Wrong GE series magic");
    const auto count = r.Word();
    Check(count > 0 && count <= 16384 && count % drawsPerSample == 0, "Invalid GE draw count");
    Series series; series.drawsPerSample = drawsPerSample;
    series.draws.reserve(count);
    for (std::uint32_t i = 0; i < count; ++i) {
        SeriesDraw d;
        for (auto& word : d.registers) {
            word = r.Word(); Check(word <= 0xffffff, "Invalid GE register payload");
        }
        for (auto& v : d.world) v = r.Float();
        for (auto& bone : d.bones) for (auto& v : bone) v = r.Float();
        const auto vertices = r.Word(); d.weightCount = r.Word();
        Check(vertices > 0 && vertices <= 4096 && vertices % 3 == 0, "Invalid GE triangle vertices");
        Check(d.weightCount > 0 && d.weightCount <= 8, "Invalid GE weight slots");
        Check((d.registers[4] & 0xffff) == vertices && ((d.registers[4] >> 16) & 7) == 3,
              "GE PRIM and vertex buffer disagree");
        const auto vt = d.registers[0x12];
        Check(!(vt & (1u << 23)) && ((vt >> 11) & 3) == 0 && ((vt >> 18) & 7) == 0 &&
              ((vt >> 2) & 7) == 0 && ((vt >> 9) & 3) == 2 && ((vt >> 7) & 3) == 2 &&
              ((vt >> 5) & 3) == 1 && (vt & 3) == 2 && ((vt >> 14) & 7) + 1 == d.weightCount,
              "Unsupported original GE vertex contract");
        d.vertices.resize(vertices); d.uv.resize(vertices);
        for (std::uint32_t j = 0; j < vertices; ++j) {
            auto& v = d.vertices[j];
            for (auto& x : v.position) x = r.Float();
            for (auto& x : v.normal) x = r.Float();
            for (std::size_t k = 0; k < v.weights.size(); ++k) {
                v.weights[k] = r.Float();
                Check(v.weights[k] >= 0 && v.weights[k] < 2 && (k < d.weightCount || v.weights[k] == 0),
                      "Invalid original GE weight");
            }
            for (auto& x : d.uv[j]) x = r.Float();
        }
        series.draws.push_back(std::move(d));
    }
    Check(r.End(), "Trailing GE series bytes");
    // Fixed packet/vertex identity across samples. Positions and original weights
    // are inputs, not per-sample data; changing them requires a different series.
    for (std::size_t i = drawsPerSample; i < series.draws.size(); ++i) {
        const auto& a = series.draws[i % drawsPerSample]; const auto& b = series.draws[i];
        Check(a.registers[0x12] == b.registers[0x12] && a.weightCount == b.weightCount &&
              a.vertices.size() == b.vertices.size() && a.uv == b.uv, "GE series packet layout changed");
        for (std::size_t j = 0; j < a.vertices.size(); ++j)
            Check(a.vertices[j].position == b.vertices[j].position && a.vertices[j].normal == b.vertices[j].normal &&
                  a.vertices[j].weights == b.vertices[j].weights, "GE series packet geometry changed");
    }
    return series;
}
std::vector<LitVertex> EvaluateSample(const Series& series, std::size_t sample) {
    Check(sample < series.SampleCount(), "GE sample outside capture");
    std::vector<LitVertex> result;
    for (std::size_t i = sample * series.drawsPerSample; i < (sample + 1) * series.drawsPerSample; ++i) {
        const auto& d = series.draws[i];
        Check(d.vertices.size() == d.uv.size(), "GE UV/position count differs");
        for (std::size_t j = 0; j < d.vertices.size(); ++j) {
            const auto t = Transform(d.vertices[j], d.bones, d.weightCount, d.world, d.registers[0x51] & 1);
            result.push_back({t, Light(d.registers, t.worldPosition, t.unitWorldNormal), d.uv[j]});
        }
    }
    return result;
}
} // namespace T3BGE
