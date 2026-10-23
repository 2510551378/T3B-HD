// Test-only adapters around byte-identical upstream transform/rectangle functions.
// Does not sample textures, run depth tests, or claim complete PPSSPP rendering.
#include "GPU/Math3D.h"
#include "Common/CPUDetect.h"
#include <cstdio>
#include <stdexcept>
#include <vector>
#include <iostream>
#include <limits>
#include <smmintrin.h>
using namespace Math3D;
TestCPUInfo cpu_info{true};
using ClipCoords=Vec4f;
static constexpr int SCREEN_SCALE_FACTOR=16;
struct ScreenCoords { int x=0,y=0;u16 z=0;ScreenCoords()=default;ScreenCoords(int a,int b,u16 c):x(a),y(b),z(c){} };
struct DrawingCoords { int x,y; };
struct VertexData { Vec3Packedf texturecoords;float clipw=0;u32 color0=0,color1=0;ScreenCoords screenpos;float fogdepth=0; };
struct ClipVertexData { ClipCoords clippos;VertexData v;bool OutsideRange()const{return v.screenpos.x==0x7fffffff;} };
struct RetainedState {
    u32 r[256]{},fog1=0,fog2=0;float worldMatrix[12],viewMatrix[12],projMatrix[16];
    float F(u32 v)const{v<<=8;float f;std::memcpy(&f,&v,4);return f;}
    float getViewportXScale()const{return F(r[0x42]);}float getViewportYScale()const{return F(r[0x43]);}float getViewportZScale()const{return F(r[0x44]);}
    float getViewportXCenter()const{return F(r[0x45]);}float getViewportYCenter()const{return F(r[0x46]);}float getViewportZCenter()const{return F(r[0x47]);}
    bool isLightingEnabled()const{return r[0x17]&1;}bool isFogEnabled()const{return r[0x1f]&1;}
    bool isModeClear()const{return r[0xd3]!=0;}bool isTextureMapEnabled()const{return r[0x1e]&1;}
    bool isDitherEnabled()const{return r[0x20]&1;}
    bool areNormalsReversed()const{return r[0x51]&1;}int getUVGenMode()const{return r[0xc0]&3;}
    bool isDepthClampEnabled()const{return r[0x1c]&1;}int getOffsetX16()const{return r[0x4c]&65535;}int getOffsetY16()const{return r[0x4d]&65535;}
}gstate;
float getFloat24(u32 v){v<<=8;float f;std::memcpy(&f,&v,4);return f;}
bool my_isnanorinf(float f){return !std::isfinite(f);}
struct VertexReader{bool isThrough()const{return false;}bool hasUV()const{return true;}bool hasColor0()const{return true;}};
namespace Lighting {struct State{bool usesWorldPos=false,usesWorldNormal=false;};void ComputeState(State*,bool){throw std::runtime_error("Unexpected lighting path");}}
enum class MatrixMode {POS_TO_CLIP,WORLD_TO_CLIP};
enum {GE_TEXMAP_TEXTURE_COORDS=0,GE_TEXMAP_ENVIRONMENT_MAP=2,GE_TEXMAP_UNKNOWN=3};
struct TransformState {
    Lighting::State lightingState;float matrix[16];Vec4f posToFog;Vec3f screenScale,screenAdd;
    ScreenCoords(*roundToScreen)(Vec3f,const ClipCoords&,bool*);
    bool enableTransform,enableLighting,enableFog,readUV,negateNormals;uint8_t uvGenMode,matrixMode;
};
// Added getters preserve only register storage. Arithmetic is upstream.
struct ViewportGetters:RetainedState {};
#include "upstream_transform.inc"
struct BinCoords{int x1,y1,x2,y2;};
struct PixelID {
    bool applyDepthRange=true,earlyZChecks=false,clearMode=false;
    struct{int minz=0,maxz=65535,depthbufStride=512;}cached;
    int DepthTestFunc()const{return 7;}
};
struct RasterizerState {
    bool enableTextures=true,throughMode=false,textureProj=false;
    struct{int width0Shift=5,height0Shift=5;}samplerID;
    PixelID pixelID;
    void(*drawPixel)(int,int,int,int,const Vec4<int>&,const PixelID&)=nullptr;
};
RasterizerState OptimizeFlatRasterizerState(const RasterizerState&s,const VertexData&){return s;}
bool CheckDepthTestPassed(int,int,int,int,int){throw std::runtime_error("Unexpected early depth lookup");}
const Vec4<int>& ToVec4IntArg(const Vec4<int>&v){return v;}
struct TransformUnit{static DrawingCoords ScreenToDrawing(int x,int y){return {(x>>4)&1023,(y>>4)&1023};}};
static FILE *partsOut=nullptr,*pixelsOut=nullptr;
static u32 sampleID=0,pairID=0,partID=0;
static std::uint64_t pixelsWritten=0;
static std::vector<std::pair<float,float>> textureCoords;
static size_t textureAt=0;
template<class T>void Put(FILE*f,const T&v){if(std::fwrite(&v,sizeof(T),1,f)!=1)throw std::runtime_error("Reference output failed");}
void ApplyTexturing(const RasterizerState&,Vec4<int>*,const Vec4<int>&mask,const Vec4<float>&s,const Vec4<float>&t,float){
    textureCoords.clear();textureAt=0;
    for(int i=0;i<4;++i)if(mask[i]>=0)textureCoords.emplace_back(s[i],t[i]);
}
void CapturePixel(int x,int y,int z,int fog,const Vec4<int>&c,const PixelID&){
    if(textureAt>=textureCoords.size()||++pixelsWritten>20000000)throw std::runtime_error("Unexpected pixel/texture call extent");
    auto uv=textureCoords[textureAt++];Put(pixelsOut,partID);Put(pixelsOut,u32(x));Put(pixelsOut,u32(y));
    Put(pixelsOut,uv.first);Put(pixelsOut,uv.second);Put(pixelsOut,u32(z));Put(pixelsOut,u32(fog));Put(pixelsOut,c.ToRGBA());
}
#define PROFILE_THIS_SCOPE(x) do{}while(0)
class BinManager;
namespace Rasterizer {
#include "upstream_rectangle.inc"
bool RectangleFastPath(const VertexData&,const VertexData&,::BinManager&){throw std::runtime_error("Unexpected through-mode path");}
}
class BinManager {
    RasterizerState state;
public:
    BinManager(){state.drawPixel=&CapturePixel;}
    const RasterizerState&State()const{return state;}
    void AddRect(const VertexData&a,const VertexData&b){
        ++partID;const auto begin=pixelsWritten;
        Rasterizer::DrawRectangle(a,b,{0,0,480*16-1,272*16-1},state);
        Put(partsOut,sampleID);Put(partsOut,pairID);Put(partsOut,partID);
        Put(partsOut,a.screenpos.x);Put(partsOut,a.screenpos.y);Put(partsOut,b.screenpos.x);Put(partsOut,b.screenpos.y);Put(partsOut,u32(b.screenpos.z));
        Put(partsOut,a.texturecoords.x);Put(partsOut,a.texturecoords.y);Put(partsOut,b.texturecoords.x);Put(partsOut,b.texturecoords.y);
        Put(partsOut,b.fogdepth);Put(partsOut,b.color0);Put(partsOut,begin);Put(partsOut,u32(pixelsWritten-begin));
    }
    void AddClearRect(const VertexData&,const VertexData&){throw std::runtime_error("Unexpected clear-mode path");}
};
namespace Clipper {
void AddTriangleRect(const VertexData&,const VertexData&,BinManager&){throw std::runtime_error("Unexpected texture projection");}
#include "upstream_process_rect.inc"
}
template<class T>void Read(FILE*f,T*p,size_t n=1){if(std::fread(p,sizeof(T),n,f)!=n)throw std::runtime_error("Truncated sprite input");}
int main(int argc,char**argv){
    if(argc!=5)return 2;
    try{
        FILE*input=std::fopen(argv[1],"rb"),*endpointOut=std::fopen(argv[2],"wb");partsOut=std::fopen(argv[3],"wb");pixelsOut=std::fopen(argv[4],"wb");
        if(!input||!endpointOut||!partsOut||!pixelsOut)throw std::runtime_error("Reference file open failed");
        char magic[8];Read(input,magic,8);u32 draws;Read(input,&draws);
        if(std::memcmp(magic,"T3BSPR1\0",8)||draws<1||draws>64)throw std::runtime_error("Wrong source sprite format/scope");
        u32 total=0;
        for(sampleID=0;sampleID<draws;++sampleID){
            Read(input,gstate.r,256);gstate.fog1=gstate.r[0xcd];gstate.fog2=gstate.r[0xce];
            Read(input,gstate.worldMatrix,12);Read(input,gstate.viewMatrix,12);Read(input,gstate.projMatrix,16);u32 count;Read(input,&count);
            if(count>65535||count%2||gstate.r[0x12]!=0x119)throw std::runtime_error("Wrong source rectangle count/VTYPE");
            TransformState state{};VertexReader reader;ComputeTransformState(&state,reader);
            std::vector<ClipVertexData> endpoints;
            for(u32 i=0;i<count;++i){
                float p[3],uv[2];u32 color;Read(input,p,3);Read(input,uv,2);Read(input,&color);
                ClipVertexData v{};v.clippos=Vec3ByMatrix44(Vec3f(p),state.matrix);
                Vec3f scaled;scaled.vec=_mm_add_ps(_mm_div_ps(_mm_mul_ps(v.clippos.vec,state.screenScale.vec),_mm_shuffle_ps(v.clippos.vec,v.clippos.vec,_MM_SHUFFLE(3,3,3,3))),state.screenAdd.vec);
                bool outside=false;v.v.screenpos=state.roundToScreen(scaled,v.clippos,&outside);if(outside)v.v.screenpos.x=0x7fffffff;
                v.v.fogdepth=state.enableFog?Dot43(state.posToFog,Vec3f(p)):1.f;v.v.clipw=v.clippos.w;v.v.color0=color;
                v.v.texturecoords=Vec3Packedf(uv[0]*getFloat24(gstate.r[0x48])+getFloat24(gstate.r[0x4a]),uv[1]*getFloat24(gstate.r[0x49])+getFloat24(gstate.r[0x4b]),0.f);
                for(int k=0;k<4;++k){Put(endpointOut,v.clippos[k]);}
                Put(endpointOut,v.v.screenpos.x);Put(endpointOut,v.v.screenpos.y);Put(endpointOut,u32(v.v.screenpos.z));Put(endpointOut,v.v.fogdepth);Put(endpointOut,u32(outside));
                endpoints.push_back(v);++total;
            }
            BinManager binner;
            for(pairID=0;pairID<count/2;++pairID)Clipper::ProcessRect(endpoints[pairID*2],endpoints[pairID*2+1],binner);
        }
        if(std::fgetc(input)!=EOF)throw std::runtime_error("Trailing sprite input");
        std::fclose(input);std::fclose(endpointOut);std::fclose(partsOut);std::fclose(pixelsOut);
        std::cout<<"{\"endpoints\":"<<total<<",\"parts\":"<<partID<<",\"candidate_pixels\":"<<pixelsWritten<<"}\n";return 0;
    }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
