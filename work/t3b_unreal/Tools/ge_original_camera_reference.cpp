// Reuse the owned device/raster/readback implementation; old entry remains unchanged.
#define main T3BCalibrationReferenceMain
#include "ge_depth_reference.cpp"
#undef main

void CaptureVertices(GPU& gpu, const Sample& sample, const std::string& out) {
    const auto code = Read(out + "/actual_vs.dxbc");
    D3D11_SO_DECLARATION_ENTRY declarations[] = {
        {0,"SV_Position",0,0,4,0},{0,"TEXCOORD",0,0,2,0},{0,"COLOR",0,0,4,0}};
    const UINT outputStride = 40; Com<ID3D11GeometryShader> stream;
    HR(gpu.device->CreateGeometryShaderWithStreamOutput(code.data(),code.size(),declarations,3,
        &outputStride,1,D3D11_SO_NO_RASTERIZED_STREAM,nullptr,stream.put()), "Original camera stream output");
    std::vector<Vertex> vertices;
    for (const auto& d:sample.draws) vertices.insert(vertices.end(),d.vertices.begin(),d.vertices.end());
    D3D11_BUFFER_DESC b{}; b.ByteWidth = UINT(vertices.size()*sizeof(Vertex));
    b.Usage = D3D11_USAGE_IMMUTABLE; b.BindFlags = D3D11_BIND_VERTEX_BUFFER;
    D3D11_SUBRESOURCE_DATA initial{vertices.data(),0,0}; Com<ID3D11Buffer> vb,output,read;
    HR(gpu.device->CreateBuffer(&b,&initial,vb.put()), "Source vertex upload");
    b.ByteWidth = UINT(vertices.size()*outputStride); b.Usage=D3D11_USAGE_DEFAULT; b.BindFlags=D3D11_BIND_STREAM_OUTPUT;
    HR(gpu.device->CreateBuffer(&b,nullptr,output.put()), "SO output");
    b.Usage=D3D11_USAGE_STAGING; b.BindFlags=0; b.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
    HR(gpu.device->CreateBuffer(&b,nullptr,read.put()), "SO readback");
    WorldConstants constants{}; std::memcpy(constants.matrix,gpu.worldToClip.data(),sizeof constants.matrix); constants.exposure=1;
    gpu.context->UpdateSubresource(gpu.cb.get(),0,nullptr,&constants,0,0);
    ID3D11Buffer* cb=gpu.cb.get(); gpu.context->VSSetConstantBuffers(0,1,&cb);
    gpu.context->IASetInputLayout(gpu.layout.get()); gpu.context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_POINTLIST);
    ID3D11Buffer* v=vb.get(); UINT stride=sizeof(Vertex),offset=0; gpu.context->IASetVertexBuffers(0,1,&v,&stride,&offset);
    gpu.context->VSSetShader(gpu.vs.get(),nullptr,0); gpu.context->GSSetShader(stream.get(),nullptr,0);
    ID3D11Buffer* o=output.get(); gpu.context->SOSetTargets(1,&o,&offset);
    gpu.context->Draw(UINT(vertices.size()),0); gpu.context->SOSetTargets(0,nullptr,nullptr);
    gpu.context->GSSetShader(nullptr,nullptr,0); gpu.context->CopyResource(read.get(),output.get());
    D3D11_MAPPED_SUBRESOURCE mapped{}; HR(gpu.context->Map(read.get(),0,D3D11_MAP_READ,0,&mapped), "SO Map");
    Save(out+"/sample_"+std::to_string(sample.index)+".clip_uv_color_f32",mapped.pData,vertices.size()*outputStride);
    gpu.context->Unmap(read.get(),0);
}

int main(int argc,char** argv) {
    try {
        if (argc!=5) return 2;
        const auto geometry=T3BGE::LoadGPUGeometry(Read(argv[1]));
        const auto cameras=Read(argv[3]); const std::string out=argv[4];
        Check(cameras.size()==20+12*68 && !std::memcmp(cameras.data(),"T3BCAM1\0",8), "Unexpected camera binary");
        std::uint32_t header[3]; std::memcpy(header,cameras.data()+8,sizeof header);
        Check(header[0]==480 && header[1]==272 && header[2]==12 && geometry.frames.size()==12, "Unsupported camera extent");
        // Render at the original PSP resolution. Higher-resolution rendering is a separate test.
        GPU gpu(header[0],header[1],Read(argv[2]),out,true);
        for (size_t i=0;i<geometry.atlases.size();++i) {
            const auto& t=geometry.atlases[i]; gpu.AddTexture({t.width,t.height,t.rgba},out+"/texture_"+std::to_string(i)+"_actual.rgba");
        }
        std::vector<std::string> captures;
        for (const auto& f:geometry.frames) {
            const size_t at=20+f.sample*68; std::uint32_t id; std::memcpy(&id,cameras.data()+at,4);
            Check(id==f.sample && id<12, "Camera sample pairing differs");
            std::memcpy(gpu.worldToClip.data(),cameras.data()+at+4,64);
            Sample sample{f.sample,{}};
            for (const auto& d:f.draws) sample.draws.push_back({d.texture,d.ordinal,d.vertices});
            CaptureVertices(gpu,sample,out);
            for (bool depth:{false,true}) captures.push_back(gpu.Capture(sample,1.f,depth,
                "sample_"+std::to_string(id)+(depth?"_original_camera_depth_on":"_original_camera_depth_off"),out));
        }
        std::string report="{\"passed\":true,\"pid\":"+std::to_string(GetCurrentProcessId())+",\"adapter\":\""+gpu.adapter+
            "\",\"width\":480,\"height\":272,\"original_camera_matrices\":true,\"UE_executed\":false,\"captures\":[";
        for (size_t i=0;i<captures.size();++i) {if(i)report+=',';report+=captures[i];}
        report+="]}"; Save(out+"/actual_gpu_report.json",report.data(),report.size());
        std::cout<<"{\"passed\":true,\"captures\":"<<captures.size()<<",\"pid\":"<<GetCurrentProcessId()<<"}\n"; return 0;
    } catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
