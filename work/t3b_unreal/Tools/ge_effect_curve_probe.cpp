#include "T3BGEEffectCurve.h"
#include <cstdint>
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
        if(!in)throw std::runtime_error("Curve input not readable");
        std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(in)),{});
        if(bytes.size()<12||bytes.size()>1024*1024||std::memcmp(bytes.data(),"T3BCV1\0\0",8))
            throw std::runtime_error("Wrong curve transport");
        std::size_t at=8;
        const auto word=[&]() {
            if(bytes.size()-at<4)throw std::runtime_error("Truncated curve operation");
            const auto* p=bytes.data()+at;at+=4;
            return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);
        };
        const auto number=[&]() {auto b=word();float v;std::memcpy(&v,&b,4);return v;};
        const auto curve=[&]() {
            T3BGE::EffectCurve2D v{};
            for(float& a:v.Position)a=number();
            for(float& a:v.Velocity)a=number();
            for(float& a:v.Acceleration)a=number();
            return v;
        };
        const auto count=word();if(!count||count>4096)throw std::runtime_error("Curve count bound");
        std::ofstream out(argv[2],std::ios::binary);
        for(std::uint32_t k=0;k<count;++k) {
            const auto kind=word();const float t=number(),previousTime=number();
            const auto state=curve(),previous=curve(),current=curve();T3BGE::EffectCurve2D result{};
            if(kind==0)result=T3BGE::ChangeOriginalEffectCurve(state,previous,current,t);
            else if(kind==1)result=T3BGE::WrapOriginalEffectCurve(state,previous,current,t,previousTime);
            else throw std::runtime_error("Unsupported curve operation");
            for(float a:result.Position)out.write(reinterpret_cast<const char*>(&a),4);
            for(float a:result.Velocity)out.write(reinterpret_cast<const char*>(&a),4);
            for(float a:result.Acceleration)out.write(reinterpret_cast<const char*>(&a),4);
        }
        if(at!=bytes.size())throw std::runtime_error("Trailing curve bytes");
        out.close();if(!out)throw std::runtime_error("Curve output failed");
        std::cout<<"{\"operations\":"<<count<<"}\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
