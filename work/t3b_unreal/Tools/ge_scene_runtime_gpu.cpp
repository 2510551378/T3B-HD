#include "ge_strip_fx_reference_adapter.cpp"
#include "T3BGEScene.h"
int main(int argc,char** argv){
    try{
        if(argc!=5)return 2;
        const std::string out=argv[4];const auto scene=T3BGE::LoadSceneGeometry(Read(argv[1]));const auto bindings=T3BGE::LoadSceneEffectBindings(Read(argv[2]));
        ObservedGPU gpu(scene.width,scene.height,Read(argv[3]),out);
        for(std::size_t i=0;i<scene.atlases.size();++i){const auto& a=scene.atlases[i];gpu.AddTexture({a.width,a.height,a.rgba},out+"/atlas_"+std::to_string(i)+"_actual.rgba");}
        std::vector<std::string> captures;
        for(std::uint32_t i=0;i<scene.frames.size();++i){
            const auto frame=T3BGE::EvaluateSceneFrame(scene,i,&bindings);ObservedFrame f{};f.sample=frame.sample;
            for(const auto& d:frame.draws){ObservedDraw v{};v.texture=d.texture;v.ordinal=d.ordinal;v.flags=d.flags;v.count=d.vertices.size();v.stencilRef=d.stencilRef;
                std::memcpy(v.parameters.matrix,d.localToClip.data(),64);std::memcpy(v.parameters.fog,d.fog.data(),16);std::memcpy(v.parameters.fogRGB,d.fogRGB.data(),16);
                v.parameters.control[0]=d.ordinal+1;v.parameters.control[1]=(d.flags&8)?1:0;v.parameters.control[2]=(d.flags&16)?1:0;
                v.vertices.resize(d.vertices.size());static_assert(sizeof(Vertex)==sizeof(T3BGE::GPUVertex),"Scene vertex ABI");std::memcpy(v.vertices.data(),d.vertices.data(),d.vertices.size()*sizeof(Vertex));f.draws.push_back(std::move(v));
            }
            gpu.Stream(f,out);captures.push_back(gpu.CaptureObserved(f,"source_states","sample_"+std::to_string(i)+"_runtime",out));
        }
        std::string report="{\"passed\":true,\"pid\":"+std::to_string(GetCurrentProcessId())+",\"adapter\":\""+gpu.adapter+"\",\"captures\":[";
        for(std::size_t i=0;i<captures.size();++i){if(i)report+=',';report+=captures[i];}report+="]}";Save(out+"/actual_gpu_report.json",report.data(),report.size());std::cout<<"{\"passed\":true,\"captures\":"<<captures.size()<<"}\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
