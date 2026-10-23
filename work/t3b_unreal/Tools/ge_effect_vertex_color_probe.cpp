#include "T3BGEEffectVertexColor.h"
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>

int main(int argc,char** argv){
    try{
        if(argc!=3)return 2;
        std::ifstream in(argv[1],std::ios::binary);if(!in)throw std::runtime_error("Vertex-color input not readable");
        std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(in)),{});
        if(bytes.size()<12||bytes.size()>16*1024*1024||std::memcmp(bytes.data(),"T3BRC1\0\0",8))throw std::runtime_error("Wrong vertex-color transport");
        std::size_t at=8;
        const auto word=[&](){
            if(bytes.size()-at<4)throw std::runtime_error("Truncated vertex-color input");
            const auto* p=bytes.data()+at;at+=4;
            return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);
        };
        const auto color=[&](){T3BGE::EffectRGBA result{};for(float& f:result){auto w=word();std::memcpy(&f,&w,4);}return result;};
        const auto raw=[&](std::size_t size){
            if(size>bytes.size()-at)throw std::runtime_error("Truncated vertex-color payload");
            std::vector<std::uint8_t> result(bytes.begin()+at,bytes.begin()+at+size);at+=size;return result;
        };
        const auto count=word();if(!count||count>4096)throw std::runtime_error("Vertex-color operation count bound");
        std::ofstream out(argv[2],std::ios::binary);
        const auto writeWord=[&](std::uint32_t value){out.write(reinterpret_cast<const char*>(&value),4);};
        for(std::uint32_t k=0;k<count;++k){
            const auto mode=word();if(mode>255)throw std::runtime_error("Source color mode outside byte domain");
            const auto source=color(),parent=color(),previous=color();const auto pending=word(),capacity=word();
            const auto paletteBytes=word();if(!paletteBytes||paletteBytes%4||paletteBytes>4096*4)throw std::runtime_error("Source palette bound");
            const auto palette=raw(paletteBytes),previousPalette=raw(paletteBytes);
            const auto combined=T3BGE::ModulateOriginalEffectRGBA(source,parent);
            const auto processed=T3BGE::ProcessOriginalEffectColorMode(combined,static_cast<std::uint8_t>(mode));
            const bool update=T3BGE::NeedsOriginalEffectColorUpdate(previous,processed,pending,capacity);
            const auto result=update?T3BGE::ModulateOriginalEffectVertexPalette(palette,processed):previousPalette;
            for(const auto& values:{combined,processed})for(float f:values)out.write(reinterpret_cast<const char*>(&f),4);
            writeWord(update?1:0);writeWord(paletteBytes);out.write(reinterpret_cast<const char*>(result.data()),result.size());
            const auto draws=word();if(draws>64)throw std::runtime_error("Vertex-color draw count bound");writeWord(draws);
            for(std::uint32_t j=0;j<draws;++j){
                const auto vt=word(),n=word(),size=word();if(!n||n>4096||size>4096*16)throw std::runtime_error("Vertex-color geometry bound");
                std::vector<std::uint32_t> indices(n);for(auto& index:indices)index=word();auto vertices=raw(size);
                if(update)T3BGE::PatchOriginalEffectVertexColors(vt,vertices,indices,result);
                writeWord(size);out.write(reinterpret_cast<const char*>(vertices.data()),vertices.size());
            }
        }
        if(at!=bytes.size())throw std::runtime_error("Trailing vertex-color bytes");
        out.close();if(!out)throw std::runtime_error("Vertex-color output failed");
        std::cout<<"{\"operations\":"<<count<<"}\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
