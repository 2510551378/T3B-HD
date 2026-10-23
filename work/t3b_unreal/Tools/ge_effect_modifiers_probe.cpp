#include "T3BGEEffectModifiers.h"
#include <cmath>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>
namespace {
void Check(bool v,const char* s){if(!v)throw std::runtime_error(s);}
class Reader {
    std::vector<std::uint8_t> bytes;std::size_t at=0;
public:
    explicit Reader(const char* file){std::ifstream f(file,std::ios::binary);Check(bool(f),"Inputs unreadable");bytes={std::istreambuf_iterator<char>(f),{}};Check(bytes.size()<=1024*1024,"Input too large");}
    std::uint32_t Word(){Check(at+4<=bytes.size(),"Input truncated");const auto* p=bytes.data()+at;at+=4;return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);}
    float Float(){auto w=Word();float x;std::memcpy(&x,&w,4);return x;}
    bool End()const{return at==bytes.size();}
};
void Word(std::vector<std::uint8_t>& bytes,std::uint32_t value){for(unsigned k=0;k<4;++k)bytes.push_back(static_cast<std::uint8_t>(value>>(8*k)));}
}
int main(int argc,char** argv){
    try{
        if(argc!=3)return 2;
        Reader r(argv[1]);Check(r.Word()==0x4d423354&&r.Word()==0x00314f44,"Wrong modifier transport");const auto n=r.Word();Check(n>0&&n<=128,"Modifier case bound");std::vector<std::uint8_t> output;
        for(std::uint32_t i=0;i<n;++i){
            const auto type=r.Word(),independent=r.Word();auto seed=r.Word();Check((type==23||type==24)&&independent<=1,"Unsupported modifier interface");
            T3BGE::EffectModifierWindow target;for(auto& x:target){x=r.Float();}
            T3BGE::EffectModifierChannels channels;for(auto& c:channels){const auto enabled=r.Word(),mode=r.Word();Check(enabled<=1&&mode<=255,"Modifier channel flags");c.enabled=enabled;c.mode=static_cast<std::uint8_t>(mode);for(auto& x:c.amplitude){x=r.Float();}}
            std::array<std::array<float,3>,3> random;for(auto& v:random){for(auto& x:v){x=r.Float();}}
            std::array<float,3> center;for(auto& x:center){x=r.Float();}
            if(type==23)T3BGE::ApplyOriginalType23Modifiers(target,channels,random,center);
            else T3BGE::ApplyOriginalType24Modifiers(target,channels,independent,seed);
            for(float x:target){std::uint32_t w;std::memcpy(&w,&x,4);Word(output,w);}Word(output,seed);
        }
        Check(r.End(),"Trailing modifier input");std::ofstream f(argv[2],std::ios::binary);f.write(reinterpret_cast<const char*>(output.data()),output.size());Check(bool(f),"Output failed");std::cout<<"{\"operations\":"<<n<<"}\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
