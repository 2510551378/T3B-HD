// Compile unchanged upstream Lighting.cpp/Math3D.cpp as an independent reference.
#include "GPU/GPUState.h"
#include "GPU/Software/Lighting.h"
#include "T3BGELighting.h"
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <array>
#include <iostream>

RetainedGPUState gstate;
struct TestCPUInfo{bool bSSE4_1;};
TestCPUInfo cpu_info{true};
using namespace Math3D;
template<class T> void Read(FILE* f,T* p,std::size_t n=1){if(std::fread(p,sizeof(T),n,f)!=n)throw std::runtime_error("Truncated reference input");}
void Write(FILE*f,const T3BGE::Transformed& t,const T3BGE::Colors& c){
    std::fwrite(t.worldPosition.data(),4,3,f);std::fwrite(t.unitWorldNormal.data(),4,3,f);
    std::fwrite(c.primary.data(),1,4,f);std::fwrite(c.secondary.data(),1,3,f);std::fputc(0,f);
}
int main(int argc,char**argv){
    if(argc!=4)return 2;
    try{
        FILE* in=std::fopen(argv[1],"rb");FILE* official=std::fopen(argv[2],"wb");FILE* own=std::fopen(argv[3],"wb");
        if(!in||!official||!own)throw std::runtime_error("Reference file open failed");
        char magic[8];Read(in,magic,8);if(std::memcmp(magic,"T3BLIT1\0",8))throw std::runtime_error("Wrong input schema");
        u32 draws;Read(in,&draws);unsigned vertices=0,transformDiff=0,colorDiff=0,maxColorDiff=0;
        for(unsigned draw=0;draw<draws;++draw){
            T3BGE::Registers regs;Read(in,regs.data(),256);gstate.Load(regs.data());
            T3BGE::Matrix43 world;std::array<T3BGE::Matrix43,8>bones;Read(in,world.data(),12);Read(in,bones[0].data(),96);
            u32 count,slots;Read(in,&count);Read(in,&slots);if(slots<1||slots>8||count>4096)throw std::runtime_error("Reference bounds");
            Lighting::State state{};Lighting::ComputeState(&state,false);
            for(unsigned i=0;i<count;++i){
                float values[16];Read(in,values,16);
                T3BGE::Vertex v{{values[0],values[1],values[2]},{values[3],values[4],values[5]}, {}};
                std::memcpy(v.weights.data(),values+6,32);
                alignas(16) float skin[16]{};
                for(unsigned j=0;j<slots;++j)if(v.weights[j]!=0){
                    const __m128 weight=_mm_set1_ps(v.weights[j]);
                    for(int k=0;k<12;k+=4)_mm_store_ps(skin+k,_mm_add_ps(_mm_load_ps(skin+k),_mm_mul_ps(_mm_loadu_ps(bones[j].data()+k),weight)));
                }
                Vec3f p=Vec3ByMatrix43(Vec3f(v.position.data()),skin);
                Vec3f n=Norm3ByMatrix43(Vec3f(v.normal.data()),skin);
                if(regs[0x51]&1)n=-n;
                Vec3f wp=Vec3ByMatrix43(p,world.data()),wn=Norm3ByMatrix43(n,world.data());wn.NormalizeOr001();
                VertexData vertex{};vertex.color0=gstate.getMaterialAmbientRGBA();Lighting::Process(vertex,wp,wn,state);
                T3BGE::Transformed t{{wp.x,wp.y,wp.z},{wn.x,wn.y,wn.z}};
                T3BGE::Colors c{};for(unsigned k=0;k<4;++k)c.primary[k]=(vertex.color0>>(8*k))&255;
                for(unsigned k=0;k<3;++k)c.secondary[k]=(vertex.color1>>(8*k))&255;
                const auto actual=T3BGE::Transform(v,bones,slots,world,regs[0x51]&1);
                const auto colors=T3BGE::Light(regs,actual.worldPosition,actual.unitWorldNormal);
                transformDiff+=std::memcmp(actual.worldPosition.data(),t.worldPosition.data(),12)!=0||std::memcmp(actual.unitWorldNormal.data(),t.unitWorldNormal.data(),12)!=0;
                const bool different=colors.primary!=c.primary||colors.secondary!=c.secondary;
                if(different&&colorDiff<5)std::cerr<<"color mismatch draw="<<draw<<" vertex="<<i<<"\n";
                colorDiff+=different;
                for(unsigned k=0;k<4;++k)maxColorDiff=std::max(maxColorDiff,unsigned(std::abs(int(colors.primary[k])-int(c.primary[k]))));
                Write(official,t,c);Write(own,actual,colors);++vertices;
            }
        }
        if(std::fgetc(in)!=EOF)throw std::runtime_error("Trailing reference bytes");
        std::fclose(in);std::fclose(official);std::fclose(own);
        std::cout<<"{\"draws\":"<<draws<<",\"vertices\":"<<vertices<<",\"transform_vertex_bit_mismatches\":"<<transformDiff<<",\"color_vertex_mismatches\":"<<colorDiff<<",\"max_primary_channel_difference\":"<<maxColorDiff<<"}\n";
        return transformDiff||colorDiff?1:0;
    }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 3;}
}
