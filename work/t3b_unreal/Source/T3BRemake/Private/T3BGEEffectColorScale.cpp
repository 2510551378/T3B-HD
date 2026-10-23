#include "T3BGEEffectColorScale.h"
#include <cmath>
#include <stdexcept>

namespace {
float Add(float a,float b){volatile float r=a+b;return r;}
float Sub(float a,float b){volatile float r=a-b;return r;}
float Mul(float a,float b){volatile float r=a*b;return r;}
void Finite(float v){if(!std::isfinite(v))throw std::runtime_error("Nonfinite source color/scale");}
void Validate(const std::array<float,4>& v){for(float f:v)Finite(f);}
void Validate(const T3BGE::EffectColorState& s){Validate(s.Color);Validate(s.Base);Validate(s.Velocity);}
void Validate(const T3BGE::EffectColorKey& s){Validate(s.Base);Validate(s.Velocity);}
} // namespace

namespace T3BGE {
EffectColorState ChangeOriginalEffectColor(const EffectColorState& s,
    const EffectColorKey& previous,const EffectColorKey& current,float t){
    Validate(s);Validate(previous);Validate(current);Finite(t);auto result=s;
    for(unsigned k=0;k<4;++k){
        const float oldValue=Add(Mul(previous.Velocity[k],t),previous.Base[k]);
        const float value=Add(Mul(s.Velocity[k],t),s.Base[k]);
        result.Base[k]=Add(Sub(value,oldValue),current.Base[k]);
        result.Velocity[k]=Add(Sub(s.Velocity[k],previous.Velocity[k]),current.Velocity[k]);
        result.Color[k]=result.Base[k];
    }
    Validate(result);return result;
}
EffectColorState EvaluateOriginalEffectColor(const EffectColorState& s,float t){
    Validate(s);Finite(t);auto result=s;
    for(unsigned k=0;k<4;++k){
        const float value=Add(s.Base[k],Mul(s.Velocity[k],t));Finite(value);
        // VFPU finite vmax/min select the T operand on equal values, including
        // the +0 clamp bound. std::clamp would preserve an input -0 instead.
        const float lower=value>0.0f?value:0.0f;
        result.Color[k]=lower<255.0f?lower:255.0f;
    }
    return result;
}
EffectColorState WrapOriginalEffectColor(const EffectColorState& s,
    const EffectColorKey& previous,const EffectColorKey& current,float t,float oldTime){
    Validate(s);Validate(previous);Validate(current);Finite(t);Finite(oldTime);auto result=s;
    for(unsigned k=0;k<4;++k){
        const float accumulated=Add(Mul(s.Velocity[k],oldTime),s.Base[k]);
        result.Velocity[k]=Add(current.Velocity[k],Sub(s.Velocity[k],previous.Velocity[k]));
        result.Base[k]=Sub(accumulated,Mul(result.Velocity[k],t));
    }
    return EvaluateOriginalEffectColor(result,t);
}
EffectPercentScaleState ChangeOriginalEffectPercentScale(const EffectPercentScaleState& s,
    const std::array<float,4>& previous,const std::array<float,4>& current){
    Validate(s.Scale);Validate(s.Percent);Validate(previous);Validate(current);auto result=s;
    for(unsigned k=0;k<3;++k){
        result.Percent[k]=Add(Sub(s.Percent[k],previous[k]),current[k]);
        result.Scale[k]=Mul(result.Percent[k],0.01f);
    }
    result.Scale[3]=0.0f;Validate(result.Scale);Validate(result.Percent);return result;
}
EffectPercentScaleState ResetOriginalEffectPercentScale(const EffectPercentScaleState& s){
    Validate(s.Scale);Validate(s.Percent);auto result=s;
    for(unsigned k=0;k<3;++k)result.Percent[k]=Mul(s.Scale[k],100.0f);
    result.Percent[3]=0.0f;Validate(result.Percent);return result;
}
} // namespace T3BGE
