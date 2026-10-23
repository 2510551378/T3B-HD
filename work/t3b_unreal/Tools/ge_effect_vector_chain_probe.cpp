#include "T3BGEEffectModifiers.h"
#include "T3BGEEffectVectorCurve.h"
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
    explicit Reader(const char* p){std::ifstream f(p,std::ios::binary);Check(bool(f),"Chain input unreadable");bytes={std::istreambuf_iterator<char>(f),{}};Check(bytes.size()<=1024*1024,"Chain input size");}
    std::uint32_t Word(){Check(at+4<=bytes.size(),"Chain input truncated");const auto* p=bytes.data()+at;at+=4;return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);}
    float Float(){auto w=Word();float x;std::memcpy(&x,&w,4);return x;}
    bool End()const{return at==bytes.size();}
};
void Output(std::vector<float>& out,const T3BGE::EffectVectorState& state){for(const auto* v:{&state.Current,&state.Base,&state.Velocity,&state.Acceleration})out.insert(out.end(),v->begin(),v->end());}
}
int main(int argc,char** argv){
    try{
        if(argc!=3)return 2;
        Reader r(argv[1]);Check(r.Word()==0x56423354&&r.Word()==0x00314843,"Wrong vector chain magic");const auto n=r.Word();Check(n>0&&n<=32,"Vector chain step bound");
        T3BGE::EffectModifierWindow initial;for(auto& x:initial){x=r.Float();}T3BGE::EffectModifierChannels channels;
        for(auto& c:channels){const auto enabled=r.Word(),mode=r.Word();Check(enabled<=1&&mode<=255,"Bad chain modifier flags");c.enabled=enabled;c.mode=static_cast<std::uint8_t>(mode);for(auto& x:c.amplitude){x=r.Float();}}
        std::array<std::array<float,3>,3> random;for(auto& v:random){for(auto& x:v){x=r.Float();}}std::array<float,3> center;for(auto& x:center){x=r.Float();}
        T3BGE::ApplyOriginalType23Modifiers(initial,channels,random,center);T3BGE::EffectVectorState state;unsigned index=0;
        for(auto* v:{&state.Current,&state.Base,&state.Velocity,&state.Acceleration}){for(auto& x:*v){x=initial[index++];}}
        std::vector<float> output;Output(output,state);
        for(std::uint32_t i=0;i<n;++i){
            const auto kind=r.Word();const float t=r.Float(),previousTime=r.Float();T3BGE::EffectVectorKey previous,current;
            for(auto* k:{&previous,&current}){for(auto* v:{&k->Base,&k->Velocity,&k->Acceleration}){for(auto& x:*v){x=r.Float();}}}
            if(kind==1)state=T3BGE::EvaluateOriginalEffectVector(state,t);
            else if(kind==2)state=T3BGE::WrapOriginalEffectVector(state,previous,current,t,previousTime);
            else throw std::runtime_error("Unknown chain transition");
            Output(output,state);
        }
        Check(r.End(),"Trailing chain input");std::ofstream f(argv[2],std::ios::binary);f.write(reinterpret_cast<const char*>(output.data()),output.size()*4);Check(bool(f),"Chain output failed");std::cout<<"{\"steps\":"<<n<<",\"state_snapshots_loaded\":1}\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
