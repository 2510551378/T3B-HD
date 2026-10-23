// Headless isolated D3D11 validation of production tint/patch/decode against GE input.
// The adapter renames only the legacy executable entry point; GPU classes/shader
// remain the previously verified source-state implementation.
#include "ge_strip_fx_reference_adapter.cpp"
#include "T3BGEEffectVertexColor.h"
#include "T3BGEEffectGeometry.h"

struct FramePaths { ObservedFrame ge,runtime,previous; };
struct InputSet { std::vector<Texture> textures;std::vector<FramePaths> frames; };

std::string CheckPaletteGPUState(ObservedGPU& gpu,const ObservedDraw& draw,const std::string& label){
    Com<ID3D11RasterizerState> raster;gpu.context->RSGetState(raster.put());D3D11_RASTERIZER_DESC r{};raster->GetDesc(&r);
    Check(r.CullMode==((draw.flags&4)?D3D11_CULL_BACK:D3D11_CULL_NONE)&&r.FrontCounterClockwise==BOOL(!(draw.flags&16384))&&
          r.DepthClipEnable==BOOL(!(draw.flags&64)),"Actual palette rasterizer state differs");
    Com<ID3D11SamplerState> sampler;gpu.context->PSGetSamplers(0,1,sampler.put());D3D11_SAMPLER_DESC s{};sampler->GetDesc(&s);
    Check(s.Filter==D3D11_FILTER_MIN_MAG_MIP_LINEAR&&s.AddressU==((draw.flags&256)?D3D11_TEXTURE_ADDRESS_CLAMP:D3D11_TEXTURE_ADDRESS_WRAP)&&
          s.AddressV==((draw.flags&512)?D3D11_TEXTURE_ADDRESS_CLAMP:D3D11_TEXTURE_ADDRESS_WRAP)&&s.MaxLOD==0,"Actual palette sampler state differs");
    Com<ID3D11ShaderResourceView> view;gpu.context->PSGetShaderResources(0,1,view.put());Check(view.get()==gpu.textures[draw.texture]->get(),"Actual palette texture binding differs");
    return "{\"label\":\""+label+"\",\"flags\":"+std::to_string(draw.flags)+",\"texture\":"+std::to_string(draw.texture)+
        ",\"cull\":"+std::to_string(r.CullMode)+",\"front_ccw\":"+std::to_string(r.FrontCounterClockwise)+",\"depth_clip\":"+std::to_string(r.DepthClipEnable)+
        ",\"filter\":"+std::to_string(s.Filter)+",\"address_u\":"+std::to_string(s.AddressU)+",\"address_v\":"+std::to_string(s.AddressV)+",\"max_lod\":0}";
}

std::vector<Vertex> ExpandEffect(const T3BGE::EffectGeometry& mesh){
    std::vector<Vertex> result;
    for(auto index:mesh.triangleIndices){
        const auto& source=mesh.vertices[index];Vertex vertex{};
        for(unsigned k=0;k<3;++k)vertex.position[k]=source.position[k];
        for(unsigned k=0;k<2;++k)vertex.uv[k]=source.uv[k];
        for(unsigned k=0;k<4;++k)vertex.color[k]=static_cast<float>(source.color[k])/255.0f;
        result.push_back(vertex);
    }
    return result;
}
InputSet LoadPaletteGPU(const std::vector<std::uint8_t>& raw,const std::string& out){
    Reader reader(raw);char magic[8];reader.Copy(magic,8);Check(!std::memcmp(magic,"T3BPCG1\0",8),"Wrong palette GPU transport");
    const auto width=reader.U32(),height=reader.U32(),frameCount=reader.U32(),textureCount=reader.U32();
    Check(width==480&&height==272&&frameCount>0&&frameCount<=16&&textureCount>0&&textureCount<=16,"Palette GPU scope bound");InputSet input;
    for(UINT i=0;i<textureCount;++i){
        Texture t{};t.w=reader.U32();t.h=reader.U32();Check(t.w>0&&t.h>0&&t.w<=4096&&t.h<=4096,"Palette GPU texture extent");
        t.rgba.resize(size_t(t.w)*t.h*4);reader.Copy(t.rgba.data(),t.rgba.size());input.textures.push_back(std::move(t));
    }
    for(UINT i=0;i<frameCount;++i){
        const auto sample=reader.U32(),draws=reader.U32();Check(sample==i&&draws>0&&draws<=64,"Palette GPU frame scope");
        FramePaths f{};f.ge.sample=f.runtime.sample=f.previous.sample=sample;
        for(UINT j=0;j<draws;++j){
            ObservedDraw d{};d.texture=reader.U32();d.ordinal=j;d.flags=reader.U32();d.stencilRef=reader.U32();
            Check(d.texture<textureCount&&d.flags<32768&&d.stencilRef<=255,"Palette GPU draw state");
            reader.Copy(d.parameters.matrix,64);reader.Copy(d.parameters.fog,16);reader.Copy(d.parameters.fogRGB,16);
            d.parameters.control[0]=j+1;d.parameters.control[1]=(d.flags&8)?1:0;d.parameters.control[2]=(d.flags&16)?1:0;
            T3BGE::Registers r{};reader.Copy(r.data(),r.size()*4);
            const auto vt=reader.U32(),n=reader.U32(),mode=reader.U32(),paletteBytes=reader.U32();
            Check(vt==0x11e&&n>=3&&n<=4096&&mode<=255&&paletteBytes>0&&paletteBytes<=4096*4,"Palette GPU operand scope");
            T3BGE::EffectRGBA source{},parent{};reader.Copy(source.data(),16);reader.Copy(parent.data(),16);
            std::vector<std::uint8_t> palette(paletteBytes);reader.Copy(palette.data(),palette.size());
            std::vector<std::uint32_t> references(n);reader.Copy(references.data(),references.size()*4);
            std::vector<std::uint8_t> before(n*16),after(n*16);reader.Copy(before.data(),before.size());reader.Copy(after.data(),after.size());
            const auto previousMesh=T3BGE::DecodeOriginalEffectStrip(vt,n,before,r);
            const auto color=T3BGE::ProcessOriginalEffectColorMode(T3BGE::ModulateOriginalEffectRGBA(source,parent),static_cast<std::uint8_t>(mode));
            const auto converted=T3BGE::ModulateOriginalEffectVertexPalette(palette,color);auto patched=before;
            T3BGE::PatchOriginalEffectVertexColors(vt,patched,references,converted);Check(patched==after,"Production patched bytes differ from original GE");
            const auto mesh=T3BGE::DecodeOriginalEffectStrip(vt,n,patched,r);auto produced=ExpandEffect(mesh);
            const auto count=reader.U32();Check(count==produced.size()&&count<=65535,"Palette GPU triangle expansion count");
            std::vector<Vertex> original(count);reader.Copy(original.data(),original.size()*sizeof(Vertex));
            Check(std::memcmp(original.data(),produced.data(),produced.size()*sizeof(Vertex))==0,"Production upload attributes differ from original GE");
            const auto stem=out+"/sample_"+std::to_string(i)+"_draw_"+std::to_string(j);
            Save(stem+"_production_palette.rgba",converted.data(),converted.size());Save(stem+"_production_vertices.bin",patched.data(),patched.size());
            d.count=count;d.vertices=std::move(original);f.ge.draws.push_back(d);
            d.vertices=std::move(produced);f.runtime.draws.push_back(d);
            d.vertices=ExpandEffect(previousMesh);f.previous.draws.push_back(std::move(d));
        }
        input.frames.push_back(std::move(f));
    }
    reader.End();return input;
}
int main(int argc,char** argv){
    try{
        if(argc!=4)return 2;
        const std::string out=argv[3];
        const auto input=LoadPaletteGPU(Read(argv[1]),out);ObservedGPU gpu(480,272,Read(argv[2]),out);
        for(size_t i=0;i<input.textures.size();++i)gpu.AddTexture(input.textures[i],out+"/atlas_"+std::to_string(i)+"_actual.rgba");
        const auto white=static_cast<UINT>(input.textures.size());gpu.AddTexture({1,1,{255,255,255,255}},out+"/white_actual.rgba");
        std::vector<std::string> captures,states;
        for(const auto& f:input.frames){
            gpu.Stream(f.ge,out+"/ge");gpu.Stream(f.runtime,out+"/runtime");gpu.Stream(f.previous,out+"/previous");
            const auto stem="sample_"+std::to_string(f.ge.sample);
            captures.push_back(gpu.CaptureObserved(f.ge,"source_states",stem+"_ge",out));
            states.push_back(CheckPaletteGPUState(gpu,f.ge.draws.back(),stem+"_ge"));
            captures.push_back(gpu.CaptureObserved(f.runtime,"source_states",stem+"_runtime",out));
            states.push_back(CheckPaletteGPUState(gpu,f.runtime.draws.back(),stem+"_runtime"));
            captures.push_back(gpu.CaptureObserved(f.previous,"source_states",stem+"_previous",out));
            states.push_back(CheckPaletteGPUState(gpu,f.previous.draws.back(),stem+"_previous"));
            auto noTexture=f.runtime;for(auto& d:noTexture.draws)d.texture=white;
            captures.push_back(gpu.CaptureObserved(noTexture,"source_states",stem+"_no_texture",out));
            states.push_back(CheckPaletteGPUState(gpu,noTexture.draws.back(),stem+"_no_texture"));
        }
        captures.push_back(gpu.CaptureObserved(DoubleAlphaControl(white,2),"source_states","additive_calibration",out,true));
        std::string report="{\"passed\":true,\"pid\":"+std::to_string(GetCurrentProcessId())+",\"adapter\":\""+gpu.adapter+"\",\"captures\":[";
        for(size_t i=0;i<captures.size();++i){if(i)report+=',';report+=captures[i];}report+="],\"actual_state_checks\":[";
        for(size_t i=0;i<states.size();++i){if(i)report+=',';report+=states[i];}report+="]}";
        Save(out+"/actual_gpu_report.json",report.data(),report.size());std::cout<<"{\"passed\":true,\"captures\":"<<captures.size()<<"}\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
