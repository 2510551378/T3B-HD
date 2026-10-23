#include "T3BGEVfpuRandom.h"
namespace T3BGE {
void InitOriginalVFPURCXDefault(VFPURCXState& s){s.words={1u,2u,4u,8u,0u,0u,0u,0u};}
void InitOriginalVFPURCXSeed(VFPURCXState& s,std::uint32_t seed){for(int i=0;i<8;++i)s.words[i]=0x3F800000u|((seed>>((i/4)*16))&0xFFFFu)|(((seed>>(4*i))&0xFu)<<16);}
std::uint32_t GenerateOriginalVFPURandom(VFPURCXState& s){
    auto& r=s.words;std::uint32_t A=(r[0]&0xFFFFu)|(r[4]<<16),B=(r[1]&0xFFFFu)|(r[5]<<16),C=(r[2]&0xFFFFu)|(r[6]<<16),D=(r[3]&0xFFFFu)|(r[7]<<16);
    std::uint32_t E=(((r[0]>>16)&0xF)<<0)|(((r[1]>>16)&0xF)<<4)|(((r[2]>>16)&0xF)<<8)|(((r[3]>>16)&0xF)<<12)|(((r[4]>>16)&0xF)<<16)|(((r[5]>>16)&0xF)<<20)|(((r[6]>>16)&0xF)<<24)|(((r[7]>>16)&0xF)<<28);
    A=69069u*A+1u;B^=B<<13;B^=B>>17;B^=B<<5;std::uint32_t t=2u*D+C+E;E=std::uint32_t((std::uint64_t(C)+std::uint64_t(D>>1)+std::uint64_t(E))>>32);C=D;D=t;
    r[0]=0x3F800000u|(((E>>0)&0xF)<<16)|(A&0xFFFFu);r[1]=0x3F800000u|(((E>>4)&0xF)<<16)|(B&0xFFFFu);r[2]=0x3F800000u|(((E>>8)&0xF)<<16)|(C&0xFFFFu);r[3]=0x3F800000u|(((E>>12)&0xF)<<16)|(D&0xFFFFu);
    r[4]=0x3F800000u|(((E>>16)&0xF)<<16)|(A>>16);r[5]=0x3F800000u|(((E>>20)&0xF)<<16)|(B>>16);r[6]=0x3F800000u|(((E>>24)&0xF)<<16)|(C>>16);r[7]=0x3F800000u|(((E>>28)&0xF)<<16)|(D>>16);
    return A+B+D;
}
std::uint32_t GenerateOriginalVRNDI(VFPURCXState& s){return GenerateOriginalVFPURandom(s);}
std::uint32_t GenerateOriginalVRNDF1(VFPURCXState& s){return 0x3F800000u|(GenerateOriginalVFPURandom(s)&0x007FFFFFu);}
std::uint32_t GenerateOriginalVRNDF2(VFPURCXState& s){return 0x40000000u|(GenerateOriginalVFPURandom(s)&0x007FFFFFu);}
} // namespace T3BGE
