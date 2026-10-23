#include "T3BGEEffectClock.h"
#include <cmath>
#include <cstring>
#include <stdexcept>

namespace {
void Check(bool ok,const char* why) { if (!ok) throw std::runtime_error(why); }
float Add(float a,float b) { volatile float result=a+b; return result; }
float Sub(float a,float b) { volatile float result=a-b; return result; }
} // namespace

namespace T3BGE {
float AdvanceOriginalEffectTime(float current,float effectiveDelta) {
    Check(std::isfinite(current)&&std::isfinite(effectiveDelta),"Nonfinite original effect time");
    const float result=Add(current,effectiveDelta);
    Check(std::isfinite(result),"Effect time overflow"); return result;
}
float WrapOriginalEffectTime(float current,std::uint16_t start,std::uint16_t end) {
    Check(std::isfinite(current)&&double(current)>=-2147483648.0&&double(current)<2147483648.0,
          "Effect clock outside verified trunc.w.s domain");
    Check(end>start,"Invalid original effect loop interval");
    const auto integer=static_cast<std::int32_t>(current); // trunc.w.s
    // The original SUBU is modulo2^32 before signed DIV/MFHI.
    const std::uint32_t raw=static_cast<std::uint32_t>(integer)-std::uint32_t(end);
    std::int32_t numerator; std::memcpy(&numerator,&raw,4);
    const auto remainder=numerator/static_cast<std::int32_t>(end-start);
    const auto hi=numerator-remainder*static_cast<std::int32_t>(end-start);
    const float fraction=Sub(current,static_cast<float>(integer));
    return Add(Add(static_cast<float>(hi),static_cast<float>(start)),fraction);
}
float RelativeOriginalEffectTime(float nodeTime,bool hasRecord,std::int16_t start) {
    Check(std::isfinite(nodeTime),"Nonfinite original render time");
    return hasRecord ? Sub(nodeTime,static_cast<float>(start)) : nodeTime;
}
} // namespace T3BGE
