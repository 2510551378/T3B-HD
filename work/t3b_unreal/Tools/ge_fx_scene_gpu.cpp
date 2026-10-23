// Actual same-frame scene composition using unchanged source-state D3D11 renderer.
#include "ge_effect_palette_gpu_adapter.cpp"

Model LoadSameFrameScene(const std::vector<std::uint8_t>& raw){
    Reader r(raw);char magic[8];r.Copy(magic,8);Check(!std::memcmp(magic,"T3BSFC1\0",8),"Wrong same-frame scene input");
    Model m{};m.width=r.U32();m.height=r.U32();const auto frames=r.U32(),textures=r.U32();
    Check(m.width==480&&m.height==272&&frames==3&&textures>0&&textures<=256,"Scene scope");
    for(UINT i=0;i<textures;++i){
        Texture t{};t.w=r.U32();t.h=r.U32();Check(t.w>0&&t.h>0&&t.w<=4096&&t.h<=4096,"Scene texture size");
        t.rgba.resize(size_t(t.w)*t.h*4);r.Copy(t.rgba.data(),t.rgba.size());m.textures.push_back(std::move(t));
    }
    for(UINT i=0;i<frames;++i){
        ObservedFrame f{};f.sample=r.U32();const auto count=r.U32();Check(f.sample==i&&count>135&&count<=4096,"Scene frame bounds");
        for(UINT j=0;j<count;++j){
            ObservedDraw d{};d.texture=r.U32();d.ordinal=r.U32();d.flags=r.U32();d.count=r.U32();d.stencilRef=r.U32();
            Check(d.texture<textures&&d.ordinal==j&&d.flags<32768&&d.count>0&&d.count<=65535&&d.count%3==0,"Scene draw bounds");
            r.Copy(d.parameters.matrix,64);r.Copy(d.parameters.fog,16);r.Copy(d.parameters.fogRGB,16);
            d.parameters.control[0]=j+1;d.parameters.control[1]=(d.flags&8)?1:0;d.parameters.control[2]=(d.flags&16)?1:0;
            d.vertices.resize(d.count);r.Copy(d.vertices.data(),d.vertices.size()*sizeof(Vertex));
            for(const auto& v:d.vertices){for(float p:v.position)Check(std::isfinite(p),"Scene position nonfinite");for(float c:v.color)Check(std::isfinite(c)&&c>=0&&c<=1,"Scene color invalid");}
            f.draws.push_back(std::move(d));
        }m.frames.push_back(std::move(f));
    }r.End();return m;
}
int main(int argc,char** argv){
    try{
        if(argc!=5)return 2;
        const std::string out=argv[4];const auto scene=LoadSameFrameScene(Read(argv[1]));const auto palettes=LoadPaletteGPU(Read(argv[2]),out);
        ObservedGPU gpu(480,272,Read(argv[3]),out);
        for(size_t i=0;i<scene.textures.size();++i)gpu.AddTexture(scene.textures[i],out+"/atlas_"+std::to_string(i)+"_actual.rgba");
        std::vector<std::string> captures;
        for(size_t i=0;i<scene.frames.size();++i){
            const auto& ge=scene.frames[i];auto runtime=ge,previous=ge;const auto& p=palettes.frames[i];size_t k=0,first=0,last=0;
            for(size_t j=0;j<runtime.draws.size();++j){
                auto& d=runtime.draws[j];if(!(d.flags&4096))continue;
                Check(k<8,"Extra target scene draw");const auto& original=p.ge.draws[k];
                Check(d.count==original.count&&d.flags==original.flags&&d.stencilRef==original.stencilRef,"Scene target source state differs");
                Check(!std::memcmp(d.parameters.matrix,original.parameters.matrix,64)&&!std::memcmp(d.parameters.fog,original.parameters.fog,16)&&
                      !std::memcmp(d.parameters.fogRGB,original.parameters.fogRGB,16),"Scene target original transform/fog differs");
                Check(!std::memcmp(d.vertices.data(),original.vertices.data(),d.vertices.size()*sizeof(Vertex)),"Scene target GE vertex source differs");
                const auto& t=scene.textures[d.texture];const auto& pt=palettes.textures[original.texture];Check(t.w==pt.w&&t.h==pt.h&&t.rgba==pt.rgba,"Scene target CLUT texture differs");
                d.vertices=p.runtime.draws[k].vertices;previous.draws[j].vertices=p.previous.draws[k].vertices;
                if(k==0)first=j;
                last=j;++k;
            }
            Check(k==8&&last-first==7,"Expected contiguous8 original effect draws");
            const auto stem="sample_"+std::to_string(i);gpu.Stream(runtime,out+"/runtime");gpu.Stream(ge,out+"/ge");
            captures.push_back(gpu.CaptureObserved(ge,"source_states",stem+"_ge",out));
            captures.push_back(gpu.CaptureObserved(runtime,"source_states",stem+"_runtime",out));
            captures.push_back(gpu.CaptureObserved(previous,"source_states",stem+"_previous",out));
            captures.push_back(gpu.CaptureObserved(runtime,"no_effects",stem+"_no_effect",out));
            captures.push_back(gpu.CaptureObserved(runtime,"effects_only",stem+"_isolated",out));
            auto prefix=runtime;prefix.draws.resize(first);
            captures.push_back(gpu.CaptureObserved(prefix,"source_states",stem+"_before_effect",out));
            prefix=runtime;prefix.draws.resize(last+1);
            captures.push_back(gpu.CaptureObserved(prefix,"source_states",stem+"_after_effect",out));
        }
        std::string report="{\"passed\":true,\"pid\":"+std::to_string(GetCurrentProcessId())+",\"adapter\":\""+gpu.adapter+"\",\"captures\":[";
        for(size_t i=0;i<captures.size();++i){if(i)report+=',';report+=captures[i];}report+="]}";
        Save(out+"/actual_gpu_report.json",report.data(),report.size());std::cout<<"{\"passed\":true,\"captures\":"<<captures.size()<<"}\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
