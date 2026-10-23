// Owned headless D3D11 test device. Does not borrow/modify a UE device or engine.
#include "T3BGEGeometry.h"
#include <windows.h>
#include <d3d11.h>
#include <d3dcompiler.h>
#include <dxgi.h>
#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

template<class T> class Com {
    T* p = nullptr;
public:
    ~Com() { if (p) p->Release(); }
    Com() = default; Com(const Com&) = delete; Com& operator=(const Com&) = delete;
    T* get() const { return p; }
    T** put() { if (p) p->Release(); p = nullptr; return &p; }
    T* operator->() const { return p; }
};
void Check(bool ok, const char* reason) { if (!ok) throw std::runtime_error(reason); }
void HR(HRESULT h, const char* reason) { if (FAILED(h)) { std::cerr << std::hex << h << std::dec << '\n'; throw std::runtime_error(reason); } }
std::vector<std::uint8_t> Read(const std::string& path) {
    std::ifstream f(path, std::ios::binary); Check(bool(f), "Input file missing");
    return std::vector<std::uint8_t>((std::istreambuf_iterator<char>(f)), {});
}
void Save(const std::string& path, const void* p, std::size_t n) {
    std::ofstream f(path, std::ios::binary); Check(bool(f), "Output open failed");
    f.write(static_cast<const char*>(p), n); Check(bool(f), "Output write failed");
}
using Vertex = T3BGE::GPUVertex;
static_assert(sizeof(Vertex) == 36, "GPU input packing");
struct Draw { std::uint32_t texture, sourceOrdinal; std::vector<Vertex> vertices; };
struct Sample { std::uint32_t index; std::vector<Draw> draws; };
struct Texture { std::uint32_t w{}, h{}; std::vector<std::uint8_t> rgba; };
struct Constants { float view[4]; std::uint32_t drawId, padding[3]; };
static_assert(sizeof(Constants) == 32, "HLSL constant packing");
struct WorldConstants { float matrix[16], exposure; std::uint32_t drawId, padding[2]; };
static_assert(sizeof(WorldConstants) == 80, "Project world shader constant packing");

class GPU {
public:
    Com<ID3D11Device> device; Com<ID3D11DeviceContext> context;
    Com<ID3D11VertexShader> vs; Com<ID3D11PixelShader> ps; Com<ID3D11InputLayout> layout;
    Com<ID3D11Buffer> cb; Com<ID3D11SamplerState> sampler;
    Com<ID3D11BlendState> blend; Com<ID3D11RasterizerState> raster, syntheticRaster;
    Com<ID3D11DepthStencilState> depthOn, depthOff;
    Com<ID3D11Texture2D> color, owner, depth;
    Com<ID3D11RenderTargetView> colorRT, ownerRT; Com<ID3D11DepthStencilView> depthView;
    std::vector<Com<ID3D11ShaderResourceView>*> textures;
    UINT width, height; D3D_FEATURE_LEVEL feature{}; std::string adapter;
    bool worldShader = false; std::array<float,16> worldToClip{};
    GPU(UINT w, UINT h, const std::vector<std::uint8_t>& shader, const std::string& out, bool useWorldShader = false)
        : width(w), height(h), worldShader(useWorldShader) {
        HR(D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, 0, nullptr, 0, D3D11_SDK_VERSION,
                            device.put(), &feature, context.put()), "D3D11 hardware device creation failed");
        Com<IDXGIDevice> dxgi; Com<IDXGIAdapter> a;
        HR(device->QueryInterface(__uuidof(IDXGIDevice), reinterpret_cast<void**>(dxgi.put())), "DXGI device query");
        HR(dxgi->GetAdapter(a.put()), "DXGI adapter"); DXGI_ADAPTER_DESC desc{}; HR(a->GetDesc(&desc), "DXGI adapter description");
        char utf[512]{}; WideCharToMultiByte(CP_UTF8, 0, desc.Description, -1, utf, sizeof utf, nullptr, nullptr); adapter = utf;
        Com<ID3DBlob> vb, pb, error;
        HRESULT hvs = D3DCompile(shader.data(), shader.size(), nullptr, nullptr, nullptr, worldShader ? "MainVS" : "VSMain", "vs_5_0",
                                D3DCOMPILE_ENABLE_STRICTNESS | D3DCOMPILE_IEEE_STRICTNESS, 0, vb.put(), error.put());
        if (FAILED(hvs) && error.get()) std::cerr << static_cast<const char*>(error->GetBufferPointer());
        HR(hvs, "Vertex shader compile failed");
        HRESULT hps = D3DCompile(shader.data(), shader.size(), nullptr, nullptr, nullptr, worldShader ? "MainPS" : "PSMain", "ps_5_0",
                                D3DCOMPILE_ENABLE_STRICTNESS | D3DCOMPILE_IEEE_STRICTNESS, 0, pb.put(), error.put());
        if (FAILED(hps) && error.get()) std::cerr << static_cast<const char*>(error->GetBufferPointer());
        HR(hps, "Pixel shader compile failed");
        Save(out + "/actual_vs.dxbc", vb->GetBufferPointer(), vb->GetBufferSize());
        Save(out + "/actual_ps.dxbc", pb->GetBufferPointer(), pb->GetBufferSize());
        HR(device->CreateVertexShader(vb->GetBufferPointer(), vb->GetBufferSize(), nullptr, vs.put()), "CreateVS");
        HR(device->CreatePixelShader(pb->GetBufferPointer(), pb->GetBufferSize(), nullptr, ps.put()), "CreatePS");
        D3D11_INPUT_ELEMENT_DESC elements[] = {{"POSITION",0,DXGI_FORMAT_R32G32B32_FLOAT,0,0,D3D11_INPUT_PER_VERTEX_DATA,0},
            {"TEXCOORD",0,DXGI_FORMAT_R32G32_FLOAT,0,12,D3D11_INPUT_PER_VERTEX_DATA,0},
            {"COLOR",0,DXGI_FORMAT_R32G32B32A32_FLOAT,0,20,D3D11_INPUT_PER_VERTEX_DATA,0}};
        if (worldShader) for (UINT i = 0; i < 3; ++i) { elements[i].SemanticName = "ATTRIBUTE"; elements[i].SemanticIndex = i; }
        HR(device->CreateInputLayout(elements, 3, vb->GetBufferPointer(), vb->GetBufferSize(), layout.put()), "Input layout");
        D3D11_BUFFER_DESC cbd{}; cbd.ByteWidth = worldShader ? sizeof(WorldConstants) : sizeof(Constants);
        cbd.Usage = D3D11_USAGE_DEFAULT; cbd.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
        HR(device->CreateBuffer(&cbd, nullptr, cb.put()), "Constant buffer");
        D3D11_SAMPLER_DESC sd{}; sd.Filter = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
        sd.AddressU = sd.AddressV = sd.AddressW = D3D11_TEXTURE_ADDRESS_WRAP; sd.MaxLOD = D3D11_FLOAT32_MAX;
        HR(device->CreateSamplerState(&sd, sampler.put()), "Linear sampler");
        D3D11_BLEND_DESC bd{}; bd.IndependentBlendEnable = TRUE;
        auto& b = bd.RenderTarget[0]; b.BlendEnable = TRUE; b.SrcBlend = D3D11_BLEND_SRC_ALPHA;
        b.DestBlend = D3D11_BLEND_INV_SRC_ALPHA; b.BlendOp = D3D11_BLEND_OP_ADD;
        b.SrcBlendAlpha = D3D11_BLEND_ONE; b.DestBlendAlpha = D3D11_BLEND_ZERO; b.BlendOpAlpha = D3D11_BLEND_OP_ADD;
        b.RenderTargetWriteMask = D3D11_COLOR_WRITE_ENABLE_RED | D3D11_COLOR_WRITE_ENABLE_GREEN | D3D11_COLOR_WRITE_ENABLE_BLUE;
        bd.RenderTarget[1].BlendEnable = FALSE; bd.RenderTarget[1].RenderTargetWriteMask = D3D11_COLOR_WRITE_ENABLE_RED;
        HR(device->CreateBlendState(&bd, blend.put()), "Original color-alpha blend state");
        D3D11_RASTERIZER_DESC rs{}; rs.FillMode = D3D11_FILL_SOLID; rs.CullMode = D3D11_CULL_BACK;
        rs.FrontCounterClockwise = TRUE; rs.DepthClipEnable = TRUE;
        HR(device->CreateRasterizerState(&rs, raster.put()), "Original single-face raster state");
        rs.CullMode = D3D11_CULL_NONE; HR(device->CreateRasterizerState(&rs, syntheticRaster.put()), "Synthetic raster state");
        D3D11_DEPTH_STENCIL_DESC ds{}; ds.DepthEnable = TRUE; ds.DepthFunc = D3D11_COMPARISON_GREATER_EQUAL;
        ds.DepthWriteMask = D3D11_DEPTH_WRITE_MASK_ALL;
        HR(device->CreateDepthStencilState(&ds, depthOn.put()), "Original depth state");
        ds.DepthWriteMask = D3D11_DEPTH_WRITE_MASK_ZERO;
        HR(device->CreateDepthStencilState(&ds, depthOff.put()), "No-depth-write control");
        MakeTarget(DXGI_FORMAT_R8G8B8A8_UNORM, D3D11_BIND_RENDER_TARGET, color);
        MakeTarget(DXGI_FORMAT_R32_UINT, D3D11_BIND_RENDER_TARGET, owner);
        MakeTarget(DXGI_FORMAT_D32_FLOAT, D3D11_BIND_DEPTH_STENCIL, depth);
        HR(device->CreateRenderTargetView(color.get(), nullptr, colorRT.put()), "Color RTV");
        HR(device->CreateRenderTargetView(owner.get(), nullptr, ownerRT.put()), "Owner RTV");
        HR(device->CreateDepthStencilView(depth.get(), nullptr, depthView.put()), "Depth DSV");
    }
    ~GPU() { for (auto* t : textures) delete t; }
    void MakeTarget(DXGI_FORMAT format, UINT bind, Com<ID3D11Texture2D>& target) {
        D3D11_TEXTURE2D_DESC d{}; d.Width = width; d.Height = height; d.MipLevels = d.ArraySize = 1;
        d.Format = format; d.SampleDesc.Count = 1; d.Usage = D3D11_USAGE_DEFAULT; d.BindFlags = bind;
        HR(device->CreateTexture2D(&d, nullptr, target.put()), "Offscreen GPU target");
    }
    std::vector<std::uint8_t> Readback(ID3D11Texture2D* texture, UINT rowBytes) {
        D3D11_TEXTURE2D_DESC d{}; texture->GetDesc(&d); d.Usage = D3D11_USAGE_STAGING;
        d.BindFlags = d.MiscFlags = 0; d.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
        Com<ID3D11Texture2D> stage; HR(device->CreateTexture2D(&d, nullptr, stage.put()), "Create readback staging");
        context->CopyResource(stage.get(), texture); D3D11_MAPPED_SUBRESOURCE mapped{};
        HR(context->Map(stage.get(), 0, D3D11_MAP_READ, 0, &mapped), "Actual GPU Map readback");
        Check(mapped.RowPitch >= rowBytes, "GPU row pitch invalid");
        std::vector<std::uint8_t> bytes(std::size_t(rowBytes) * d.Height);
        for (UINT y = 0; y < d.Height; ++y) std::memcpy(bytes.data() + std::size_t(y) * rowBytes,
            static_cast<const std::uint8_t*>(mapped.pData) + std::size_t(y) * mapped.RowPitch, rowBytes);
        context->Unmap(stage.get(), 0); return bytes;
    }
    void AddTexture(const Texture& t, const std::string& file) {
        D3D11_TEXTURE2D_DESC d{}; d.Width = t.w; d.Height = t.h; d.MipLevels = d.ArraySize = 1;
        d.Format = DXGI_FORMAT_R8G8B8A8_UNORM; d.SampleDesc.Count = 1;
        d.Usage = D3D11_USAGE_DEFAULT; d.BindFlags = D3D11_BIND_SHADER_RESOURCE;
        D3D11_SUBRESOURCE_DATA initial{t.rgba.data(), t.w * 4, 0}; Com<ID3D11Texture2D> texture;
        HR(device->CreateTexture2D(&d, &initial, texture.put()), "Original RGBA texture upload");
        const auto back = Readback(texture.get(), t.w * 4); Check(back == t.rgba, "GPU texture bytes differ"); Save(file, back.data(), back.size());
        auto* srv = new Com<ID3D11ShaderResourceView>;
        HR(device->CreateShaderResourceView(texture.get(), nullptr, srv->put()), "Original atlas SRV"); textures.push_back(srv);
    }
    std::string Capture(const Sample& sample, float sign, bool write, const std::string& stem, const std::string& out, bool synthetic = false) {
        const float black[4] = {0,0,0,1}, zero[4] = {0,0,0,0};
        context->ClearRenderTargetView(colorRT.get(), black); context->ClearRenderTargetView(ownerRT.get(), zero);
        context->ClearDepthStencilView(depthView.get(), D3D11_CLEAR_DEPTH, 0.f, 0);
        ID3D11RenderTargetView* targets[] = {colorRT.get(), ownerRT.get()}; context->OMSetRenderTargets(2, targets, depthView.get());
        context->OMSetBlendState(blend.get(), nullptr, 0xffffffff); context->OMSetDepthStencilState(write ? depthOn.get() : depthOff.get(), 0);
        context->RSSetState(synthetic ? syntheticRaster.get() : raster.get());
        D3D11_VIEWPORT viewport{0,0,float(width),float(height),0,1}; context->RSSetViewports(1, &viewport);
        context->IASetInputLayout(layout.get()); context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
        context->VSSetShader(vs.get(), nullptr, 0); context->PSSetShader(ps.get(), nullptr, 0);
        ID3D11Buffer* constant = cb.get(); context->VSSetConstantBuffers(0, 1, &constant); context->PSSetConstantBuffers(0, 1, &constant);
        ID3D11SamplerState* ss = sampler.get(); context->PSSetSamplers(0, 1, &ss);
        for (std::size_t i = 0; i < sample.draws.size(); ++i) {
            const auto& draw = sample.draws[i]; Check(draw.texture < textures.size(), "Draw texture missing");
            D3D11_BUFFER_DESC b{}; b.ByteWidth = UINT(draw.vertices.size() * sizeof(Vertex));
            b.Usage = D3D11_USAGE_IMMUTABLE; b.BindFlags = D3D11_BIND_VERTEX_BUFFER;
            D3D11_SUBRESOURCE_DATA initial{draw.vertices.data(), 0, 0}; Com<ID3D11Buffer> vb;
            HR(device->CreateBuffer(&b, &initial, vb.put()), "Original vertex buffer upload");
            ID3D11Buffer* vertex = vb.get(); UINT stride = sizeof(Vertex), offset = 0; context->IASetVertexBuffers(0, 1, &vertex, &stride, &offset);
            Constants constants{{sign,2.f/180.f,2.f/270.f,1.f/2000.f}, UINT(i + 1), {0,0,0}};
            if (worldShader) {
                WorldConstants world{}; std::memcpy(world.matrix, worldToClip.data(), sizeof world.matrix);
                world.exposure = 1.f; world.drawId = UINT(i + 1);
                context->UpdateSubresource(cb.get(), 0, nullptr, &world, 0, 0);
            } else context->UpdateSubresource(cb.get(), 0, nullptr, &constants, 0, 0);
            ID3D11ShaderResourceView* srv = textures[draw.texture]->get(); context->PSSetShaderResources(0, 1, &srv);
            context->Draw(UINT(draw.vertices.size()), 0);
        }
        Com<ID3D11DepthStencilState> actual; UINT reference;
        context->OMGetDepthStencilState(actual.put(), &reference); D3D11_DEPTH_STENCIL_DESC ds{}; actual->GetDesc(&ds);
        Check(ds.DepthEnable && ds.DepthFunc == D3D11_COMPARISON_GREATER_EQUAL &&
              ds.DepthWriteMask == (write ? D3D11_DEPTH_WRITE_MASK_ALL : D3D11_DEPTH_WRITE_MASK_ZERO), "Actual depth state differs");
        Com<ID3D11RasterizerState> actualRaster; context->RSGetState(actualRaster.put());
        D3D11_RASTERIZER_DESC rs{}; actualRaster->GetDesc(&rs);
        Check(rs.FrontCounterClockwise && rs.CullMode == (synthetic ? D3D11_CULL_NONE : D3D11_CULL_BACK), "Actual culling state differs");
        Com<ID3D11BlendState> actualBlend; float factor[4]; UINT mask;
        context->OMGetBlendState(actualBlend.put(), factor, &mask); D3D11_BLEND_DESC bs{}; actualBlend->GetDesc(&bs);
        Check(bs.IndependentBlendEnable && bs.RenderTarget[0].BlendEnable &&
              bs.RenderTarget[0].SrcBlend == D3D11_BLEND_SRC_ALPHA && bs.RenderTarget[0].DestBlend == D3D11_BLEND_INV_SRC_ALPHA &&
              bs.RenderTarget[0].BlendOp == D3D11_BLEND_OP_ADD && !bs.RenderTarget[1].BlendEnable, "Actual blend state differs");
        context->OMSetRenderTargets(0, nullptr, nullptr);
        const auto rgba = Readback(color.get(), width * 4), ids = Readback(owner.get(), width * 4), z = Readback(depth.get(), width * 4);
        Save(out + "/" + stem + ".rgba", rgba.data(), rgba.size()); Save(out + "/" + stem + ".owner_u32", ids.data(), ids.size());
        Save(out + "/" + stem + ".depth_f32", z.data(), z.size());
        return "{\"stem\":\"" + stem + "\",\"sample\":" + std::to_string(sample.index) + ",\"camera_sign\":" + std::to_string(int(sign)) +
            ",\"depth_write\":" + (write ? "true" : "false") + ",\"depth_compare_enum\":" + std::to_string(ds.DepthFunc) +
            ",\"draws\":" + std::to_string(sample.draws.size()) + ",\"synthetic\":" + (synthetic ? "true" : "false") + "}";
    }
};

Sample Synthetic(UINT texture, bool reverse) {
    Sample sample{0,{}};
    for (int i = 0; i < 2; ++i) {
        const bool isNearLayer = reverse ? i == 1 : i == 0;
        Draw d{texture,UINT(i),{}};
        const float corners[6][2] = {{-30,45},{30,45},{30,-45},{-30,45},{30,-45},{-30,-45}};
        for (const auto& c : corners) d.vertices.push_back({{c[0], isNearLayer ? 600.f : -600.f, c[1] + 88.f},
            {0,0}, {isNearLayer ? .5f : 0.f,0,isNearLayer ? 0.f : .5f,128.f/255.f}});
        sample.draws.push_back(std::move(d));
    }
    return sample;
}
int main(int argc, char** argv) {
    try {
        if (argc != 4) return 2;
        const std::string out = argv[3]; const auto bytes = Read(argv[1]), shader = Read(argv[2]);
        const auto geometry = T3BGE::LoadGPUGeometry(bytes);
        UINT width = geometry.calibrationWidth, height = geometry.calibrationHeight;
        UINT count = UINT(geometry.frames.size()), nt = UINT(geometry.atlases.size());
        Check(width == 512 && height == 768 && count == 12 && nt == 2, "Unsupported calibration bundle scope");
        GPU gpu(width, height, shader, out);
        for (UINT i = 0; i < nt; ++i) {
            const auto& source = geometry.atlases[i];
            Texture t{source.width, source.height, source.rgba};
            gpu.AddTexture(t, out + "/texture_" + std::to_string(i) + "_actual.rgba");
        }
        std::vector<std::string> results;
        for (const auto& source : geometry.frames) {
            Sample sample{source.sample,{}};
            for (const auto& d : source.draws) sample.draws.push_back({d.texture,d.ordinal,d.vertices});
            for (int sign : {1,-1}) for (bool write : {false,true}) {
                const std::string stem = "sample_" + std::to_string(sample.index) + (sign > 0 ? "_positive_y_" : "_negative_y_") + (write ? "source_depth" : "no_depth_write");
                results.push_back(gpu.Capture(sample, float(sign), write, stem, out));
            }
        }
        Texture white{1,1,{255,255,255,255}}; gpu.AddTexture(white, out + "/synthetic_white_actual.rgba");
        for (bool reverse : {false,true}) for (bool write : {false,true}) {
            const auto sample = Synthetic(nt, reverse);
            const std::string stem = std::string("synthetic_") + (reverse ? "far_then_near_" : "near_then_far_") + (write ? "depth_on" : "depth_off");
            results.push_back(gpu.Capture(sample, 1.f, write, stem, out, true));
        }
        std::string report = "{\"passed\":true,\"pid\":" + std::to_string(GetCurrentProcessId()) + ",\"adapter\":\"" + gpu.adapter +
            "\",\"feature_level\":" + std::to_string(gpu.feature) + ",\"width\":512,\"height\":768,\"depth_format\":\"D32_FLOAT\",\"captures\":[";
        for (std::size_t i = 0; i < results.size(); ++i) { if (i) report += ','; report += results[i]; }
        report += "]}"; Save(out + "/actual_gpu_report.json", report.data(), report.size());
        std::cout << "{\"passed\":true,\"captures\":" << results.size() << ",\"adapter\":\"" << gpu.adapter << "\"}\n";
        return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
