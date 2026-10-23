// Calls the production reader and marker evaluator; no alternative transform.
#include "T3BGEWeaponMarkers.h"
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>

std::vector<std::uint8_t> Read(const char* path) {
    std::ifstream in(path,std::ios::binary);
    if (!in) throw std::runtime_error("Input not readable");
    return {(std::istreambuf_iterator<char>(in)),{}};
}
int main(int argc,char** argv) {
    try {
        if (argc!=4) return 2;
        const auto series=T3BGE::LoadSeries(Read(argv[1]),1);
        const auto definitions=T3BGE::LoadWeaponMarkers(Read(argv[2]));
        std::ofstream out(argv[3],std::ios::binary);
        if (!out) throw std::runtime_error("Output not writable");
        for (const auto& d:series.draws) for (const auto& marker:T3BGE::EvaluateWeaponMarkers(definitions,d)) {
            out.write(reinterpret_cast<const char*>(marker.world.data()),sizeof(double)*16);
            out.write(reinterpret_cast<const char*>(marker.unitPlusZ.data()),sizeof(double)*3);
        }
        out.close(); if (!out) throw std::runtime_error("Output write failed");
        std::cout<<"{\"samples\":"<<series.SampleCount()<<",\"markersPerSample\":2}\n";
        return 0;
    } catch (const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
