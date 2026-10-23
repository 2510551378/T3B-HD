// Test-only retained-register adapter for unchanged tagged PPSSPP Lighting.cpp.
// This is not a full GPU state, target emulator, or replacement for its backend.
#pragma once
#include <cstdint>
#include <cstring>
using u8=std::uint8_t; using u16=std::uint16_t; using u32=std::uint32_t;
using s8=std::int8_t; using s16=std::int16_t; using s32=std::int32_t;
inline float getFloat24(u32 x) { x<<=8;float v;std::memcpy(&v,&x,4);return v; }
constexpr int GE_TEXMAP_ENVIRONMENT_MAP=2;
struct RetainedGPUState {
    u32 r[256]{},lpos[12]{},latt[12]{},ldir[12]{},lcutoff[4]{},lconv[4]{};
    u32 materialupdate=0;
    void Load(const u32* words) {
        std::memcpy(r,words,sizeof(r));materialupdate=r[0x53];
        for(int i=0;i<12;++i) { lpos[i]=r[0x63+i];latt[i]=r[0x7B+i];ldir[i]=r[0x6F+i]; }
        for(int i=0;i<4;++i) { lcutoff[i]=r[0x8B+i];lconv[i]=r[0x87+i]; }
    }
    bool isLightChanEnabled(int i) const{return r[0x18+i]&1;}
    bool isUsingPoweredDiffuseLight(int i)const{return (r[0x5F+i]&3)==2;}
    bool isUsingSpecularLight(int i)const{return (r[0x5F+i]&3)==1;}
    bool isDirectionalLight(int i)const{return ((r[0x5F+i]>>8)&3)==0;}
    bool isSpotLight(int i)const{return ((r[0x5F+i]>>8)&3)==2;}
    bool isUsingSecondaryColor()const{return r[0x5E]&1;}
    u32 getLightAmbientColor(int i)const{return r[0x8F+i*3]&0xFFFFFF;}
    u32 getDiffuseColor(int i)const{return r[0x90+i*3]&0xFFFFFF;}
    u32 getSpecularColor(int i)const{return r[0x91+i*3]&0xFFFFFF;}
    u32 getMaterialAmbientRGBA()const{return (r[0x55]&0xFFFFFF)|((r[0x58]&255)<<24);}
    u32 getMaterialDiffuse()const{return r[0x56]&0xFFFFFF;}
    u32 getMaterialSpecular()const{return r[0x57]&0xFFFFFF;}
    u32 getMaterialEmissive()const{return r[0x54]&0xFFFFFF;}
    u32 getAmbientRGBA()const{return (r[0x5C]&0xFFFFFF)|((r[0x5D]&255)<<24);}
    float getMaterialSpecularCoef()const{return getFloat24(r[0x5B]);}
    int getUVGenMode()const{return r[0xC0]&3;}
    int getUVLS0()const{return r[0xC1]&3;}
    int getUVLS1()const{return (r[0xC1]>>8)&3;}
};
extern RetainedGPUState gstate;
