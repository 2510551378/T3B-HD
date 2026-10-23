// Exercise the production series reader/kernel, never duplicate its arithmetic.
#include "T3BGESeries.h"
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>

int main(int argc, char** argv) {
    try {
        if (argc != 4) return 2;
        std::ifstream in(argv[1], std::ios::binary);
        if (!in) throw std::runtime_error("Input not readable");
        std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(in)), {});
        const auto series = T3BGE::LoadSeries(bytes, 106);
        std::ofstream out(argv[2], std::ios::binary), uv(argv[3], std::ios::binary);
        if (!out || !uv) throw std::runtime_error("Output not writable");
        std::size_t count = 0;
        for (std::size_t i = 0; i < series.SampleCount(); ++i) {
            for (const auto& v : T3BGE::EvaluateSample(series, i)) {
                out.write(reinterpret_cast<const char*>(v.transform.worldPosition.data()), 12);
                out.write(reinterpret_cast<const char*>(v.transform.unitWorldNormal.data()), 12);
                out.write(reinterpret_cast<const char*>(v.colors.primary.data()), 4);
                out.write(reinterpret_cast<const char*>(v.colors.secondary.data()), 3); out.put(0);
                uv.write(reinterpret_cast<const char*>(v.uv.data()), 8); ++count;
            }
        }
        out.close(); uv.close();
        if (!out || !uv) throw std::runtime_error("Output write failed");
        std::cout << "{\"samples\":" << series.SampleCount() << ",\"vertices\":" << count << "}\n";
        return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
