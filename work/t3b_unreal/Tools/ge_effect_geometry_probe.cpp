// Calls the production source effect decoder. T3BFXS1 is our bounded transport.
#include "T3BGEEffectGeometry.h"
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>

int main(int argc,char** argv) {
    try {
        if (argc!=3) return 2;
        std::ifstream in(argv[1],std::ios::binary);
        if (!in) throw std::runtime_error("Effect input not readable");
        std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(in)),{});
        if (bytes.size()<12 || bytes.size()>16*1024*1024 || std::memcmp(bytes.data(),"T3BFXS1\0",8))
            throw std::runtime_error("Invalid effect transport");
        std::size_t at=8;
        const auto word=[&]() {
            if (bytes.size()-at<4) throw std::runtime_error("Truncated effect transport");
            const auto* p=bytes.data()+at; at+=4;
            return std::uint32_t(p[0]) | (std::uint32_t(p[1])<<8) |
                (std::uint32_t(p[2])<<16) | (std::uint32_t(p[3])<<24);
        };
        const auto count=word(); if (!count || count>4096) throw std::runtime_error("Effect draw count bound");
        std::ofstream out(argv[2],std::ios::binary);
        const auto writeWord=[&](std::uint32_t v){out.write(reinterpret_cast<const char*>(&v),4);};
        std::size_t vertices=0,triangles=0;
        for (std::uint32_t i=0; i<count; ++i) {
            T3BGE::Registers r{}; for (auto& v:r) v=word();
            const auto vt=word(),n=word(),size=word();
            if (size>bytes.size()-at) throw std::runtime_error("Truncated original effect vertices");
            std::vector<std::uint8_t> raw(bytes.begin()+at,bytes.begin()+at+size); at+=size;
            const auto mesh=T3BGE::DecodeOriginalEffectStrip(vt,n,raw,r);
            writeWord(static_cast<std::uint32_t>(mesh.vertices.size()));
            writeWord(static_cast<std::uint32_t>(mesh.triangleIndices.size()));
            for (const auto& v:mesh.vertices) {
                out.write(reinterpret_cast<const char*>(v.position.data()),12);
                out.write(reinterpret_cast<const char*>(v.uv.data()),8);
                out.write(reinterpret_cast<const char*>(v.color.data()),4);
            }
            for (auto v:mesh.triangleIndices) writeWord(v);
            vertices+=mesh.vertices.size(); triangles+=mesh.triangleIndices.size()/3;
        }
        if (at!=bytes.size()) throw std::runtime_error("Trailing effect transport bytes");
        out.close(); if (!out) throw std::runtime_error("Effect output failed");
        std::cout<<"{\"draws\":"<<count<<",\"vertices\":"<<vertices<<",\"triangles\":"<<triangles<<"}\n";
        return 0;
    } catch (const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
