#include "T3BGEOriginalMatrix.h"
#include <cstring>
#include <iostream>
#include <string>

static void PrintBits(const T3BGE::OriginalMatrix16& out){
    for(float v:out){std::uint32_t b;std::memcpy(&b,&v,4);std::cout<<std::hex<<b<<' ';}
    std::cout<<'\n';
}

static int RunStdin(){
    T3BGE::OriginalMatrixInput x{};
    while(std::cin>>x.mode>>x.scalar>>x.p30[0]>>x.p30[1]>>x.p30[2]){
        for(float& v:x.input)std::cin>>v;
        for(float& v:x.parent)std::cin>>v;
        for(float& v:x.global)std::cin>>v;
        if(!std::cin) return 2;
        PrintBits(T3BGE::ComputeOriginalMatrix(x));
    }
    return 0;
}

int main(int argc,char** argv){
    // The optional stdin mode is used by the actual PPSSPP sidecar verifier.
    // Keep the zero-argument synthetic probe stable for the small regression.
    if(argc==2&&std::string(argv[1])=="--stdin") return RunStdin();
    T3BGE::OriginalMatrixInput x{};x.scalar=.625f;x.p30={2.f,3.f,4.f};
    for(unsigned i=0;i<16;++i){x.input[i]=float(static_cast<int>((i*7+3)%11)-5)/3.f;x.parent[i]=float(static_cast<int>((i*5+1)%13)-6)/4.f;x.global[i]=float(static_cast<int>((i*3+2)%17)-8)/5.f;}
    for(unsigned mode=0;mode<2;++mode){x.mode=mode;PrintBits(T3BGE::ComputeOriginalMatrix(x));}
    return 0;
}
