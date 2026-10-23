// Own headless device; source-state reference, not a complete PSP emulator.
#define main T3BLegacyCalibrationMain
#include "ge_depth_reference.cpp"
#undef main
#include <algorithm>
#include <cmath>

struct Params { float matrix[16],fog[4]; UINT control[4],fogRGB[4]; };
static_assert(sizeof(Params)==112,"Observed shader constants");
struct ObservedDraw { UINT texture,ordinal,flags,count,stencilRef; Params parameters{}; std::vector<Vertex> vertices; };
struct ObservedFrame { UINT sample; std::vector<ObservedDraw> draws; };
struct Model { UINT width,height; std::vector<Texture> textures; std::vector<ObservedFrame> frames; };
class Reader {
    const std::vector<std::uint8_t>& bytes; size_t at=0;
public:
    explicit Reader(const std::vector<std::uint8_t>& b):bytes(b) { Check(b.size()<=256*1024*1024,"Input too large"); }
    void Copy(void* out,size_t n) { Check(n<=bytes.size()-at,"Truncated input");std::memcpy(out,bytes.data()+at,n);at+=n; }
    UINT U32() { UINT value;Copy(&value,4);return value; }
    void End() { Check(at==bytes.size(),"Trailing input"); }
};
Model Load(const std::vector<std::uint8_t>& raw) {
    Reader r(raw);char magic[8];r.Copy(magic,8);Check(!std::memcmp(magic,"T3BGEF1\0",8),"Wrong observed input");
    Model m{};m.width=r.U32();m.height=r.U32();UINT frames=r.U32(),textures=r.U32();
    Check(m.width==480&&m.height==272&&frames==12&&textures>0&&textures<=256,"Unsupported input extent");
    for(UINT i=0;i<textures;++i) {
        Texture t{};t.w=r.U32();t.h=r.U32();Check(t.w>0&&t.h>0&&t.w<=4096&&t.h<=4096,"Texture dimensions");
        t.rgba.resize(size_t(t.w)*t.h*4);r.Copy(t.rgba.data(),t.rgba.size());m.textures.push_back(std::move(t));
    }
    for(UINT i=0;i<frames;++i) {
        ObservedFrame f{};f.sample=r.U32();UINT count=r.U32();Check(f.sample==i&&count>0&&count<=4096,"Frame bounds");
        for(UINT j=0;j<count;++j) {
            ObservedDraw d{};d.texture=r.U32();d.ordinal=r.U32();d.flags=r.U32();d.count=r.U32();d.stencilRef=r.U32();
            Check(d.texture<textures&&d.ordinal==j&&d.flags<256&&d.count>0&&d.count<=65535&&d.count%3==0&&
                d.stencilRef<=255&&(!(d.flags&32)||d.stencilRef==0),"Draw bounds/state");
            r.Copy(d.parameters.matrix,64);r.Copy(d.parameters.fog,16);r.Copy(d.parameters.fogRGB,16);
            for(float v:d.parameters.matrix)Check(std::isfinite(v),"Nonfinite projection");
            for(float v:d.parameters.fog)Check(std::isfinite(v),"Nonfinite fog plane");
            d.parameters.control[0]=j+1;d.parameters.control[1]=(d.flags&8)?1:0;d.parameters.control[2]=(d.flags&16)?1:0;
            d.vertices.resize(d.count);r.Copy(d.vertices.data(),d.vertices.size()*sizeof(Vertex));
            for(const auto& v:d.vertices) {
                for(float x:v.position)Check(std::isfinite(x),"Nonfinite position");
                for(float x:v.uv)Check(std::isfinite(x),"Nonfinite UV");
                for(float x:v.color)Check(std::isfinite(x)&&x>=0&&x<=1,"Invalid vertex colour");
            }
            f.draws.push_back(std::move(d));
        }
        m.frames.push_back(std::move(f));
    }
    r.End();return m;
}
class ObservedGPU:public GPU {
    std::array<Com<ID3D11BlendState>,2> blends;
    std::array<Com<ID3D11RasterizerState>,4> rasters;
    std::array<Com<ID3D11DepthStencilState>,4> depths;
    Com<ID3D11GeometryShader> stream;
public:
    ObservedGPU(UINT w,UINT h,const std::vector<std::uint8_t>& shader,const std::string& out):GPU(w,h,shader,out) {
        D3D11_BUFFER_DESC b{};b.ByteWidth=sizeof(Params);b.Usage=D3D11_USAGE_DEFAULT;b.BindFlags=D3D11_BIND_CONSTANT_BUFFER;
        HR(device->CreateBuffer(&b,nullptr,cb.put()),"Observed constants");
        MakeTarget(DXGI_FORMAT_D24_UNORM_S8_UINT,D3D11_BIND_DEPTH_STENCIL,depth);
        HR(device->CreateDepthStencilView(depth.get(),nullptr,depthView.put()),"D24S8 view");
        for(UINT i=0;i<2;++i) {
            D3D11_BLEND_DESC d{};d.IndependentBlendEnable=TRUE;auto& t=d.RenderTarget[0];
            t.BlendEnable=i;t.SrcBlend=D3D11_BLEND_SRC_ALPHA;t.DestBlend=D3D11_BLEND_INV_SRC_ALPHA;t.BlendOp=D3D11_BLEND_OP_ADD;
            t.SrcBlendAlpha=D3D11_BLEND_ONE;t.DestBlendAlpha=D3D11_BLEND_ZERO;t.BlendOpAlpha=D3D11_BLEND_OP_ADD;t.RenderTargetWriteMask=7;
            d.RenderTarget[1].RenderTargetWriteMask=1;HR(device->CreateBlendState(&d,blends[i].put()),"Observed blend");
        }
        for(UINT i=0;i<4;++i) {
            D3D11_RASTERIZER_DESC r{};r.FillMode=D3D11_FILL_SOLID;r.CullMode=(i&1)?D3D11_CULL_BACK:D3D11_CULL_NONE;
            r.FrontCounterClockwise=TRUE;r.DepthClipEnable=(i&2)?FALSE:TRUE;
            HR(device->CreateRasterizerState(&r,rasters[i].put()),"Observed cull/clamp");
            D3D11_DEPTH_STENCIL_DESC d{};d.DepthEnable=TRUE;d.DepthFunc=D3D11_COMPARISON_GREATER_EQUAL;
            d.DepthWriteMask=(i&1)?D3D11_DEPTH_WRITE_MASK_ALL:D3D11_DEPTH_WRITE_MASK_ZERO;
            d.StencilEnable=(i&2)?TRUE:FALSE;d.StencilReadMask=0;d.StencilWriteMask=255;
            d.FrontFace.StencilFunc=D3D11_COMPARISON_ALWAYS;d.FrontFace.StencilFailOp=D3D11_STENCIL_OP_ZERO;
            d.FrontFace.StencilDepthFailOp=d.FrontFace.StencilPassOp=D3D11_STENCIL_OP_REPLACE;d.BackFace=d.FrontFace;
            HR(device->CreateDepthStencilState(&d,depths[i].put()),"Observed depth/stencil");
        }
        auto code=Read(out+"/actual_vs.dxbc");const UINT stride=44;
        D3D11_SO_DECLARATION_ENTRY s[]={{0,"SV_Position",0,0,4,0},{0,"TEXCOORD",0,0,2,0},{0,"COLOR",0,0,4,0},{0,"TEXCOORD",1,0,1,0}};
        HR(device->CreateGeometryShaderWithStreamOutput(code.data(),code.size(),s,4,&stride,1,D3D11_SO_NO_RASTERIZED_STREAM,nullptr,stream.put()),"Observed VS stream output");
    }
    void Bind(const ObservedDraw& d,bool noFog=false) {
        Params p=d.parameters;if(noFog)p.control[2]=0;
        context->UpdateSubresource(cb.get(),0,nullptr,&p,0,0);ID3D11Buffer* constant=cb.get();
        context->VSSetConstantBuffers(0,1,&constant);context->PSSetConstantBuffers(0,1,&constant);
        D3D11_BUFFER_DESC b{};b.ByteWidth=UINT(d.vertices.size()*sizeof(Vertex));b.Usage=D3D11_USAGE_IMMUTABLE;b.BindFlags=D3D11_BIND_VERTEX_BUFFER;
        D3D11_SUBRESOURCE_DATA initial{d.vertices.data(),0,0};Com<ID3D11Buffer> vb;HR(device->CreateBuffer(&b,&initial,vb.put()),"Observed vertex upload");
        ID3D11Buffer* buffer=vb.get();UINT stride=sizeof(Vertex),offset=0;context->IASetVertexBuffers(0,1,&buffer,&stride,&offset);
    }
    void Stream(const ObservedFrame& f,const std::string& out) {
        UINT count=0;for(const auto& d:f.draws)count+=d.count;
        Com<ID3D11Buffer> output,read;D3D11_BUFFER_DESC b{};b.ByteWidth=count*44;b.Usage=D3D11_USAGE_DEFAULT;b.BindFlags=D3D11_BIND_STREAM_OUTPUT;
        HR(device->CreateBuffer(&b,nullptr,output.put()),"Observed SO buffer");b.Usage=D3D11_USAGE_STAGING;b.BindFlags=0;b.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
        HR(device->CreateBuffer(&b,nullptr,read.put()),"Observed SO staging");
        context->OMSetRenderTargets(0,nullptr,nullptr);context->IASetInputLayout(layout.get());context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_POINTLIST);
        context->VSSetShader(vs.get(),nullptr,0);context->GSSetShader(stream.get(),nullptr,0);ID3D11Buffer* target=output.get();UINT offset=0;
        context->SOSetTargets(1,&target,&offset);for(const auto& d:f.draws){Bind(d);context->Draw(d.count,0);}
        context->SOSetTargets(0,nullptr,nullptr);context->GSSetShader(nullptr,nullptr,0);context->CopyResource(read.get(),output.get());
        D3D11_MAPPED_SUBRESOURCE mapped{};HR(context->Map(read.get(),0,D3D11_MAP_READ,0,&mapped),"Observed SO Map");
        Save(out+"/sample_"+std::to_string(f.sample)+".clip_uv_color_fog_f32",mapped.pData,count*44);context->Unmap(read.get(),0);
    }
    std::string CaptureObserved(const ObservedFrame& f,const std::string& mode,const std::string& stem,const std::string& out,bool synthetic=false) {
        const float black[]={0,0,0,1},zero[]={0,0,0,0};context->ClearRenderTargetView(colorRT.get(),black);context->ClearRenderTargetView(ownerRT.get(),zero);
        context->ClearDepthStencilView(depthView.get(),D3D11_CLEAR_DEPTH|D3D11_CLEAR_STENCIL,0,0);
        ID3D11RenderTargetView* targets[]={colorRT.get(),ownerRT.get()};context->OMSetRenderTargets(2,targets,depthView.get());
        context->IASetInputLayout(layout.get());context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
        context->VSSetShader(vs.get(),nullptr,0);context->PSSetShader(ps.get(),nullptr,0);
        ID3D11SamplerState* ss=sampler.get();context->PSSetSamplers(0,1,&ss);D3D11_VIEWPORT vp{0,0,float(width),float(height),0,1};context->RSSetViewports(1,&vp);
        UINT draws=0;
        for(const auto& d:f.draws) {
            bool bg=(d.flags&128)!=0;if((mode=="no_background"&&bg)||(mode=="background_only"&&!bg))continue;
            const UINT blend=(d.flags&1)?1:0,raster=((d.flags&4)?1:0)|((d.flags&64)?2:0);
            const UINT ds=((d.flags&2)&&mode!="no_depth_writes"?1:0)|((d.flags&32)?2:0);
            context->OMSetBlendState(blends[blend].get(),nullptr,0xffffffff);context->RSSetState(rasters[raster].get());
            context->OMSetDepthStencilState(depths[ds].get(),d.stencilRef);Bind(d,mode=="no_fog");
            ID3D11ShaderResourceView* srv=textures[d.texture]->get();context->PSSetShaderResources(0,1,&srv);context->Draw(d.count,0);
            Com<ID3D11DepthStencilState> actual;UINT ref;context->OMGetDepthStencilState(actual.put(),&ref);D3D11_DEPTH_STENCIL_DESC actualDS{};actual->GetDesc(&actualDS);
            Check(ref==d.stencilRef&&actualDS.DepthWriteMask==((ds&1)?D3D11_DEPTH_WRITE_MASK_ALL:D3D11_DEPTH_WRITE_MASK_ZERO)&&
                actualDS.StencilEnable==BOOL((ds&2)!=0)&&actualDS.DepthFunc==D3D11_COMPARISON_GREATER_EQUAL,"Actual depth/stencil differs");++draws;
        }
        context->OMSetRenderTargets(0,nullptr,nullptr);const auto rgb=Readback(color.get(),width*4),ids=Readback(owner.get(),width*4),z=Readback(depth.get(),width*4);
        Save(out+"/"+stem+".rgba",rgb.data(),rgb.size());Save(out+"/"+stem+".owner_u32",ids.data(),ids.size());Save(out+"/"+stem+".depth_stencil_u32",z.data(),z.size());
        return "{\"sample\":"+std::to_string(f.sample)+",\"mode\":\""+mode+"\",\"stem\":\""+stem+"\",\"draws\":"+std::to_string(draws)+",\"synthetic\":"+(synthetic?"true":"false")+"}";
    }
};
ObservedFrame Control(UINT texture,float fog,bool stencilFail=false) {
    ObservedFrame frame{0,{}};
    for(UINT i=0;i<(stencilFail?2U:1U);++i) {
        ObservedDraw d{};d.texture=texture;d.ordinal=i;d.flags=2|16|32;d.count=3;d.stencilRef=stencilFail?(i?73:11):0;
        for(int j=0;j<4;++j)d.parameters.matrix[j*5]=1;
        d.parameters.fog[3]=fog;
        d.parameters.control[0]=i+1;d.parameters.control[2]=1;d.parameters.fogRGB[0]=68;d.parameters.fogRGB[1]=112;d.parameters.fogRGB[2]=142;
        const float points[3][2]={{-.75f,-.75f},{-.75f,.75f},{.75f,-.75f}};
        for(const auto& p:points)d.vertices.push_back({{p[0],p[1],stencilFail?(i?.2f:.8f):.5f},{.5f,.5f},{.5f,.25f,.75f,1}});
        frame.draws.push_back(std::move(d));
    }
    return frame;
}
int main(int argc,char** argv) {
    try {
        if(argc!=4)return 2;
        const std::string out=argv[3];const auto model=Load(Read(argv[1]));ObservedGPU gpu(model.width,model.height,Read(argv[2]),out);
        for(size_t i=0;i<model.textures.size();++i)gpu.AddTexture(model.textures[i],out+"/atlas_"+std::to_string(i)+"_actual.rgba");
        std::vector<std::string> captures;
        for(const auto& f:model.frames) {
            gpu.Stream(f,out);
            for(const char* mode:{"source_states","no_background","background_only","no_fog","no_depth_writes"})
                captures.push_back(gpu.CaptureObserved(f,mode,"sample_"+std::to_string(f.sample)+"_"+mode,out));
        }
        const UINT white=UINT(model.textures.size());gpu.AddTexture({1,1,{255,255,255,255}},out+"/control_white.rgba");
        for(int i=0;i<3;++i)captures.push_back(gpu.CaptureObserved(Control(white,float(i)/2),"source_states","fog_control_"+std::to_string(i),out,true));
        captures.push_back(gpu.CaptureObserved(Control(white,.5f,true),"source_states","stencil_depth_fail_control",out,true));
        std::string report="{\"passed\":true,\"pid\":"+std::to_string(GetCurrentProcessId())+",\"adapter\":\""+gpu.adapter+
            "\",\"width\":480,\"height\":272,\"depth_format\":\"D24_UNORM_S8_UINT\",\"UE_executed\":false,\"captures\":[";
        for(size_t i=0;i<captures.size();++i){if(i)report+=',';report+=captures[i];}report+="]}";
        Save(out+"/actual_gpu_report.json",report.data(),report.size());std::cout<<"{\"passed\":true,\"captures\":"<<captures.size()<<"}\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
