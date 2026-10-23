#include "T3BGEEffectModifiers.h"
#include <cmath>
#include <cstring>
#include <stdexcept>
namespace {
void Check(bool v,const char* message){if(!v)throw std::runtime_error(message);}
float F32(float v){volatile float rounded=v;return rounded;}
float Add(float a,float b){return F32(a+b);}
float Sub(float a,float b){return F32(a-b);}
float Mul(float a,float b){return F32(a*b);}
void Validate(const T3BGE::EffectModifierWindow& target,const T3BGE::EffectModifierChannels& channels){
    for(float x:target){Check(std::isfinite(x),"Nonfinite modifier target");}
    for(const auto& c:channels){if(c.enabled){for(float x:c.amplitude){Check(std::isfinite(x),"Nonfinite modifier amplitude");}}}
}
float ScalarOffset(std::uint32_t random,float amplitude,std::uint8_t mode){
    const float half=(mode==1||mode==2)?Mul(amplitude,0.5f):amplitude;
    float value=F32(static_cast<float>(random));
    value=Mul(value,0x1p-31f);value=Mul(value,2.f);value=Mul(value,half);value=Sub(value,half);
    if(mode==1)value=Add(value,half);
    if(mode==2)value=Sub(value,half);
    return value;
}
}
namespace T3BGE {
std::uint32_t NextOriginalEffectRandom(std::uint32_t& seed){seed=seed*1103515245u+12345u;return seed&0x7fffffffu;}
void ApplyOriginalType23Modifiers(EffectModifierWindow& target,const EffectModifierChannels& channels,
    const std::array<std::array<float,3>,3>& observed,const std::array<float,3>& center){
    Validate(target,channels);auto result=target;
    for(std::size_t k=0;k<3;++k){
        const auto& c=channels[k];if(!c.enabled)continue;
        for(std::size_t axis=0;axis<3;++axis){
            Check(std::isfinite(center[axis])&&observed[k][axis]>=2.f&&observed[k][axis]<4.f,"Missing original VRNDF2 input");
            const float half=(c.mode==1||c.mode==2)?Mul(c.amplitude[axis],0.5f):c.amplitude[axis];
            float delta=Mul(Sub(observed[k][axis],center[axis]),half);
            // Both original type23 mode1 and mode2 branches use vsub here.
            // Do not copy the scalar type24 mode1 (positive offset) behavior.
            if(c.mode==1||c.mode==2)delta=Sub(delta,half);
            result[(k+1)*4+axis]=Add(result[(k+1)*4+axis],delta);
            Check(std::isfinite(result[(k+1)*4+axis]),"Modifier result overflow");
        }
        result[(k+1)*4+3]=1.f;
    }
    target=result;
}
std::uint32_t ApplyOriginalType23ModifiersFromRCX(EffectModifierWindow& target,const EffectModifierChannels& channels,
    VFPURCXState& rcx,const std::array<float,3>& vectorCenter){
    std::array<std::array<float,3>,3> observed{};std::uint32_t generated=0;
    for(std::size_t channel=0;channel<3;++channel){
        if(!channels[channel].enabled)continue;
        for(std::size_t axis=0;axis<3;++axis){
            std::uint32_t bits=GenerateOriginalVRNDF2(rcx);float value;std::memcpy(&value,&bits,4);observed[channel][axis]=value;++generated;
        }
    }
    ApplyOriginalType23Modifiers(target,channels,observed,vectorCenter);return generated;
}
void ApplyOriginalType24Modifiers(EffectModifierWindow& target,const EffectModifierChannels& channels,bool independent,std::uint32_t& seed){
    Validate(target,channels);auto result=target;auto nextSeed=seed;
    for(std::size_t k=0;k<3;++k){
        const auto& c=channels[k];if(!c.enabled)continue;
        const auto first=NextOriginalEffectRandom(nextSeed);
        const float shared=ScalarOffset(first,c.amplitude[0],c.mode);
        for(std::size_t axis=0;axis<3;++axis){
            const float delta=axis==0||!independent?shared:ScalarOffset(NextOriginalEffectRandom(nextSeed),c.amplitude[axis],c.mode);
            result[(k+1)*4+axis]=Add(result[(k+1)*4+axis],delta);
            Check(std::isfinite(result[(k+1)*4+axis]),"Modifier result overflow");
        }
        result[(k+1)*4+3]=1.f;
        if(k==0){for(std::size_t axis=0;axis<3;++axis){result[axis]=Mul(result[4+axis],0.01f);}result[3]=0.f;}
    }
    target=result;seed=nextSeed;
}
} // namespace T3BGE
