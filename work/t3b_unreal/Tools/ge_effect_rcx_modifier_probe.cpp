#include "T3BGEEffectModifiers.h"
#include <cstring>
#include <iostream>
int main(){
    T3BGE::EffectModifierWindow target{};target[2]=45.f;target[6]=45.f;
    T3BGE::EffectModifierChannels channels{};channels[0].enabled=true;channels[1].enabled=true;channels[0].amplitude[2]=32.f;channels[1].amplitude[2]=16.f;
    T3BGE::VFPURCXState rcx;T3BGE::InitOriginalVFPURCXSeed(rcx,0x12345678);auto n=T3BGE::ApplyOriginalType23ModifiersFromRCX(target,channels,rcx,{3.f,3.f,3.f});
    std::cout<<n;for(float x:target){std::uint32_t b;std::memcpy(&b,&x,4);std::cout<<' '<<std::hex<<b;}std::cout<<'\n';return 0;
}
