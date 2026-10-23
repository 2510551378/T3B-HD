#include "T3BGEEffectVectorCurve.h"
#include <cmath>
#include <stdexcept>
namespace {
void Check(bool v,const char* s){if(!v)throw std::runtime_error(s);}
float F32(float x){volatile float rounded=x;return rounded;}
float Add(float x,float y){return F32(x+y);}
float Sub(float x,float y){return F32(x-y);}
float Mul(float x,float y){return F32(x*y);}
void Valid(const T3BGE::EffectVectorState& s){
    for(const auto* v:{&s.Current,&s.Base,&s.Velocity,&s.Acceleration}){for(float x:*v){Check(std::isfinite(x),"Nonfinite vector state");}}
}
void Valid(const T3BGE::EffectVectorKey& k){
    for(const auto* v:{&k.Base,&k.Velocity,&k.Acceleration}){for(float x:*v){Check(std::isfinite(x),"Nonfinite vector key");}}
}
}
namespace T3BGE {
EffectVectorState EvaluateOriginalEffectVector(const EffectVectorState& s,float t){
    Valid(s);Check(std::isfinite(t),"Nonfinite vector time");auto out=s;const float halfTime=Mul(t,0.5f);
    for(unsigned i=0;i<4;++i){out.Current[i]=Add(Mul(Add(Mul(s.Acceleration[i],halfTime),s.Velocity[i]),t),s.Base[i]);}
    Valid(out);return out;
}
EffectVectorState ChangeOriginalEffectVector(const EffectVectorState& s,const EffectVectorKey& previous,const EffectVectorKey& current,float t){
    Valid(s);Valid(previous);Valid(current);Check(std::isfinite(t),"Nonfinite vector time");auto out=s;const float halfSquared=Mul(Mul(t,t),0.5f);
    for(unsigned i=0;i<3;++i){
        const float oldValue=Add(Mul(previous.Acceleration[i],halfSquared),Add(Mul(previous.Velocity[i],t),previous.Base[i]));
        // The original helper reuses previous-key acceleration in this term.
        const float stateValue=Add(Mul(previous.Acceleration[i],halfSquared),Add(Mul(s.Velocity[i],t),s.Base[i]));
        out.Base[i]=Add(Sub(stateValue,oldValue),current.Base[i]);
        const float oldVelocity=Add(Mul(previous.Acceleration[i],t),previous.Velocity[i]);
        const float stateVelocity=Add(Mul(s.Acceleration[i],t),s.Velocity[i]);
        out.Velocity[i]=Add(Sub(stateVelocity,oldVelocity),current.Velocity[i]);
        out.Acceleration[i]=Add(Sub(s.Acceleration[i],previous.Acceleration[i]),current.Acceleration[i]);
    }
    out.Current=out.Base;Valid(out);return out;
}
EffectVectorState WrapOriginalEffectVector(const EffectVectorState& s,const EffectVectorKey& previous,const EffectVectorKey& current,float t,float oldTime){
    Valid(s);Valid(previous);Valid(current);Check(std::isfinite(t)&&std::isfinite(oldTime),"Nonfinite vector wrap time");auto out=s;
    const float halfOldSquared=Mul(Mul(oldTime,oldTime),0.5f),newSquared=Mul(t,t);
    for(unsigned i=0;i<3;++i){
        const float accumulated=Add(Mul(s.Acceleration[i],halfOldSquared),Add(Mul(s.Velocity[i],oldTime),s.Base[i]));
        const float oldVelocity=Add(Mul(previous.Acceleration[i],oldTime),previous.Velocity[i]);
        const float stateVelocity=Add(Mul(s.Acceleration[i],oldTime),s.Velocity[i]);
        out.Velocity[i]=Add(Sub(stateVelocity,oldVelocity),current.Velocity[i]);
        out.Acceleration[i]=Add(current.Acceleration[i],Sub(s.Acceleration[i],previous.Acceleration[i]));
        const float carry=Add(Mul(Mul(out.Acceleration[i],0.5f),newSquared),Mul(out.Velocity[i],t));
        out.Base[i]=Sub(accumulated,carry);
    }
    return EvaluateOriginalEffectVector(out,t);
}
} // namespace T3BGE
