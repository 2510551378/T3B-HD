#include "T3BGEEffectGeometry.h"
#include "T3BGEEffectVertexColor.h"
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>

int main(int argc,char** argv){
    try{
        if(argc!=3)return 2;
        std::ifstream in(argv[1],std::ios::binary);if(!in)throw std::runtime_error("Tinted strip input not readable");
        std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(in)),{});
        if(bytes.size()<12||bytes.size()>16*1024*1024||std::memcmp(bytes.data(),"T3BPC1\0\0",8))throw std::runtime_error("Wrong tinted strip transport");
        std::size_t at=8;
        const auto word=[&](){
            if(bytes.size()-at<4)throw std::runtime_error("Truncated tinted strip input");
            const auto* p=bytes.data()+at;at+=4;
            return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);
        };
        const auto color=[&](){T3BGE::EffectRGBA c{};for(float& f:c){auto w=word();std::memcpy(&f,&w,4);}return c;};
        const auto raw=[&](std::size_t n){
            if(n>bytes.size()-at)throw std::runtime_error("Truncated tinted strip payload");
            std::vector<std::uint8_t> v(bytes.begin()+at,bytes.begin()+at+n);at+=n;return v;
        };
        const auto count=word();if(!count||count>4096)throw std::runtime_error("Tinted strip count bound");
        std::ofstream out(argv[2],std::ios::binary);
        const auto writeWord=[&](std::uint32_t v){out.write(reinterpret_cast<const char*>(&v),4);};
        std::size_t totalVertices=0;
        for(std::uint32_t i=0;i<count;++i){
            T3BGE::Registers r{};for(auto& value:r)value=word();
            const auto vt=word(),n=word(),mode=word();if(!n||n>4096||mode>255)throw std::runtime_error("Tinted strip operand bound");
            const auto source=color(),parent=color();const auto paletteSize=word();
            if(!paletteSize||paletteSize>4096*4)throw std::runtime_error("Tinted strip palette bound");
            const auto palette=raw(paletteSize);std::vector<std::uint32_t> indices(n);for(auto& v:indices)v=word();
            const auto size=word();if(size>4096*16)throw std::runtime_error("Tinted strip geometry bound");auto vertices=raw(size);
            const auto rgba=T3BGE::ProcessOriginalEffectColorMode(T3BGE::ModulateOriginalEffectRGBA(source,parent),static_cast<std::uint8_t>(mode));
            const auto converted=T3BGE::ModulateOriginalEffectVertexPalette(palette,rgba);
            T3BGE::PatchOriginalEffectVertexColors(vt,vertices,indices,converted);
            const auto mesh=T3BGE::DecodeOriginalEffectStrip(vt,n,vertices,r);
            writeWord(static_cast<std::uint32_t>(converted.size()));out.write(reinterpret_cast<const char*>(converted.data()),converted.size());
            writeWord(static_cast<std::uint32_t>(vertices.size()));out.write(reinterpret_cast<const char*>(vertices.data()),vertices.size());
            writeWord(static_cast<std::uint32_t>(mesh.vertices.size()));writeWord(static_cast<std::uint32_t>(mesh.triangleIndices.size()));
            for(const auto& v:mesh.vertices){
                out.write(reinterpret_cast<const char*>(v.position.data()),12);out.write(reinterpret_cast<const char*>(v.uv.data()),8);out.write(reinterpret_cast<const char*>(v.color.data()),4);
            }
            for(auto index:mesh.triangleIndices)writeWord(index);
            totalVertices+=mesh.vertices.size();
        }
        if(at!=bytes.size())throw std::runtime_error("Trailing tinted strip input");
        out.close();if(!out)throw std::runtime_error("Tinted strip output failed");
        std::cout<<"{\"draws\":"<<count<<",\"vertices\":"<<totalVertices<<"}\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
