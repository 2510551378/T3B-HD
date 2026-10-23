#include "T3BGEEffectGeometry.h"
#include <cmath>
#include <cstring>
#include <stdexcept>

namespace {
void Check(bool ok,const char* why) { if (!ok) throw std::runtime_error(why); }
float F24(std::uint32_t payload) {
    Check(payload<=0xffffff,"Invalid GE effect F24 payload");
    const std::uint32_t bits=payload<<8; float value;
    std::memcpy(&value,&bits,4); Check(std::isfinite(value),"Nonfinite effect UV parameter");
    return value;
}
std::uint32_t U16(const std::vector<std::uint8_t>& raw,std::size_t at) {
    return std::uint32_t(raw[at]) | (std::uint32_t(raw[at+1])<<8);
}
float S16(const std::vector<std::uint8_t>& raw,std::size_t at) {
    const auto word=U16(raw,at);
    const int signedValue=word>=32768 ? static_cast<int>(word)-65536 : static_cast<int>(word);
    return static_cast<float>(signedValue)/32768.0f;
}
} // namespace

namespace T3BGE {
EffectGeometry DecodeOriginalEffectStrip(std::uint32_t vtype,std::uint32_t count,
    const std::vector<std::uint8_t>& sourceBytes,const Registers& r) {
    Check((vtype==0x102 || vtype==0x11e) && count>=3 && count<=4096,
          "Unsupported original effect strip layout/count");
    const std::size_t stride=vtype==0x102 ? 10 : 16;
    Check(sourceBytes.size()==count*stride,"Effect vertices extent differs");
    Check(r[0x12]==vtype && (r[4]&65535)==count && ((r[4]>>16)&7)==4,
          "Original effect registers/PRIM differ");
    Check(r[0x17]==0 && r[0x50]==1 && (r[0xc0]&3)==0,
          "Unsupported effect lighting/shading/UV generation");
    const float scale[2]={F24(r[0x48]),F24(r[0x49])};
    const float offset[2]={F24(r[0x4a]),F24(r[0x4b])};
    EffectGeometry out; out.vertices.resize(count);
    for (std::size_t i=0; i<count; ++i) {
        const auto at=i*stride;
        auto& v=out.vertices[i];
        for (unsigned k=0; k<2; ++k) {
            const float uv=static_cast<float>(U16(sourceBytes,at+2*k))/32768.0f;
            volatile float product=uv*scale[k];
            volatile float translated=product+offset[k];
            v.uv[k]=translated;
        }
        const auto positionAt=at+(vtype==0x102 ? 4 : 8);
        for (unsigned k=0; k<3; ++k) v.position[k]=S16(sourceBytes,positionAt+2*k);
        if (vtype==0x11e) {
            for (unsigned k=0; k<4; ++k) v.color[k]=sourceBytes[at+4+k];
        } else {
            for (unsigned k=0; k<3; ++k) v.color[k]=static_cast<std::uint8_t>(r[0x55]>>(k*8));
            v.color[3]=static_cast<std::uint8_t>(r[0x58]);
        }
    }
    out.triangleIndices.reserve((count-2)*3);
    for (std::uint32_t i=0; i+2<count; ++i) {
        out.triangleIndices.push_back(i+(i&1));
        out.triangleIndices.push_back(i+1-(i&1));
        out.triangleIndices.push_back(i+2);
    }
    return out;
}
} // namespace T3BGE
