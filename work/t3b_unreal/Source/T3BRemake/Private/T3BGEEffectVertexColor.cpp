#include "T3BGEEffectVertexColor.h"
#include <cmath>
#include <cstring>
#include <stdexcept>

namespace {
void Check(bool v,const char* why){if(!v)throw std::runtime_error(why);}
float Mul(float a,float b){volatile float r=a*b;return r;}
float Sub(float a,float b){volatile float r=a-b;return r;}
void Validate(const T3BGE::EffectRGBA& v){for(float f:v)Check(std::isfinite(f),"Nonfinite effect render color");}
} // namespace

namespace T3BGE {
EffectRGBA ModulateOriginalEffectRGBA(const EffectRGBA& source,const EffectRGBA& parent){
    Validate(source);Validate(parent);EffectRGBA result{};
    for(unsigned k=0;k<4;++k){result[k]=Mul(source[k],parent[k]);}
    Validate(result);return result;
}
EffectRGBA ProcessOriginalEffectColorMode(const EffectRGBA& rgba,std::uint8_t mode){
    Validate(rgba);auto result=rgba;
    if(mode==6||mode==9||mode==10||mode==11||mode==12){
        const float alpha=Mul(rgba[3],1.0f/128.0f);
        const float factor=mode==6?Sub(1.0f,alpha):mode==10?Sub(2.0f,alpha):alpha;
        for(unsigned k=0;k<3;++k){
            float v=Mul(rgba[k],factor);Check(std::isfinite(v),"Effect mode overflow");
            if(mode==6){if(v<0.0f)v=0.0f;}
            else if(!(v<=255.0f))v=255.0f;
            result[k]=v;
        }
    }
    return result;
}
bool NeedsOriginalEffectColorUpdate(const EffectRGBA& previous,const EffectRGBA& current,
    std::uint32_t pending,std::uint32_t capacity){
    static_assert(sizeof(float)==4,"Original F32 color representation required");
    Check(pending<=capacity&&capacity<=8192,"Invalid source color cache bounds");
    return pending<capacity&&std::memcmp(previous.data(),current.data(),16)!=0;
}
std::vector<std::uint8_t> ModulateOriginalEffectVertexPalette(
    const std::vector<std::uint8_t>& source,const EffectRGBA& rgba){
    Validate(rgba);Check(!source.empty()&&source.size()%4==0&&source.size()<=4096*4,"Invalid vertex-color palette extent");
    EffectRGBA factors{};for(unsigned k=0;k<4;++k)factors[k]=Mul(rgba[k],1.0f/128.0f);
    std::vector<std::uint8_t> result(source.size());
    for(std::size_t i=0;i<source.size();++i){
        const float value=Mul(static_cast<float>(source[i]),factors[i%4]);
        Check(std::isfinite(value)&&double(value)>=-2147483648.0&&double(value)<2147483648.0,"Palette value outside original trunc domain");
        const auto integer=static_cast<std::int32_t>(value);
        // The original clamps only above255, then SB stores the low byte.
        result[i]=integer>=256?255:static_cast<std::uint8_t>(integer);
    }
    return result;
}
void PatchOriginalEffectVertexColors(std::uint32_t vt,std::vector<std::uint8_t>& vertices,
    const std::vector<std::uint32_t>& indices,const std::vector<std::uint8_t>& palette){
    Check(vt==0x11e||vt==0x11c,"Unsupported original color-patch vertex layout");
    const std::size_t stride=vt==0x11e?16:12,offset=vt==0x11e?4:0;
    Check(!indices.empty()&&indices.size()<=4096&&vertices.size()==indices.size()*stride,"Vertex-color patch extent differs");
    Check(!palette.empty()&&palette.size()%4==0&&palette.size()<=4096*4,"Invalid color-patch palette extent");
    for(std::size_t i=0;i<indices.size();++i){
        Check(indices[i]<palette.size()/4,"Vertex color index outside source palette");
        std::memcpy(vertices.data()+i*stride+offset,palette.data()+indices[i]*4,4);
    }
}
} // namespace T3BGE
