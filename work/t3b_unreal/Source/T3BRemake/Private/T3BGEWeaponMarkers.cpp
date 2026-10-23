#include "T3BGEWeaponMarkers.h"
#include <cmath>
#include <cstring>
#include <stdexcept>

namespace {
using M = T3BGE::MarkerMatrix;
void Check(bool ok, const char* why) { if (!ok) throw std::runtime_error(why); }
M Multiply(const M& a, const M& b) {
    M out{};
    for (unsigned c=0; c<4; ++c) for (unsigned r=0; r<4; ++r)
        for (unsigned k=0; k<4; ++k) out[c*4+r] += a[k*4+r]*b[c*4+k];
    return out;
}
M Expand(const T3BGE::Matrix43& original) {
    M result{}; result[15]=1;
    for (unsigned c=0; c<4; ++c) for (unsigned r=0; r<3; ++r)
        result[c*4+r]=double(original[c*3+r]);
    return result;
}
void CheckAffine(const M& m) {
    for (auto v:m) Check(std::isfinite(v), "Nonfinite original marker matrix");
    Check(m[3]==0 && m[7]==0 && m[11]==0 && m[15]==1, "Nonaffine original marker matrix");
}
} // namespace

namespace T3BGE {
WeaponMarkerDefinitions LoadWeaponMarkers(const std::vector<std::uint8_t>& bytes) {
    Check(bytes.size()==208, "Wrong original marker definition extent");
    Check(std::memcmp(bytes.data(),"T3BWMK1\0",8)==0, "Wrong source marker magic");
    std::size_t at=8;
    const auto word=[&]() {
        const auto* p=bytes.data()+at; at+=4;
        return std::uint32_t(p[0]) | (std::uint32_t(p[1])<<8) |
            (std::uint32_t(p[2])<<16) | (std::uint32_t(p[3])<<24);
    };
    const auto number=[&]() { auto u=word(); float f; std::memcpy(&f,&u,4); return f; };
    Check(word()==2, "Expected original source indices1/2");
    WeaponMarkerDefinitions result; result.originalVertexWeight=number();
    Check(result.originalVertexWeight==32767.0f/32768.0f, "Wrong original rifle weight");
    M root{};
    for (auto& v:root) v=number();
    CheckAffine(root);
    for (unsigned c=0; c<4; ++c) for (unsigned r=0; r<3; ++r) {
        const float value=static_cast<float>(root[c*4+r]);
        std::uint32_t bits; std::memcpy(&bits,&value,4); bits &= 0xffffff00u;
        std::memcpy(&result.expectedGEroot[c*3+r],&bits,4);
    }
    for (auto& local:result.originalLocalMatrices) {
        for (auto& v:local) v=number();
        CheckAffine(local);
    }
    return result;
}
std::array<float,16> ComposeOriginalWeaponMarker(
    const WeaponMarkerDefinitions& definitions, unsigned sourceIndex,
    const std::array<float,16>& fullOriginalWorld) {
    Check(sourceIndex>=1 && sourceIndex<=2, "Original weapon marker index outside1/2");
    M checkedWorld{};
    for (unsigned i=0; i<16; ++i) checkedWorld[i]=fullOriginalWorld[i];
    CheckAffine(checkedWorld);
    const auto& local=definitions.originalLocalMatrices[sourceIndex-1];
    std::array<float,16> result{};
    for (unsigned c=0; c<4; ++c) for (unsigned r=0; r<4; ++r) {
        float sum=0;
        for (unsigned k=0; k<4; ++k) {
            // Force each original F32 rounding even with a host FMA optimizer.
            volatile float term=fullOriginalWorld[k*4+r]*static_cast<float>(local[c*4+k]);
            volatile float next=sum+term;
            sum=next;
        }
        result[c*4+r]=sum;
    }
    return result;
}
std::array<WeaponMarkerPose,2> EvaluateWeaponMarkers(
    const WeaponMarkerDefinitions& definitions, const SeriesDraw& rifle) {
    Check(rifle.registers[0x12]==0x522 && rifle.weightCount==1 && rifle.vertices.size()==243,
          "Marker replay requires the recovered one-slot rifle draw");
    for (const auto& v:rifle.vertices)
        Check(v.weights[0]==definitions.originalVertexWeight, "Rifle/source marker weight mismatch");
    Check(rifle.bones[0]==definitions.expectedGEroot, "Unexpected rifle root BONE bind");
    const M world=Expand(rifle.world);
    std::array<WeaponMarkerPose,2> result{};
    for (unsigned i=0; i<2; ++i) {
        auto& p=result[i]; p.world=Multiply(world,definitions.originalLocalMatrices[i]);
        CheckAffine(p.world);
        double length=0;
        for (unsigned k=0; k<3; ++k) length+=p.world[8+k]*p.world[8+k];
        length=std::sqrt(length); Check(std::isfinite(length) && length>0, "Degenerate source marker direction");
        for (unsigned k=0; k<3; ++k) p.unitPlusZ[k]=p.world[8+k]/length;
    }
    return result;
}
} // namespace T3BGE
