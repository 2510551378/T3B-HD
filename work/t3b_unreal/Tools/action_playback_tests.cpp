#include "../Source/T3BRemake/Private/T3BActionClip.h"
#include <cmath>
#include <iostream>
#include <limits>

namespace {
unsigned checks=0, failures=0;
void Check(bool ok,const char* name){++checks;if(!ok){++failures;std::cerr<<name<<'\n';}}
T3BSource::Skin Skin(float offset){
    T3BSource::Skin s;s.bones=1;s.materials=1;s.flags=15;s.units=1;s.floor=0;
    s.parent={-1};s.time={0,1};s.packets={{0,1,0,3}};
    T3BSource::SkinVertex v;v.count=1;v.weight[0]=1;v.position.x=offset;s.vertices={v};
    s.matrix={1,0,0,0,0,1,0,0,0,0,1,0, 1,0,0,4,0,1,0,0,0,0,1,0};
    return s;
}
bool Reject(const T3BSource::Skin& a,const T3BSource::Skin& b){
    try{T3BAction::ValidateCompatible(a,b);}catch(const T3BSource::FormatError&){return true;}return false;
}
float X(const T3BSource::Skin& s,double t){return T3BAction::Pose(s,T3BAction::PlaybackPhase(t,1,true))[0].x;}
}
int main(){
    const auto body=Skin(0),gun=Skin(5);
    T3BAction::ValidateCompatible(body,body);Check(true,"identical reference accepted");
    auto other=body;
    other=body;other.vertices[0].uv.u=.5f;Check(Reject(body,other),"UV replacement refused");
    other=body;other.vertices[0].weight[0]=.99f;Check(Reject(body,other),"weight replacement refused");
    other=body;other.vertices[0].position.x=1;Check(Reject(body,other),"geometry replacement refused");
    other=body;other.vertices[0].normal.y=1;Check(Reject(body,other),"normal replacement refused");
    other=body;other.packets[0].material=1;Check(Reject(body,other),"material rebinding refused");
    other=body;other.parent[0]=0;Check(Reject(body,other),"hierarchy replacement refused");
    other=body;other.flags=0;Check(Reject(body,other),"render flags replacement refused");
    other=body;other.units=2;Check(Reject(body,other),"unit replacement refused");
    other=body;other.matrix[3]=100;T3BAction::ValidateCompatible(body,other);Check(true,"new poses allowed");
    Check(std::abs(X(body,.5)-2)<1e-5,"finite source interval unchanged");
    Check(std::abs(X(body,1.06)-2)<1e-4,"end-to-start seam midpoint");
    Check(std::abs(X(body,1.25)-.52f)<1e-4,"overshoot remainder preserved");
    for(double t:{0.,.5,1.,1.06,1.12,2.23,4.54,90.15})
        Check(std::abs((X(gun,t)-X(body,t))-5)<1e-4,"paired attachment invariant");
    for(double boundary:{1.,1.12,2.12,2.24})
        Check(std::abs(X(body,boundary-1e-6)-X(body,boundary+1e-6))<1e-4,"continuous seam endpoints");
    Check(T3BAction::PlaybackPhase(-2,1,false).first==0,"negative seek clamped");
    Check(T3BAction::PlaybackPhase(2,1,false).first==1,"finite probe never loops");
    bool rejected=false;try{T3BAction::PlaybackPhase(std::numeric_limits<double>::quiet_NaN(),1,true);}
    catch(const T3BSource::FormatError&){rejected=true;}Check(rejected,"nonfinite clock refused");
    rejected=false;try{T3BAction::Pose(body,{0,0,std::numeric_limits<float>::quiet_NaN()});}
    catch(const T3BSource::FormatError&){rejected=true;}Check(rejected,"nonfinite phase refused");
    std::cout<<"action_playback_checks="<<checks<<"\naction_playback_failures="<<failures<<'\n';return failures?1:0;
}
