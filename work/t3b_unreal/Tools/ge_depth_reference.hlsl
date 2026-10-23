#include "/T3B/Private/T3BGECommon.ush"
// Controlled D3D11 calibration, not a complete PSP rasterizer.
// Input light is the independently checked original GE vertex-light model.
cbuffer Camera : register(b0) {
    float4 View; // camera sign, 2/orthoWidth, 2/orthoHeight, depth scale
    uint DrawId;
    float3 Padding;
};
struct Input {
    float3 Position : POSITION;
    float2 UV : TEXCOORD0;
    float4 Color : COLOR0;
};
struct Interpolated {
    float4 Position : SV_Position;
    float2 UV : TEXCOORD0;
    float4 Color : COLOR0;
};
Interpolated VSMain(Input v) {
    Interpolated o;
    // Same +/-Y orthographic image axes as the existing UE calibration.
    o.Position = float4(v.Position.x * View.x * View.y,
                        (v.Position.z - 88.0) * View.z,
                        0.5 + v.Position.y * View.x * View.w, 1.0);
    o.UV = v.UV;
    o.Color = v.Color;
    return o;
}
Texture2D<float4> Atlas : register(t0);
SamplerState LinearRepeat : register(s0);
struct Pixel {
    float4 Color : SV_Target0;
    uint Owner : SV_Target1;
};
Pixel PSMain(Interpolated v) {
    Pixel p;
    p.Color = T3BGECombine(Atlas.Sample(LinearRepeat, v.UV), v.Color);
    p.Owner = DrawId;
    return p;
}
