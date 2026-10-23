#include "T3BGEEffectColorScale.h"
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>

int main(int argc,char** argv){
    try{
        if(argc!=3)return 2;
        std::ifstream in(argv[1],std::ios::binary);
        if(!in)throw std::runtime_error("Color/scale input not readable");
        std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(in)),{});
        if(bytes.size()<12||bytes.size()>1024*1024||std::memcmp(bytes.data(),"T3BCS1\0\0",8))
            throw std::runtime_error("Wrong color/scale transport");
        std::size_t at=8;
        const auto word=[&](){
            if(bytes.size()-at<4)throw std::runtime_error("Truncated color/scale input");
            const auto* p=bytes.data()+at;at+=4;
            return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);
        };
        const auto number=[&](){auto raw=word();float f;std::memcpy(&f,&raw,4);return f;};
        const auto vector=[&](){std::array<float,4> v{};for(float& a:v)a=number();return v;};
        const auto count=word();if(!count||count>4096)throw std::runtime_error("Color/scale count bound");
        std::ofstream out(argv[2],std::ios::binary);
        for(std::uint32_t i=0;i<count;++i){
            const auto kind=word();const float t=number(),oldTime=number();
            T3BGE::EffectColorState state{vector(),vector(),vector()};
            const T3BGE::EffectColorKey previous{vector(),vector()},current{vector(),vector()};
            if(kind<3){
                if(kind==0)state=T3BGE::ChangeOriginalEffectColor(state,previous,current,t);
                else if(kind==1)state=T3BGE::WrapOriginalEffectColor(state,previous,current,t,oldTime);
                else state=T3BGE::EvaluateOriginalEffectColor(state,t);
            }else if(kind<5){
                T3BGE::EffectPercentScaleState scale{state.Color,state.Base};
                scale=kind==3?T3BGE::ChangeOriginalEffectPercentScale(scale,previous.Base,current.Base):T3BGE::ResetOriginalEffectPercentScale(scale);
                state={scale.Scale,scale.Percent,{0,0,0,0}};
            }else throw std::runtime_error("Unsupported color/scale operation");
            for(const auto& values:{state.Color,state.Base,state.Velocity})
                for(float value:values)out.write(reinterpret_cast<const char*>(&value),4);
        }
        if(at!=bytes.size())throw std::runtime_error("Trailing color/scale input");
        out.close();if(!out)throw std::runtime_error("Color/scale output failed");
        std::cout<<"{\"operations\":"<<count<<"}\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
