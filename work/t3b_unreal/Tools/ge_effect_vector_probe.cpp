#include "T3BGEEffectVectorCurve.h"
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>
namespace {
void Check(bool v,const char* s){if(!v)throw std::runtime_error(s);}
class Reader {
    std::vector<unsigned char> bytes;std::size_t at=0;
public:
    explicit Reader(const char* p){std::ifstream f(p,std::ios::binary);Check(bool(f),"Input unreadable");bytes={std::istreambuf_iterator<char>(f),{}};Check(bytes.size()<=1024*1024,"Vector input size");}
    std::uint32_t Word(){Check(at+4<=bytes.size(),"Vector input truncated");const auto* p=bytes.data()+at;at+=4;return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);}
    float Float(){auto w=Word();float x;std::memcpy(&x,&w,4);return x;}
    bool End()const{return at==bytes.size();}
};
}
int main(int argc,char** argv){
    try{
        if(argc!=3)return 2;
        Reader r(argv[1]);Check(r.Word()==0x56423354&&r.Word()==0x00314345,"Wrong vector input magic");const auto n=r.Word();Check(n>0&&n<=128,"Vector operation bound");std::vector<float> result;
        for(std::uint32_t i=0;i<n;++i){
            const auto kind=r.Word();T3BGE::EffectVectorState state;
            for(auto* v:{&state.Current,&state.Base,&state.Velocity,&state.Acceleration}){for(auto& x:*v){x=r.Float();}}
            T3BGE::EffectVectorKey previous,current;
            for(auto* k:{&previous,&current}){for(auto* v:{&k->Base,&k->Velocity,&k->Acceleration}){for(auto& x:*v){x=r.Float();}}}
            const float t=r.Float(),oldTime=r.Float();
            if(kind==1)state=T3BGE::ChangeOriginalEffectVector(state,previous,current,t);
            else if(kind==2)state=T3BGE::WrapOriginalEffectVector(state,previous,current,t,oldTime);
            else if(kind==3)state=T3BGE::EvaluateOriginalEffectVector(state,t);
            else throw std::runtime_error("Unknown vector operation");
            for(const auto* v:{&state.Current,&state.Base,&state.Velocity,&state.Acceleration})result.insert(result.end(),v->begin(),v->end());
        }
        Check(r.End(),"Trailing vector input");std::ofstream f(argv[2],std::ios::binary);f.write(reinterpret_cast<const char*>(result.data()),result.size()*4);Check(bool(f),"Vector output failed");std::cout<<"{\"operations\":"<<n<<"}\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
