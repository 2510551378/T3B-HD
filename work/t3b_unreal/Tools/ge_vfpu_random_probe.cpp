#include "T3BGEVfpuRandom.h"
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
void Check(bool v,const char* s){if(!v)throw std::runtime_error(s);}
std::uint32_t Word(std::ifstream& f){std::uint32_t w;f.read(reinterpret_cast<char*>(&w),4);Check(bool(f),"VRND input truncated");return w;}
int main(int argc,char** argv){try{if(argc!=3)return 2;std::ifstream in(argv[1],std::ios::binary);Check(bool(in),"VRND input unreadable");Check(Word(in)==0x56423354&&Word(in)==0x00314e52,"Wrong VRND magic");auto n=Word(in);Check(n>0&&n<=128,"VRND case bound");std::ofstream out(argv[2],std::ios::binary);for(std::uint32_t i=0;i<n;++i){auto seed=Word(in),steps=Word(in);T3BGE::VFPURCXState s;T3BGE::InitOriginalVFPURCXSeed(s,seed);for(std::uint32_t j=0;j<steps;++j){auto kind=Word(in);std::uint32_t value=kind==0?T3BGE::GenerateOriginalVRNDI(s):kind==1?T3BGE::GenerateOriginalVRNDF1(s):kind==2?T3BGE::GenerateOriginalVRNDF2(s):throw std::runtime_error("VRND kind");out.write(reinterpret_cast<char*>(&value),4);}for(auto w:s.words)out.write(reinterpret_cast<char*>(&w),4);}Check(bool(in),"VRND input trailing");std::cout<<"{\"cases\":"<<n<<"}\n";return 0;}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
