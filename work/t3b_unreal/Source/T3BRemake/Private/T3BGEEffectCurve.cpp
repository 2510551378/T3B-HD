#include "T3BGEEffectCurve.h"
#include <cmath>
#include <cstdint>
#include <stdexcept>

namespace {
float Add(float a,float b) { volatile float v=a+b;return v; }
float Sub(float a,float b) { volatile float v=a-b;return v; }
float Mul(float a,float b) { volatile float v=a*b;return v; }
float Div(float a,float b) { volatile float v=a/b;return v; }
void Finite(float v) { if(!std::isfinite(v))throw std::runtime_error("Nonfinite effect curve"); }
void Validate(const T3BGE::EffectCurve2D& v) {
    for(int k=0;k<2;++k){Finite(v.Position[k]);Finite(v.Velocity[k]);Finite(v.Acceleration[k]);}
}
float Position(float p,float v,float a,float t,float tt) {
    return Add(Add(Mul(Mul(a,0.5f),tt),Mul(v,t)),p);
}
float NormalizeOriginal(float value) {
    if(value<0.0f||!(value<4096.0f)) {
        const float shifted=Add(value,4096.0f);
        const float scaled=Mul(shifted,1.0f/4096.0f);
        if(!std::isfinite(scaled)||double(scaled)<-2147483648.0||double(scaled)>=2147483648.0)
            throw std::runtime_error("Effect curve outside original trunc domain");
        const auto integer=static_cast<std::int32_t>(scaled);
        value=Sub(shifted,Mul(static_cast<float>(integer),4096.0f));
    }
    return value;
}
} // namespace

namespace T3BGE {
EffectCurve2D ChangeOriginalEffectCurve(const EffectCurve2D& state,
    const EffectCurve2D& previous,const EffectCurve2D& current,float t) {
    Validate(state);Validate(previous);Validate(current);Finite(t);
    const float tt=Mul(t,t);EffectCurve2D result{};
    for(int k=0;k<2;++k) {
        const float oldPosition=Position(previous.Position[k],previous.Velocity[k],previous.Acceleration[k],t,tt);
        const float statePosition=Position(state.Position[k],state.Velocity[k],state.Acceleration[k],t,tt);
        result.Position[k]=Add(current.Position[k],Sub(statePosition,oldPosition));
        const float oldVelocity=Add(Mul(previous.Acceleration[k],t),previous.Velocity[k]);
        const float stateVelocity=Add(Mul(state.Acceleration[k],t),state.Velocity[k]);
        result.Velocity[k]=Add(current.Velocity[k],Sub(stateVelocity,oldVelocity));
        result.Acceleration[k]=Add(current.Acceleration[k],Sub(state.Acceleration[k],previous.Acceleration[k]));
    }
    Validate(result);return result;
}

EffectCurve2D WrapOriginalEffectCurve(const EffectCurve2D& state,
    const EffectCurve2D& previous,const EffectCurve2D& current,float t,float previousTime) {
    Validate(state);Validate(previous);Validate(current);Finite(t);Finite(previousTime);
    const float oldTT=Mul(previousTime,previousTime),tt=Mul(t,t);EffectCurve2D result{};
    for(int k=0;k<2;++k) {
        const float stateVelocity=Add(Mul(state.Acceleration[k],previousTime),state.Velocity[k]);
        const float oldVelocity=Add(Mul(previous.Acceleration[k],previousTime),previous.Velocity[k]);
        result.Velocity[k]=Add(current.Velocity[k],Sub(stateVelocity,oldVelocity));
        result.Acceleration[k]=Add(current.Acceleration[k],Sub(state.Acceleration[k],previous.Acceleration[k]));
        const float accumulated=Position(state.Position[k],state.Velocity[k],state.Acceleration[k],previousTime,oldTT);
        const float restart=Add(Mul(Mul(result.Acceleration[k],0.5f),tt),Mul(result.Velocity[k],t));
        result.Position[k]=NormalizeOriginal(Sub(accumulated,restart));
    }
    Validate(result);return result;
}

std::array<float,2> EvaluateOriginalEffectCurve(const EffectCurve2D& state,float t) {
    Validate(state);Finite(t);const float tt=Mul(t,t);std::array<float,2> result{};
    for(int k=0;k<2;++k) {
        result[k]=Position(state.Position[k],state.Velocity[k],state.Acceleration[k],t,tt);
        Finite(result[k]);
    }
    return result;
}

std::array<float,2> BindOriginalEffectUV(const std::array<float,2>& pixelOffset,
    std::int32_t width,std::int32_t height,const std::array<float,2>& groupOffset) {
    if(width<=0||height<=0)throw std::runtime_error("Invalid original effect texture dimensions");
    const float dimensions[2]={static_cast<float>(width),static_cast<float>(height)};
    std::array<float,2> result{};
    for(int k=0;k<2;++k) {
        float v=pixelOffset[k];Finite(v);Finite(groupOffset[k]);unsigned iterations=0;
        while(v<0.0f||!(v<=dimensions[k])) {
            if(++iterations>65536)throw std::runtime_error("Original UV normalization iteration bound");
            const float next=v<0.0f?Add(v,dimensions[k]):Sub(v,dimensions[k]);
            if(next==v)throw std::runtime_error("Original UV normalization made no progress");
            v=next;
        }
        result[k]=Add(Div(v,dimensions[k]),groupOffset[k]);Finite(result[k]);
    }
    return result;
}
} // namespace T3BGE
