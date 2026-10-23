#include "T3BGEEffectCurve.h"
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>

int main(int argc,char** argv) {
    try {
        if(argc!=3)return 2;
        std::ifstream in(argv[1],std::ios::binary);
        if(!in)throw std::runtime_error("UV input not readable");
        std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(in)),{});
        if(bytes.size()<12||bytes.size()>1024*1024||std::memcmp(bytes.data(),"T3BUV1\0\0",8))
            throw std::runtime_error("Wrong effect UV transport");
        std::size_t at=8;
        const auto word=[&]() {
            if(bytes.size()-at<4)throw std::runtime_error("Truncated effect UV input");
            const auto* p=bytes.data()+at;at+=4;
            return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);
        };
        const auto number=[&]() {auto b=word();float v;std::memcpy(&v,&b,4);return v;};
        const auto count=word();if(!count||count>4096)throw std::runtime_error("UV operation count bound");
        std::ofstream out(argv[2],std::ios::binary);
        for(std::uint32_t k=0;k<count;++k) {
            const float t=number();T3BGE::EffectCurve2D state{};
            for(float& v:state.Position)v=number();
            for(float& v:state.Velocity)v=number();
            for(float& v:state.Acceleration)v=number();
            const auto width=word(),height=word();
            if(width>2147483647||height>2147483647)throw std::runtime_error("UV dimensions outside signed domain");
            const float gx=number(),gy=number();
            const auto evaluated=T3BGE::EvaluateOriginalEffectCurve(state,t);
            const auto normalized=T3BGE::BindOriginalEffectUV(evaluated,static_cast<std::int32_t>(width),static_cast<std::int32_t>(height),{gx,gy});
            for(float v:evaluated)out.write(reinterpret_cast<const char*>(&v),4);
            for(float v:normalized)out.write(reinterpret_cast<const char*>(&v),4);
            for(unsigned i=0;i<2;++i) {
                std::uint32_t raw;std::memcpy(&raw,&normalized[i],4);
                const auto command=((0x4au+i)<<24)|(raw>>8);
                out.write(reinterpret_cast<const char*>(&command),4);
            }
        }
        if(at!=bytes.size())throw std::runtime_error("Trailing effect UV bytes");
        out.close();if(!out)throw std::runtime_error("UV output failed");
        std::cout<<"{\"operations\":"<<count<<"}\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
