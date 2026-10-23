// Own D3D11 hardware device; tests the expanded project shader, not UE/RDG.
#include <windows.h>
#include <d3d11.h>
#include <d3d11shader.h>
#include <d3dcompiler.h>
#include <dxgi.h>
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

template<class T> struct Com {
    T* p = nullptr;
    ~Com() { if (p) p->Release(); }
    T* get() const { return p; }
    T** put() { if (p) p->Release(); p = nullptr; return &p; }
    T* operator->() const { return p; }
};
void HR(HRESULT h, const char* why) { if (FAILED(h)) throw std::runtime_error(std::string(why) + ":" + std::to_string(h)); }
std::vector<char> Read(const std::string& path) {
    std::ifstream f(path, std::ios::binary); if (!f) throw std::runtime_error("Missing input");
    return {(std::istreambuf_iterator<char>(f)), {}};
}
void Save(const std::string& path, const void* p, size_t n) {
    std::ofstream f(path, std::ios::binary); f.write(static_cast<const char*>(p), n);
    if (!f) throw std::runtime_error("Output write failed");
}
struct Vertex { float p[3], uv[2], color[4]; };
struct Constants { float matrix[16], exposure; UINT owner, padding[2]; };
static_assert(sizeof(Vertex) == 36 && sizeof(Constants) == 80, "Input/constant layout");
std::string Reflect(ID3DBlob* code) {
    Com<ID3D11ShaderReflection> r;
    HR(D3DReflect(code->GetBufferPointer(), code->GetBufferSize(), IID_ID3D11ShaderReflection,
                 reinterpret_cast<void**>(r.put())), "Reflect");
    D3D11_SHADER_DESC sd{}; HR(r->GetDesc(&sd), "Reflection desc"); std::string rows = "[";
    for (UINT i = 0; i < sd.ConstantBuffers; ++i) {
        auto* cb = r->GetConstantBufferByIndex(i); D3D11_SHADER_BUFFER_DESC bd{}; HR(cb->GetDesc(&bd), "CB desc");
        for (UINT j = 0; j < bd.Variables; ++j) {
            auto* v = cb->GetVariableByIndex(j); D3D11_SHADER_VARIABLE_DESC vd{}; HR(v->GetDesc(&vd), "Var desc");
            D3D11_SHADER_TYPE_DESC td{}; HR(v->GetType()->GetDesc(&td), "Type desc");
            if (rows.size() > 1) rows += ',';
            rows += "{\"name\":\"" + std::string(vd.Name) + "\",\"offset\":" + std::to_string(vd.StartOffset) +
                ",\"size\":" + std::to_string(vd.Size) + ",\"class\":" + std::to_string(td.Class) +
                ",\"used\":" + ((vd.uFlags & D3D_SVF_USED) ? "true" : "false") + "}";
        }
    }
    return rows + "]";
}
int main(int argc, char** argv) {
    try {
        if (argc != 3) return 2;
        const std::string out = argv[2]; const auto text = Read(argv[1]);
        Com<ID3DBlob> vsCode, psCode, errors;
        for (int stage = 0; stage < 2; ++stage) {
            HRESULT h = D3DCompile(text.data(), text.size(), nullptr, nullptr, nullptr,
                stage ? "MainPS" : "MainVS", stage ? "ps_5_0" : "vs_5_0",
                D3DCOMPILE_ENABLE_STRICTNESS | D3DCOMPILE_IEEE_STRICTNESS, 0,
                stage ? psCode.put() : vsCode.put(), errors.put());
            if (FAILED(h) && errors.get()) std::cerr << static_cast<const char*>(errors->GetBufferPointer());
            HR(h, "Actual project shader-body compilation");
        }
        Save(out + "/actual_vs.dxbc", vsCode->GetBufferPointer(), vsCode->GetBufferSize());
        Save(out + "/actual_ps.dxbc", psCode->GetBufferPointer(), psCode->GetBufferSize());
        Com<ID3D11Device> device; Com<ID3D11DeviceContext> ctx; D3D_FEATURE_LEVEL feature{};
        HR(D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, 0, nullptr, 0, D3D11_SDK_VERSION,
                            device.put(), &feature, ctx.put()), "Hardware device");
        Com<IDXGIDevice> dxgi; Com<IDXGIAdapter> adapter;
        HR(device->QueryInterface(__uuidof(IDXGIDevice), reinterpret_cast<void**>(dxgi.put())), "DXGI");
        HR(dxgi->GetAdapter(adapter.put()), "Adapter"); DXGI_ADAPTER_DESC ad{}; HR(adapter->GetDesc(&ad), "Adapter desc");
        char name[512]{}; WideCharToMultiByte(CP_UTF8, 0, ad.Description, -1, name, sizeof name, nullptr, nullptr);
        Com<ID3D11VertexShader> vs; Com<ID3D11PixelShader> ps; Com<ID3D11InputLayout> layout;
        HR(device->CreateVertexShader(vsCode->GetBufferPointer(), vsCode->GetBufferSize(), nullptr, vs.put()), "VS");
        HR(device->CreatePixelShader(psCode->GetBufferPointer(), psCode->GetBufferSize(), nullptr, ps.put()), "PS");
        D3D11_INPUT_ELEMENT_DESC elements[] = {
            {"ATTRIBUTE",0,DXGI_FORMAT_R32G32B32_FLOAT,0,0,D3D11_INPUT_PER_VERTEX_DATA,0},
            {"ATTRIBUTE",1,DXGI_FORMAT_R32G32_FLOAT,0,12,D3D11_INPUT_PER_VERTEX_DATA,0},
            {"ATTRIBUTE",2,DXGI_FORMAT_R32G32B32A32_FLOAT,0,20,D3D11_INPUT_PER_VERTEX_DATA,0}};
        HR(device->CreateInputLayout(elements, 3, vsCode->GetBufferPointer(), vsCode->GetBufferSize(), layout.put()), "Layout");
        Com<ID3D11Buffer> cb; D3D11_BUFFER_DESC bd{}; bd.ByteWidth = sizeof(Constants);
        bd.Usage = D3D11_USAGE_DEFAULT; bd.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
        HR(device->CreateBuffer(&bd, nullptr, cb.put()), "Constants");
        ID3D11Buffer* c = cb.get(); ctx->VSSetConstantBuffers(0,1,&c); ctx->PSSetConstantBuffers(0,1,&c);
        ctx->VSSetShader(vs.get(), nullptr, 0); ctx->IASetInputLayout(layout.get());
        auto upload = [&](const std::vector<Vertex>& v, Com<ID3D11Buffer>& vb) {
            D3D11_BUFFER_DESC d{}; d.ByteWidth = UINT(v.size() * sizeof(Vertex)); d.Usage = D3D11_USAGE_IMMUTABLE;
            d.BindFlags = D3D11_BIND_VERTEX_BUFFER; D3D11_SUBRESOURCE_DATA initial{v.data(),0,0};
            HR(device->CreateBuffer(&d,&initial,vb.put()), "Vertices");
            ID3D11Buffer* b = vb.get(); UINT stride = sizeof(Vertex), offset = 0; ctx->IASetVertexBuffers(0,1,&b,&stride,&offset);
        };
        const std::vector<Vertex> points = {
            {{0,0,0},{0,.25f},{.125f,.25f,.5f,1}}, {{1,2,3},{.5f,.75f},{1,.5f,.25f,.125f}},
            {{-17,600,88},{1,-1},{0,1,0,.5f}}, {{35,-600,123},{.125f,.375f},{.75f,.25f,.5f,.25f}},
            {{-90,3,223},{.25f,.5f},{.25f,.5f,.75f,1}}};
        Save(out + "/vertex_inputs.bin", points.data(), points.size()*sizeof(Vertex));
        D3D11_SO_DECLARATION_ENTRY so[] = {{0,"SV_Position",0,0,4,0},{0,"TEXCOORD",0,0,2,0},{0,"COLOR",0,0,4,0}};
        const UINT soStride = 40; Com<ID3D11GeometryShader> stream;
        HR(device->CreateGeometryShaderWithStreamOutput(vsCode->GetBufferPointer(), vsCode->GetBufferSize(), so,3,
            &soStride,1,D3D11_SO_NO_RASTERIZED_STREAM,nullptr,stream.put()), "Stream-out VS");
        Com<ID3D11Buffer> soBuffer, soRead;
        bd.ByteWidth = UINT(points.size()*soStride); bd.BindFlags = D3D11_BIND_STREAM_OUTPUT;
        HR(device->CreateBuffer(&bd,nullptr,soBuffer.put()), "Stream output buffer");
        bd.BindFlags = 0; bd.Usage = D3D11_USAGE_STAGING; bd.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
        HR(device->CreateBuffer(&bd,nullptr,soRead.put()), "Stream readback");
        for (int test = 0; test < 3; ++test) {
            Constants k{};
            if (test < 2) {
                float s = test ? -1.f : 1.f; k.matrix[0] = s*2.f/180.f; k.matrix[6] = s/2000.f;
                k.matrix[9] = 2.f/270.f; k.matrix[13] = -88.f*(2.f/270.f); k.matrix[14] = .5f; k.matrix[15] = 1.f;
            } else {
                const float oblique[16] = {1.25f,.125f,.03125f,.0625f, -.25f,.75f,.0625f,.03125f,
                    .5f,-.125f,.875f,.125f, 2,-3,.25f,4};
                for (int i = 0; i < 16; ++i) k.matrix[i] = oblique[i];
            }
            Save(out + "/matrix_" + std::to_string(test) + ".bin", k.matrix, sizeof k.matrix);
            ctx->UpdateSubresource(cb.get(),0,nullptr,&k,0,0); Com<ID3D11Buffer> vb; upload(points,vb);
            ctx->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_POINTLIST); ctx->GSSetShader(stream.get(),nullptr,0);
            ID3D11Buffer* target = soBuffer.get(); UINT offset = 0; ctx->SOSetTargets(1,&target,&offset);
            ctx->Draw(UINT(points.size()),0); ctx->SOSetTargets(0,nullptr,nullptr); ctx->CopyResource(soRead.get(),soBuffer.get());
            D3D11_MAPPED_SUBRESOURCE mapped{}; HR(ctx->Map(soRead.get(),0,D3D11_MAP_READ,0,&mapped), "VS GPU Map");
            Save(out + "/matrix_" + std::to_string(test) + "_actual.bin",mapped.pData,points.size()*soStride); ctx->Unmap(soRead.get(),0);
        }
        ctx->GSSetShader(nullptr,nullptr,0); ctx->PSSetShader(ps.get(),nullptr,0);
        Com<ID3D11RasterizerState> raster; D3D11_RASTERIZER_DESC rs{};
        rs.FillMode = D3D11_FILL_SOLID; rs.CullMode = D3D11_CULL_NONE; rs.DepthClipEnable = TRUE;
        HR(device->CreateRasterizerState(&rs,raster.put()), "Raster"); ctx->RSSetState(raster.get());
        D3D11_VIEWPORT vp{0,0,16,16,0,1}; ctx->RSSetViewports(1,&vp);
        Com<ID3D11DepthStencilState> depth; D3D11_DEPTH_STENCIL_DESC ds{}; ds.DepthEnable = FALSE;
        HR(device->CreateDepthStencilState(&ds,depth.put()), "No depth"); ctx->OMSetDepthStencilState(depth.get(),0);
        // No blending: inspect MainPS float output before scene alpha blending/tonemapping.
        ctx->OMSetBlendState(nullptr,nullptr,0xffffffff);
        Com<ID3D11Texture2D> color, owner, colorRead, ownerRead, atlas; Com<ID3D11RenderTargetView> cr, ow;
        auto target = [&](DXGI_FORMAT format, Com<ID3D11Texture2D>& t, Com<ID3D11Texture2D>& read, Com<ID3D11RenderTargetView>& view) {
            D3D11_TEXTURE2D_DESC d{}; d.Width=d.Height=16; d.MipLevels=d.ArraySize=d.SampleDesc.Count=1;
            d.Format=format; d.Usage=D3D11_USAGE_DEFAULT; d.BindFlags=D3D11_BIND_RENDER_TARGET;
            HR(device->CreateTexture2D(&d,nullptr,t.put()), "Target"); HR(device->CreateRenderTargetView(t.get(),nullptr,view.put()), "RTV");
            d.Usage=D3D11_USAGE_STAGING; d.BindFlags=0; d.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
            HR(device->CreateTexture2D(&d,nullptr,read.put()), "Readback texture");
        };
        target(DXGI_FORMAT_R32G32B32A32_FLOAT,color,colorRead,cr); target(DXGI_FORMAT_R32_UINT,owner,ownerRead,ow);
        const float texel[4] = {.25f,.5f,.75f,.5f}; D3D11_TEXTURE2D_DESC td{};
        td.Width=td.Height=td.MipLevels=td.ArraySize=td.SampleDesc.Count=1; td.Format=DXGI_FORMAT_R32G32B32A32_FLOAT;
        td.Usage=D3D11_USAGE_IMMUTABLE; td.BindFlags=D3D11_BIND_SHADER_RESOURCE;
        D3D11_SUBRESOURCE_DATA init{texel,sizeof texel,0}; HR(device->CreateTexture2D(&td,&init,atlas.put()), "Known float atlas");
        Com<ID3D11ShaderResourceView> srv; HR(device->CreateShaderResourceView(atlas.get(),nullptr,srv.put()), "Atlas SRV");
        ID3D11ShaderResourceView* sv=srv.get(); ctx->PSSetShaderResources(0,1,&sv);
        Com<ID3D11SamplerState> sampler; D3D11_SAMPLER_DESC sd{};
        sd.Filter=D3D11_FILTER_MIN_MAG_MIP_LINEAR; sd.AddressU=sd.AddressV=sd.AddressW=D3D11_TEXTURE_ADDRESS_WRAP;
        sd.MaxLOD=D3D11_FLOAT32_MAX; HR(device->CreateSamplerState(&sd,sampler.put()), "Sampler");
        ID3D11SamplerState* ss=sampler.get(); ctx->PSSetSamplers(0,1,&ss);
        for (int test=0; test<5; ++test) {
            Constants k{}; k.matrix[0]=k.matrix[5]=k.matrix[10]=k.matrix[15]=1;
            const float exposures[] = {.25f,1,2,8,2}; k.exposure=exposures[test]; k.owner=0x12345;
            ctx->UpdateSubresource(cb.get(),0,nullptr,&k,0,0);
            std::vector<Vertex> triangle = {{{-1,-1,.5f},{.5f,.5f},{.5f,.25f,.75f,.5f}},
                {{-1,3,.5f},{.5f,.5f},{.5f,.25f,.75f,.5f}},{{3,-1,.5f},{.5f,.5f},{.5f,.25f,.75f,.5f}}};
            if (test==4) for (auto& v:triangle) v.color[3]=0;
            Com<ID3D11Buffer> vb; upload(triangle,vb); ctx->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
            const float clear[4]={-7,-7,-7,-7}, zero[4]={0,0,0,0};
            ctx->ClearRenderTargetView(cr.get(),clear); ctx->ClearRenderTargetView(ow.get(),zero);
            ID3D11RenderTargetView* views[]={cr.get(),ow.get()}; ctx->OMSetRenderTargets(2,views,nullptr); ctx->Draw(3,0);
            ctx->OMSetRenderTargets(0,nullptr,nullptr);
            auto read = [&](ID3D11Texture2D* t, ID3D11Texture2D* staging, UINT rowBytes, const char* suffix) {
                ctx->CopyResource(staging,t); D3D11_MAPPED_SUBRESOURCE mapped{};
                HR(ctx->Map(staging,0,D3D11_MAP_READ,0,&mapped), "PS GPU Map"); std::vector<char> bytes(16*rowBytes);
                for (UINT y=0; y<16; ++y) std::copy_n(static_cast<const char*>(mapped.pData)+y*mapped.RowPitch,rowBytes,bytes.data()+y*rowBytes);
                ctx->Unmap(staging,0); Save(out+"/pixel_"+std::to_string(test)+suffix,bytes.data(),bytes.size());
            };
            read(color.get(),colorRead.get(),16*16,".rgba_f32"); read(owner.get(),ownerRead.get(),16*4,".owner_u32");
        }
        std::string report="{\"pid\":"+std::to_string(GetCurrentProcessId())+",\"adapter\":\""+name+
            "\",\"feature_level\":"+std::to_string(feature)+",\"vertex_reflection\":"+Reflect(vsCode.get())+
            ",\"pixel_reflection\":"+Reflect(psCode.get())+",\"matrix_cases\":3,\"pixel_cases\":5,\"UE_executed\":false}";
        Save(out+"/actual_gpu_report.json",report.data(),report.size()); std::cout << report << '\n'; return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
