#include "../Source/T3BRemake/Private/T3BSourceData.h"

#include <cmath>
#include <cstring>
#include <functional>
#include <iostream>
#include <limits>
#include <string>

namespace {
using Bytes=std::vector<std::uint8_t>;
unsigned checks{},failures{};
void U32(Bytes& bytes,std::uint32_t value) { for(int byte=0;byte<4;byte++)bytes.push_back(static_cast<std::uint8_t>(value>>(byte*8))); }
void F32(Bytes& bytes,float value) { std::uint32_t bits;std::memcpy(&bits,&value,4);U32(bytes,bits); }
void PutU32(Bytes& bytes,std::size_t offset,std::uint32_t value) { for(int byte=0;byte<4;byte++)bytes.at(offset+byte)=static_cast<std::uint8_t>(value>>(byte*8)); }
void PutF32(Bytes& bytes,std::size_t offset,float value) { std::uint32_t bits;std::memcpy(&bits,&value,4);PutU32(bytes,offset,bits); }
void Check(bool passed,const std::string& name) { checks++;if(!passed){failures++;std::cerr<<"FAIL "<<name<<'\n';} }
void Reject(const Bytes& valid,bool skin,const std::string& name,const std::function<void(Bytes&)>& mutate) {
    auto bytes=valid;mutate(bytes);bool rejected=false;
    try { if(skin)T3BSource::LoadSkin(bytes);else T3BSource::LoadScene(bytes); }catch(const T3BSource::FormatError&){rejected=true;}
    Check(rejected,name);
}
Bytes ValidScene() {
    Bytes bytes{'T','3','B','S','C','N','1',0};U32(bytes,1);U32(bytes,1);U32(bytes,3);U32(bytes,1);
    for(float value:{0.0f,0.0f,0.0f,2.6f,.02f,-1.5f,.01f,-2.0f})F32(bytes,value);
    U32(bytes,0);U32(bytes,3);U32(bytes,0);
    for(int vertex=0;vertex<3;vertex++) {
        for(float value:{float(vertex),2.0f,3.0f,-.25f,1.75f})F32(bytes,value);
        for(auto color:{0,64,128,255})bytes.push_back(static_cast<std::uint8_t>(color));
    }return bytes;
}
Bytes ValidSkin() {
    Bytes bytes{'T','3','B','S','K','N','2',0};for(auto value:{2u,2u,1u,3u,2u,1u,15u,0u})U32(bytes,value);
    for(float value:{0.0f,.01f,-2.0f,0.0f})F32(bytes,value);
    U32(bytes,0xffffffffu);U32(bytes,0);for(auto value:{0u,3u,0u,3u})U32(bytes,value);
    for(int vertex=0;vertex<3;vertex++) {
        for(float value:{vertex?0.0f:1.0f,vertex?0.0f:2.0f,vertex?0.0f:3.0f,.25f,1.25f,0.0f,1.0f,0.0f})F32(bytes,value);
        U32(bytes,2);for(auto bone:{0u,1u,0u,0u,0u,0u,0u,0u})U32(bytes,bone);
        for(float weight:{.25f,.75f,0.0f,0.0f,0.0f,0.0f,0.0f,0.0f})F32(bytes,weight);
    }
    F32(bytes,0);F32(bytes,2);
    const float matrices[2][12]={{2,.5f,0,1,0,3,.25f,-2,.1f,0,-1,4},{1,0,2,-3,.5f,1,0,5,0,.25f,1,-1}};
    const float delta[2][3]={{4,-2,1},{-2,3,-5}};
    for(int sample=0;sample<2;sample++)for(int bone=0;bone<2;bone++)for(int component=0;component<12;component++)F32(bytes,matrices[bone][component]+(sample&&component%4==3?delta[bone][component/4]:0));
    return bytes;
}
bool Near(T3BSource::Vec3 a,T3BSource::Vec3 b,float tolerance=1e-5f) { return std::fabs(a.x-b.x)<=tolerance&&std::fabs(a.y-b.y)<=tolerance&&std::fabs(a.z-b.z)<=tolerance; }
} // namespace
int main() {
    const Bytes sceneBytes=ValidScene(),skinBytes=ValidSkin();const auto scene=T3BSource::LoadScene(sceneBytes);const auto skin=T3BSource::LoadSkin(skinBytes);
    Check(scene.draws.size()==1&&scene.vertices.size()==3&&scene.materials==1,"valid scene shape");
    Check(scene.vertices[0].rgba==std::array<std::uint8_t,4>{0,64,128,255}&&scene.vertices[0].uv.u==-.25f&&scene.vertices[0].uv.v==1.75f,"raw scene RGBA and repeated UV preserved");
    Check(skin.matrix[1]==.5f&&skin.matrix[10]==-1&&skin.parent==std::vector<std::int32_t>{-1,0},"shear reflection and hierarchy preserved");
    const auto first=T3BSource::PoseOriginal(skin,0),middle=T3BSource::PoseOriginal(skin,1),last=T3BSource::PoseOriginal(skin,2);
    Check(Near(first[0],{4,6.8125f,2.15f}),"original weighted arbitrary affine pose");
    Check(Near(middle[0],{3.75f,7.6875f,.4f}),"saved-time affine interpolation");
    Check(Near(last[0],{3.5f,8.5625f,-1.35f}),"final affine pose");
    Check(Near(T3BSource::PoseOriginal(skin,-1)[0],first[0])&&Near(T3BSource::PoseOriginal(skin,500)[0],last[0]),"both ends clamp without looping");
    const auto pc=T3BSource::ToPC(skin,middle[0],1,2,0);Check(Near(pc,{1.0375f,.096875f,2.004f}),"PC units floor actor translation");
    Check(Near(T3BSource::ToUE(pc),{200.4f,-103.75f,9.6875f},3e-5f),"UE coordinate permutation centimeters");
    Check(Near(T3BSource::ToPC(skin,middle[0],1,2,1.5707963267948966f),{1.004f,.096875f,1.9625f}),"actor yaw transform");
    Reject(sceneBytes,false,"scene truncated",[](Bytes& b){b.pop_back();});
    Reject(sceneBytes,false,"scene trailing byte",[](Bytes& b){b.push_back(0);});
    Reject(sceneBytes,false,"scene magic",[](Bytes& b){b[0]='X';});
    Reject(sceneBytes,false,"scene version",[](Bytes& b){PutU32(b,8,2);});
    Reject(sceneBytes,false,"scene zero draws",[](Bytes& b){PutU32(b,12,0);});
    Reject(sceneBytes,false,"scene huge vertices",[](Bytes& b){PutU32(b,16,0xffffffffu);});
    Reject(sceneBytes,false,"scene zero materials",[](Bytes& b){PutU32(b,20,0);});
    Reject(sceneBytes,false,"scene nonfinite spawn",[](Bytes& b){PutF32(b,24,NAN);});
    Reject(sceneBytes,false,"scene nonpositive units",[](Bytes& b){PutF32(b,48,0);});
    Reject(sceneBytes,false,"scene nonfinite floor",[](Bytes& b){PutF32(b,52,INFINITY);});
    Reject(sceneBytes,false,"scene noncontiguous first",[](Bytes& b){PutU32(b,56,1);});
    Reject(sceneBytes,false,"scene invalid primitive count",[](Bytes& b){PutU32(b,60,2);});
    Reject(sceneBytes,false,"scene out of range material",[](Bytes& b){PutU32(b,64,1);});
    Reject(sceneBytes,false,"scene nonfinite point",[](Bytes& b){PutF32(b,68,INFINITY);});
    Reject(sceneBytes,false,"scene nonfinite UV",[](Bytes& b){PutF32(b,80,NAN);});
    Reject(skinBytes,true,"skin truncated",[](Bytes& b){b.resize(100);});
    Reject(skinBytes,true,"skin trailing byte",[](Bytes& b){b.push_back(0);});
    Reject(skinBytes,true,"skin zero bones",[](Bytes& b){PutU32(b,12,0);});
    Reject(skinBytes,true,"skin too many bones",[](Bytes& b){PutU32(b,12,65);});
    Reject(skinBytes,true,"skin huge vertices",[](Bytes& b){PutU32(b,20,0xffffffffu);});
    Reject(skinBytes,true,"skin only one sample",[](Bytes& b){PutU32(b,24,1);});
    Reject(skinBytes,true,"skin zero materials",[](Bytes& b){PutU32(b,28,0);});
    Reject(skinBytes,true,"skin reserved header",[](Bytes& b){PutU32(b,36,1);});
    Reject(skinBytes,true,"skin zero units",[](Bytes& b){PutF32(b,44,0);});
    Reject(skinBytes,true,"skin nonfinite floor",[](Bytes& b){PutF32(b,48,NAN);});
    Reject(skinBytes,true,"skin parent range",[](Bytes& b){PutU32(b,56,2);});
    Reject(skinBytes,true,"skin invalid negative parent",[](Bytes& b){PutU32(b,56,0xfffffffeu);});
    Reject(skinBytes,true,"skin parent cycle",[](Bytes& b){PutU32(b,56,1);});
    Reject(skinBytes,true,"skin packet first",[](Bytes& b){PutU32(b,64,1);});
    Reject(skinBytes,true,"skin packet count",[](Bytes& b){PutU32(b,68,2);});
    Reject(skinBytes,true,"skin packet material",[](Bytes& b){PutU32(b,72,1);});
    Reject(skinBytes,true,"skin packet primitive",[](Bytes& b){PutU32(b,76,4);});
    Reject(skinBytes,true,"skin nonfinite vertex",[](Bytes& b){PutF32(b,80,INFINITY);});
    Reject(skinBytes,true,"skin nonfinite normal",[](Bytes& b){PutF32(b,100,NAN);});
    Reject(skinBytes,true,"skin influence count",[](Bytes& b){PutU32(b,112,9);});
    Reject(skinBytes,true,"skin influence index",[](Bytes& b){PutU32(b,116,2);});
    Reject(skinBytes,true,"skin negative weight",[](Bytes& b){PutF32(b,148,-.25f);});
    Reject(skinBytes,true,"skin nonfinite weight",[](Bytes& b){PutF32(b,148,NAN);});
    Reject(skinBytes,true,"skin nonzero inactive weight",[](Bytes& b){PutF32(b,156,.25f);});
    Reject(skinBytes,true,"skin wrong weight sum",[](Bytes& b){PutF32(b,148,.5f);});
    Reject(skinBytes,true,"skin sample not from zero",[](Bytes& b){PutF32(b,380,1);});
    Reject(skinBytes,true,"skin duplicate times",[](Bytes& b){PutF32(b,384,0);});
    Reject(skinBytes,true,"skin decreasing times",[](Bytes& b){PutF32(b,384,-1);});
    Reject(skinBytes,true,"skin nonfinite times",[](Bytes& b){PutF32(b,384,INFINITY);});
    Reject(skinBytes,true,"skin nonfinite matrix",[](Bytes& b){PutF32(b,388,NAN);});
    bool rejected=false;try{T3BSource::PoseOriginal(skin,NAN);}catch(const T3BSource::FormatError&){rejected=true;}Check(rejected,"reject nonfinite pose time");
    rejected=false;try{T3BSource::ToUE({INFINITY,0,0});}catch(const T3BSource::FormatError&){rejected=true;}Check(rejected,"reject nonfinite coordinate conversion");
    std::cout<<"source_data_checks="<<checks<<"\nsource_data_failures="<<failures<<'\n';return failures?1:0;
}
