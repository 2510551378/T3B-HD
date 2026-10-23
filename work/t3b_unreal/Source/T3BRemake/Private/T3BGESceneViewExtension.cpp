#include "T3BGESceneViewExtension.h"
#include "GlobalShader.h"
#include "PipelineStateCache.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "RenderResource.h"
#include "RHIStaticStates.h"
#include "SceneRendering.h"
#include "PostProcess/PostProcessInputs.h"
#include "ShaderParameterStruct.h"
#include "TextureResource.h"

namespace {
class FSceneDeclaration:public FRenderResource {
public:
    FVertexDeclarationRHIRef Declaration;
    virtual void InitRHI(FRHICommandListBase&) override {
        FVertexDeclarationElementList E;
        E.Add(FVertexElement(0,0,VET_Float3,0,sizeof(T3BGE::GPUVertex)));
        E.Add(FVertexElement(0,12,VET_Float2,1,sizeof(T3BGE::GPUVertex)));
        E.Add(FVertexElement(0,20,VET_Float4,2,sizeof(T3BGE::GPUVertex)));
        Declaration=PipelineStateCache::GetOrCreateVertexDeclaration(E);
    }
    virtual void ReleaseRHI() override { Declaration.SafeRelease(); }
};
TGlobalResource<FSceneDeclaration> GSceneDeclaration;
class FT3BSceneVS final:public FGlobalShader {
public:
    DECLARE_GLOBAL_SHADER(FT3BSceneVS);SHADER_USE_PARAMETER_STRUCT(FT3BSceneVS,FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters,)
        SHADER_PARAMETER(FMatrix44f,LocalToClip)
        SHADER_PARAMETER(FVector4f,FogPlane)
    END_SHADER_PARAMETER_STRUCT()
    static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& P){return IsFeatureLevelSupported(P.Platform,ERHIFeatureLevel::SM5);}
};
class FT3BScenePS final:public FGlobalShader {
public:
    DECLARE_GLOBAL_SHADER(FT3BScenePS);SHADER_USE_PARAMETER_STRUCT(FT3BScenePS,FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters,)
        SHADER_PARAMETER_TEXTURE(Texture2D,Atlas)
        SHADER_PARAMETER_SAMPLER(SamplerState,AtlasSampler)
        SHADER_PARAMETER(uint32,DrawFlags)
        SHADER_PARAMETER(uint32,DrawId)
        SHADER_PARAMETER(FUintVector4,FogRGB)
        SHADER_PARAMETER(float,ScenePreExposure)
    END_SHADER_PARAMETER_STRUCT()
    static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& P){return IsFeatureLevelSupported(P.Platform,ERHIFeatureLevel::SM5);}
};
IMPLEMENT_GLOBAL_SHADER(FT3BSceneVS,"/T3B/Private/T3BGEScene.usf","MainVS",SF_Vertex);
IMPLEMENT_GLOBAL_SHADER(FT3BScenePS,"/T3B/Private/T3BGEScene.usf","MainPS",SF_Pixel);
BEGIN_SHADER_PARAMETER_STRUCT(FScenePassParameters,)
    RDG_BUFFER_ACCESS(Vertices,ERHIAccess::VertexOrIndexBuffer)
    RDG_TEXTURE_ACCESS_ARRAY(Atlases)
    RENDER_TARGET_BINDING_SLOTS()
END_SHADER_PARAMETER_STRUCT()
struct FFlatDraw { uint32 First=0,Count=0,Atlas=0,Flags=0,Reference=0,Owner=0;FMatrix44f Matrix=FMatrix44f::Identity;FVector4f Fog=FVector4f(0.f,0.f,0.f,0.f);FUintVector4 FogRGB=FUintVector4(0,0,0,0); };
}
FT3BGESceneViewExtension::FT3BGESceneViewExtension(const FAutoRegister& Register,UWorld* World):FWorldSceneViewExtension(Register,World){}
void FT3BGESceneViewExtension::Submit(TSharedPtr<const T3BGE::SceneFrame,ESPMode::ThreadSafe> Frame,const TArray<FTextureResource*>& Atlases){
    check(IsInGameThread());auto Self=StaticCastSharedRef<FT3BGESceneViewExtension>(AsShared());
    ENQUEUE_RENDER_COMMAND(T3BGESourceScene)([Self,Frame=MoveTemp(Frame),Atlases](FRHICommandListImmediate&){
        Self->RenderFrame.Reset();Self->RenderAtlases.Reset();if(!Frame||Atlases.IsEmpty()||Atlases.Num()>256)return;
        for(FTextureResource* T:Atlases){if(!T||!T->TextureRHI.IsValid()){Self->RenderAtlases.Reset();return;}Self->RenderAtlases.Add(T->TextureRHI);}
        Self->RenderFrame=Frame;
    });
}
void FT3BGESceneViewExtension::PrePostProcessPass_RenderThread(FRDGBuilder& Graph,const FSceneView& InView,const FPostProcessingInputs& Inputs){
    check(IsInRenderingThread());const auto Frame=RenderFrame;
    if(!Frame||Frame->draws.empty()||RenderAtlases.IsEmpty()||!Inputs.SceneTextures||InView.GetFeatureLevel()<ERHIFeatureLevel::SM5||InView.StereoPass!=EStereoscopicPass::eSSP_FULL)return;
    const FViewInfo& View=static_cast<const FViewInfo&>(InView);FRDGTextureRef Color=Inputs.SceneTextures->GetContents()->SceneColorTexture;
    if(!Color||Color->Desc.NumSamples!=1||View.ViewRect.Width()<=0||View.ViewRect.Height()<=0||!FMath::IsFinite(View.PreExposure)||View.PreExposure<=0)return;
    TArray<T3BGE::GPUVertex> VerticesCPU;TArray<FFlatDraw> Draws;
    for(const auto& D:Frame->draws){
        if(D.texture>=uint32(RenderAtlases.Num()))return;
        FFlatDraw O{};O.First=VerticesCPU.Num();O.Count=D.vertices.size();O.Atlas=D.texture;O.Flags=D.flags;O.Reference=D.stencilRef;O.Owner=D.ordinal+1;
        FMemory::Memcpy(&O.Matrix,D.localToClip.data(),64);O.Fog=FVector4f(D.fog[0],D.fog[1],D.fog[2],D.fog[3]);O.FogRGB=FUintVector4(D.fogRGB[0],D.fogRGB[1],D.fogRGB[2],0);
        VerticesCPU.Append(D.vertices.data(),D.vertices.size());Draws.Add(O);
    }
    auto Desc=FRDGBufferDesc::CreateBufferDesc(sizeof(T3BGE::GPUVertex),VerticesCPU.Num());Desc.Usage=EBufferUsageFlags::Static|EBufferUsageFlags::VertexBuffer;
    FRDGBufferRef VB=CreateVertexBuffer(Graph,TEXT("T3BSourceSceneVertices"),Desc,VerticesCPU.GetData(),uint64(VerticesCPU.Num())*sizeof(T3BGE::GPUVertex));
    TArray<FRDGTextureRef> Atlases;auto* Params=Graph.AllocParameters<FScenePassParameters>();Params->Vertices=VB;
    for(const auto& T:RenderAtlases){auto* A=Graph.RegisterExternalTexture(CreateRenderTarget(T,TEXT("T3BSourceAtlas")));Atlases.Add(A);Params->Atlases.Emplace(A,ERHIAccess::SRVGraphics);}
    auto DepthDesc=FRDGTextureDesc::Create2D(Color->Desc.Extent,PF_DepthStencil,FClearValueBinding(0.f,0),TexCreate_DepthStencilTargetable);
    auto* Depth=Graph.CreateTexture(DepthDesc,TEXT("T3BSourceCalibrationDepth"));
    auto* Owner=Graph.CreateTexture(FRDGTextureDesc::Create2D(Color->Desc.Extent,PF_R32_UINT,FClearValueBinding::Black,TexCreate_RenderTargetable|TexCreate_ShaderResource),TEXT("T3BSourceDrawOwner"));
    // Explicit calibration replaces the color view. It does not corrupt UE's
    // unrelated camera depth or claim source clip depths are gameplay depths.
    Params->RenderTargets[0]=FRenderTargetBinding(Color,ERenderTargetLoadAction::EClear);
    Params->RenderTargets[1]=FRenderTargetBinding(Owner,ERenderTargetLoadAction::EClear);
    Params->RenderTargets.DepthStencil=FDepthStencilBinding(Depth,ERenderTargetLoadAction::EClear,ERenderTargetLoadAction::EClear,FExclusiveDepthStencil::DepthWrite_StencilWrite);
    TShaderMapRef<FT3BSceneVS> VS(View.ShaderMap);TShaderMapRef<FT3BScenePS> PS(View.ShaderMap);const auto Rect=View.ViewRect;const float Exposure=View.PreExposure;
    Graph.AddPass(RDG_EVENT_NAME("T3BSourceCalibration Sample=%u",Frame->sample),Params,ERDGPassFlags::Raster,
        [Draws=MoveTemp(Draws),Atlases=MoveTemp(Atlases),VB,VS,PS,Rect,Exposure](FRHICommandList& Cmd){
            Cmd.SetScissorRect(false,0,0,0,0);Cmd.SetViewport(Rect.Min.X,Rect.Min.Y,0.f,Rect.Max.X,Rect.Max.Y,1.f);Cmd.SetStreamSource(0,VB->GetRHI(),0);
            for(const auto& D:Draws){
                FGraphicsPipelineStateInitializer Pipeline;Cmd.ApplyCachedRenderTargets(Pipeline);Pipeline.PrimitiveType=PT_TriangleList;
                Pipeline.BoundShaderState.VertexDeclarationRHI=GSceneDeclaration.Declaration;Pipeline.BoundShaderState.VertexShaderRHI=VS.GetVertexShader();Pipeline.BoundShaderState.PixelShaderRHI=PS.GetPixelShader();
                FRasterizerStateInitializerRHI Raster(FM_Solid,(D.Flags&4)?((D.Flags&16384)?CM_CCW:CM_CW):CM_None,false);
                Raster.DepthClipMode=(D.Flags&64)?ERasterizerDepthClipMode::DepthClamp:ERasterizerDepthClipMode::DepthClip;Pipeline.RasterizerState=RHICreateRasterizerState(Raster);
                const bool Stencil=(D.Flags&32)!=0;FDepthStencilStateInitializerRHI DS((D.Flags&2)!=0,CF_GreaterEqual,Stencil,CF_Always,SO_Zero,SO_Replace,SO_Replace,Stencil,CF_Always,SO_Zero,SO_Replace,SO_Replace,0,255);
                Pipeline.DepthStencilState=RHICreateDepthStencilState(DS);
                FBlendStateInitializerRHI Blend;Blend.bUseIndependentRenderTargetBlendStates=true;Blend.bUseAlphaToCoverage=false;
                const bool Enabled=(D.Flags&1)!=0;Blend.RenderTargets[0]=FBlendStateInitializerRHI::FRenderTarget(BO_Add,Enabled?((D.Flags&1024)?BF_One:BF_SourceAlpha):BF_One,Enabled?((D.Flags&2048)?BF_One:BF_InverseSourceAlpha):BF_Zero,BO_Add,BF_One,BF_Zero,CW_RGB);
                Blend.RenderTargets[1]=FBlendStateInitializerRHI::FRenderTarget(BO_Add,BF_One,BF_Zero,BO_Add,BF_One,BF_Zero,CW_RED);Pipeline.BlendState=RHICreateBlendState(Blend);
                SetGraphicsPipelineState(Cmd,Pipeline,D.Reference);FT3BSceneVS::FParameters V;V.LocalToClip=D.Matrix;V.FogPlane=D.Fog;SetShaderParameters(Cmd,VS,VS.GetVertexShader(),V);
                FT3BScenePS::FParameters P;P.Atlas=Atlases[D.Atlas]->GetRHI();P.DrawFlags=D.Flags;P.DrawId=D.Owner;P.FogRGB=D.FogRGB;P.ScenePreExposure=Exposure;
                const auto U=(D.Flags&256)?AM_Clamp:AM_Wrap,W=(D.Flags&512)?AM_Clamp:AM_Wrap;
                FSamplerStateInitializerRHI Sampler(SF_Trilinear,U,W,AM_Wrap);Sampler.MinMipLevel=Sampler.MaxMipLevel=0;const auto SamplerRHI=RHICreateSamplerState(Sampler);P.AtlasSampler=SamplerRHI;
                SetShaderParameters(Cmd,PS,PS.GetPixelShader(),P);Cmd.DrawPrimitive(D.First,D.Count/3,1);
            }
        });
}
