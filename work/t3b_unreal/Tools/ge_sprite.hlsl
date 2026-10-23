// Controlled source-state reference, not the complete PSP fixed-point rasterizer.
cbuffer DrawParameters : register(b0) {
    row_major float4x4 WorldToClip;
    float4 FogPlane;
    uint4 Control; // draw owner, RGB double, fog enable, unused
    uint4 FogRGB;
};
Texture2D<float4> Atlas : register(t0);
SamplerState AtlasSampler : register(s0);
struct Input { float3 Position:POSITION; float3 UV:TEXCOORD0; float4 Color:COLOR0; };
struct Interpolated {
    float4 Position:SV_Position;
    float2 UV:TEXCOORD0;
    noperspective float4 Color:COLOR0;
    noperspective float Fog:TEXCOORD1;
};
Interpolated VSMain(Input v) {
    Interpolated o;
    o.Position=mul(float4(v.Position,1),WorldToClip);
    o.UV=v.UV.xy; o.Color=v.Color; o.Fog=(Control.w&65536)!=0?v.UV.z:dot(float4(v.Position,1),FogPlane);
    return o;
}
uint QuantizeFog(float v) {
    uint bits=asuint(v),exp=bits>>23;
    if ((bits&0x80000000)!=0 || exp<=118) return 0;
    if (exp>126) return 255;
    return ((bits&0x007fffff)|0x00800000)>>(16+126-exp);
}
struct Pixel { float4 Color:SV_Target0; uint Owner:SV_Target1; };
Pixel PSMain(Interpolated v) {
    Pixel o;
    float4 c=Atlas.Sample(AtlasSampler,v.UV)*v.Color;
    if((Control.w&8192)==0 && c.a<=0)discard;
    c.rgb=saturate(c.rgb*(Control.y!=0?2.0:1.0));
    if(Control.z!=0) {
        uint fog=QuantizeFog(v.Fog);
        uint3 color=(uint3)round(c.rgb*255.0);
        c.rgb=((color*fog+FogRGB.rgb*(255-fog)+255)>>8)/255.0;
    }
    // Premultiply by the unbounded 2*a; only the inverse destination factor clamps.
    if((Control.w&1024)!=0){float twiceAlpha=c.a*2.0;c.rgb*=twiceAlpha;c.a=saturate(twiceAlpha);}
    o.Color=c; o.Owner=Control.x; return o;
}
