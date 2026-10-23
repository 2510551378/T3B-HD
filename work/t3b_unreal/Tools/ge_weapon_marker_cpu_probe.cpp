// Exercise the production original-F32 marker composition on retained CPU WORLD.
#include "T3BGEWeaponMarkers.h"
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>

std::vector<std::uint8_t> Read(const char* file) {
    std::ifstream in(file,std::ios::binary);
    if (!in) throw std::runtime_error("Unreadable marker input");
    return {(std::istreambuf_iterator<char>(in)),{}};
}
int main(int argc,char** argv) {
    try {
        if (argc!=4) return 2;
        const auto definitions=T3BGE::LoadWeaponMarkers(Read(argv[1]));
        const auto worlds=Read(argv[2]);
        if (worlds.empty() || worlds.size()%64 || worlds.size()>64*240)
            throw std::runtime_error("Invalid original CPU WORLD extent");
        std::ofstream out(argv[3],std::ios::binary);
        if (!out) throw std::runtime_error("Output not writable");
        for (std::size_t at=0; at<worlds.size(); at+=64) {
            std::array<float,16> world{};
            std::memcpy(world.data(),worlds.data()+at,64);
            const auto marker=T3BGE::ComposeOriginalWeaponMarker(definitions,1,world);
            out.write(reinterpret_cast<const char*>(marker.data()),64);
        }
        out.close(); if (!out) throw std::runtime_error("Marker output failed");
        std::cout<<"{\"originalCPUWorlds\":"<<worlds.size()/64<<"}\n";
        return 0;
    } catch (const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
