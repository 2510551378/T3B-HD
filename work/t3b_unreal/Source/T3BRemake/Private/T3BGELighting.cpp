#include "T3BGELighting.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <stdexcept>
#include <smmintrin.h>

namespace T3BGE {
namespace {
float F24(std::uint32_t payload) {
    const std::uint32_t bits = (payload & 0xFFFFFFU) << 8;
    float value; std::memcpy(&value,&bits,sizeof(value));
    if (!std::isfinite(value)) throw std::runtime_error("Nonfinite GE light parameter");
    return value;
}
void Finite(const V3& v) {
    for (float f : v) if (!std::isfinite(f)) throw std::runtime_error("Nonfinite GE vertex");
}
float Dot(const V3& a,const V3& b) { return (a[0]*b[0]+a[1]*b[1])+a[2]*b[2]; }
float Normalize(V3& v) {
    const float d = std::sqrt(v[0]*v[0]+(v[1]*v[1]+v[2]*v[2]));
    if (d == 0) v[2] = 1;
    else for (float& f : v) f /= d;
    return d;
}
V3 HalfVector(const V3& l) {
    // Pinned PPSSPP x64 SSE4 software-lighting reference uses approximate RSQRT
    // for the specular half vector, unlike its full-precision NormalizeOr001().
    const __m128 v = _mm_set_ps(0, l[2]+1.0f, l[1], l[0]);
    const __m128 scale = _mm_rsqrt_ps(_mm_dp_ps(v,v,0x77));
    const __m128 n = _mm_mul_ps(v,scale);
    alignas(16) float values[4]; _mm_store_ps(values,n);
    V3 result{values[0],values[1],values[2]};
    if (std::isnan(result[0])) return {0,0,1};
    return result;
}
V3 Mul43(const Matrix43& m,const V3& p,bool point) {
    V3 out{};
    for (unsigned row=0;row<3;++row)
        out[row] = (m[row]*p[0]+m[row+3]*p[1])+
                   (point ? m[row+6]*p[2]+m[row+9] : m[row+6]*p[2]);
    return out;
}
using I4 = std::array<int,4>;
I4 Expand(std::uint32_t color) {
    I4 result{};
    for (unsigned c=0;c<4;++c) result[c] = 2*int((color>>(c*8))&255)+1;
    return result;
}
I4 RGB(std::uint32_t color) {
    I4 result{};
    for (unsigned c=0;c<3;++c) result[c] = int((color>>(c*8))&255);
    return result;
}
bool Nonzero(const I4& color) { return color[0]>1 || color[1]>1 || color[2]>1; }
void Add(I4& sum,const I4& a,const I4& b,float contribution) {
    const int scale = std::min(512,int(std::ceil(contribution*512.0f+1.0f)));
    for (unsigned c=0;c<4;++c) sum[c] += (a[c]*b[c]*scale) >> 19;
}
}

Transformed Transform(const Vertex& v,const std::array<Matrix43,8>& bones,
                      unsigned count,const Matrix43& world,bool reverse) {
    if (count<1 || count>8) throw std::runtime_error("Unsupported GE skin weight count");
    Finite(v.position); Finite(v.normal);
    Matrix43 skin{};
    for (unsigned j=0;j<count;++j) {
        if (!std::isfinite(v.weights[j]) || v.weights[j]<0) throw std::runtime_error("Invalid GE skin weight");
        if (v.weights[j]!=0)
            for (unsigned k=0;k<12;++k) skin[k] += v.weights[j]*bones[j][k];
    }
    const V3 localPosition = Mul43(skin,v.position,true);
    V3 normal = Mul43(skin,v.normal,false);
    if (reverse) for (float& f:normal) f = -f;
    Transformed out{Mul43(world,localPosition,true),Mul43(world,normal,false)};
    Normalize(out.unitWorldNormal); Finite(out.worldPosition); Finite(out.unitWorldNormal);
    return out;
}

Colors Light(const Registers& r,const V3& position,const V3& normal) {
    Finite(position); Finite(normal);
    if (((r[0x12]>>2)&7) != 0 || (r[0x12]&(1U<<23)))
        throw std::runtime_error("Input COLOR_0/throughmode outside observed Aya kernel");
    if (!(r[0x17]&1)) throw std::runtime_error("Lighting-disabled path not in this kernel");
    const auto mac = Expand((r[0x55]&0xFFFFFFU)|((r[0x58]&255)<<24));
    const auto mdc = Expand(r[0x56]&0xFFFFFFU), msc = Expand(r[0x57]&0xFFFFFFU);
    const auto ambient = Expand((r[0x5C]&0xFFFFFFU)|((r[0x5D]&255)<<24));
    auto primary = RGB(r[0x54]); I4 secondary{};
    for (unsigned c=0;c<4;++c) primary[c] += (mac[c]*ambient[c])>>10;
    const float power = std::max(0.0f,F24(r[0x5B]));
    for (unsigned i=0;i<4;++i) {
        if (!(r[0x18+i]&1)) continue;
        const unsigned type = (r[0x5F+i]>>8)&3, computation = r[0x5F+i]&3;
        if (type>1 || computation>2) throw std::runtime_error("Unobserved GE light type/computation");
        V3 l{F24(r[0x63+i*3]),F24(r[0x64+i*3]),F24(r[0x65+i*3])};
        float attenuation = 1;
        if (type==0) Normalize(l);
        else {
            for (unsigned c=0;c<3;++c) l[c] -= position[c];
            const float d = Normalize(l);
            const V3 coefficients{F24(r[0x7B+i*3]),F24(r[0x7C+i*3]),F24(r[0x7D+i*3])};
            attenuation = 1.0f / Dot(coefficients,{1,d,d*d});
            if (!(attenuation>0)) attenuation=0;
            else if (attenuation>1) attenuation=1;
        }
        const auto la=Expand(r[0x8F+i*3]&0xFFFFFFU);
        const auto ld=Expand(r[0x90+i*3]&0xFFFFFFU), ls=Expand(r[0x91+i*3]&0xFFFFFFU);
        if (Nonzero(la) && Nonzero(mac)) Add(primary,la,mac,attenuation);
        float diffuse = Dot(l,normal);
        if (computation==2) diffuse = power<=0 ? 1.0f : diffuse>0 ? std::pow(diffuse,power) : diffuse;
        if (Nonzero(ld) && Nonzero(mdc) && diffuse>0) Add(primary,ld,mdc,attenuation*diffuse);
        if (computation==1 && Nonzero(ls) && Nonzero(msc) && diffuse>=0) {
            const float value = Dot(HalfVector(l),normal);
            const float specular = power<=0 ? 1.0f : value>0 ? std::pow(value,power) : value;
            if (specular>0) Add(secondary,ls,msc,attenuation*specular);
        }
    }
    Colors result{};
    for (unsigned c=0;c<4;++c) {
        const int total = primary[c] + ((r[0x5E]&1) ? 0 : secondary[c]);
        result.primary[c] = static_cast<std::uint8_t>(std::clamp(total,0,255));
        if (c<3) result.secondary[c] = static_cast<std::uint8_t>((r[0x5E]&1) ? std::clamp(secondary[c],0,255) : 0);
    }
    return result;
}
}
