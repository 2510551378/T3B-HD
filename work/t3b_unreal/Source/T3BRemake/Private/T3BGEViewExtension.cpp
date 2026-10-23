#include "T3BGEViewExtension.h"
#include "GlobalShader.h"
#include "PipelineStateCache.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "RenderResource.h"
#include "RHIStaticStates.h"
#include "SceneRendering.h"
#include "SceneTexturesConfig.h"
#include "PostProcess/PostProcessInputs.h"
#include "ShaderParameterStruct.h"
#include "TextureResource.h"
#include "HAL/IConsoleManager.h"

namespace {
TAutoConsoleVariable<int32> GDepthWrite(TEXT("r.T3BGE.DepthWrite"), 1,
    TEXT("Original GE main depth writes. Set0 only for a controlled no-write diagnostic."), ECVF_RenderThreadSafe);
class FT3BGEVertexDeclaration : public FRenderResource {
public:
    FVertexDeclarationRHIRef Declaration;
    virtual void InitRHI(FRHICommandListBase&) override {
        FVertexDeclarationElementList Elements;
        Elements.Add(FVertexElement(0, 0, VET_Float3, 0, sizeof(T3BGE::GPUVertex)));
        Elements.Add(FVertexElement(0, 12, VET_Float2, 1, sizeof(T3BGE::GPUVertex)));
        Elements.Add(FVertexElement(0, 20, VET_Float4, 2, sizeof(T3BGE::GPUVertex)));
        Declaration = PipelineStateCache::GetOrCreateVertexDeclaration(Elements);
    }
    virtual void ReleaseRHI() override { Declaration.SafeRelease(); }
};
TGlobalResource<FT3BGEVertexDeclaration> GDeclaration;

class FT3BGEVS final : public FGlobalShader {
public:
    DECLARE_GLOBAL_SHADER(FT3BGEVS);
    SHADER_USE_PARAMETER_STRUCT(FT3BGEVS, FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
        SHADER_PARAMETER(FMatrix44f, WorldToClip)
    END_SHADER_PARAMETER_STRUCT()
    static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& P) {
        return IsFeatureLevelSupported(P.Platform, ERHIFeatureLevel::SM5);
    }
};
class FT3BGEPS final : public FGlobalShader {
public:
    DECLARE_GLOBAL_SHADER(FT3BGEPS);
    SHADER_USE_PARAMETER_STRUCT(FT3BGEPS, FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
        SHADER_PARAMETER_TEXTURE(Texture2D, Atlas)
        SHADER_PARAMETER_SAMPLER(SamplerState, AtlasSampler)
        SHADER_PARAMETER(float, ScenePreExposure)
        SHADER_PARAMETER(uint32, DrawId)
    END_SHADER_PARAMETER_STRUCT()
    static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& P) {
        return IsFeatureLevelSupported(P.Platform, ERHIFeatureLevel::SM5);
    }
};
IMPLEMENT_GLOBAL_SHADER(FT3BGEVS, "/T3B/Private/T3BGEOrdered.usf", "MainVS", SF_Vertex);
IMPLEMENT_GLOBAL_SHADER(FT3BGEPS, "/T3B/Private/T3BGEOrdered.usf", "MainPS", SF_Pixel);

BEGIN_SHADER_PARAMETER_STRUCT(FT3BGEPassParameters, )
    RDG_BUFFER_ACCESS(Vertices, ERHIAccess::VertexOrIndexBuffer)
    RDG_TEXTURE_ACCESS_ARRAY(Atlases)
    RENDER_TARGET_BINDING_SLOTS()
END_SHADER_PARAMETER_STRUCT()
}

FT3BGEViewExtension::FT3BGEViewExtension(const FAutoRegister& Register, UWorld* World)
    : FWorldSceneViewExtension(Register, World) {}

void FT3BGEViewExtension::Submit(TSharedPtr<const FT3BGEWorldFrame, ESPMode::ThreadSafe> Frame,
                                const TArray<FTextureResource*>& Atlases) {
    check(IsInGameThread());
    auto Self = StaticCastSharedRef<FT3BGEViewExtension>(AsShared());
    // Texture initialization is enqueued before Submit. Snapshot RHI references
    // here on the render thread, retaining them independently of UObject GC.
    ENQUEUE_RENDER_COMMAND(T3BGEFrame)([Self, Frame = MoveTemp(Frame), Atlases](FRHICommandListImmediate&) {
        Self->RenderFrame.Reset(); Self->RenderAtlases.Reset();
        if (!Frame || Atlases.IsEmpty() || Atlases.Num() > 256) return;
        for (FTextureResource* Texture : Atlases) {
            if (!Texture || !Texture->TextureRHI.IsValid()) { Self->RenderAtlases.Reset(); return; }
            Self->RenderAtlases.Add(Texture->TextureRHI);
        }
        Self->RenderFrame = Frame;
    });
}

void FT3BGEViewExtension::PrePostProcessPass_RenderThread(FRDGBuilder& GraphBuilder,
    const FSceneView& InView, const FPostProcessingInputs& Inputs) {
    check(IsInRenderingThread());
    auto Frame = RenderFrame;
    if (!Frame || Frame->Vertices.IsEmpty() || RenderAtlases.IsEmpty() || !Inputs.SceneTextures) return;
    if (InView.GetFeatureLevel() < ERHIFeatureLevel::SM5) return;
    const FViewInfo& View = static_cast<const FViewInfo&>(InView);
    const auto* Scene = Inputs.SceneTextures->GetContents();
    FRDGTextureRef Color = Scene->SceneColorTexture, Depth = Scene->SceneDepthTexture;
    // First implementation explicitly supports single-sample desktop views.
    // Do not silently invent resolve/depth behavior for MSAA/mobile/stereo.
    if (!Color || !Depth || Color->Desc.NumSamples != 1 || Depth->Desc.NumSamples != 1) return;
    if (Color->Desc.Extent != Depth->Desc.Extent || View.ViewRect.Width() <= 0 || View.ViewRect.Height() <= 0) return;
    if (!FMath::IsFinite(View.PreExposure) || View.PreExposure <= 0.f) return;
    for (const auto& Section : Frame->Sections)
        if (Section.Atlas >= uint32(RenderAtlases.Num())) return;
    TArray<FRDGTextureRef> Atlases;
    auto Desc = FRDGBufferDesc::CreateBufferDesc(sizeof(T3BGE::GPUVertex), Frame->Vertices.Num());
    Desc.Usage = EBufferUsageFlags::Static | EBufferUsageFlags::VertexBuffer;
    FRDGBufferRef Vertices = CreateVertexBuffer(GraphBuilder, TEXT("T3BGEWorldVertices"), Desc,
        Frame->Vertices.GetData(), uint64(Frame->Vertices.Num()) * sizeof(T3BGE::GPUVertex));
    FRDGTextureRef Owner = GraphBuilder.CreateTexture(FRDGTextureDesc::Create2D(Color->Desc.Extent, PF_R32_UINT,
        FClearValueBinding::Black, TexCreate_RenderTargetable | TexCreate_ShaderResource), TEXT("T3BGELastDraw"));
    auto* Parameters = GraphBuilder.AllocParameters<FT3BGEPassParameters>();
    Parameters->Vertices = Vertices;
    for (const auto& Texture : RenderAtlases) {
        auto* Atlas = GraphBuilder.RegisterExternalTexture(CreateRenderTarget(Texture, TEXT("T3BOriginalAtlas")));
        Atlases.Add(Atlas); Parameters->Atlases.Emplace(Atlas, ERHIAccess::SRVGraphics);
    }
    Parameters->RenderTargets[0] = FRenderTargetBinding(Color, ERenderTargetLoadAction::ELoad);
    Parameters->RenderTargets[1] = FRenderTargetBinding(Owner, ERenderTargetLoadAction::EClear);
    const bool bDepthWrite = GDepthWrite.GetValueOnRenderThread() != 0;
    Parameters->RenderTargets.DepthStencil = FDepthStencilBinding(Depth, ERenderTargetLoadAction::ELoad,
        ERenderTargetLoadAction::ELoad, bDepthWrite ? FExclusiveDepthStencil::DepthWrite_StencilNop : FExclusiveDepthStencil::DepthRead_StencilNop);
    TShaderMapRef<FT3BGEVS> VS(View.ShaderMap); TShaderMapRef<FT3BGEPS> PS(View.ShaderMap);
    const FMatrix44f WorldToClip(View.ViewMatrices.GetViewProjectionMatrix());
    const FIntRect Rect = View.ViewRect; const float PreExposure = View.PreExposure;
    const bool bReverseCulling = View.bReverseCulling;
    GraphBuilder.AddPass(RDG_EVENT_NAME("T3BGEOrdered Sample=%u Draws=%d", Frame->SourceSample, Frame->Sections.Num()),
        Parameters, ERDGPassFlags::Raster,
        [Frame, Vertices, Atlases = MoveTemp(Atlases), VS, PS, WorldToClip, Rect, PreExposure, bDepthWrite, bReverseCulling](FRHICommandList& RHICmdList) {
            FGraphicsPipelineStateInitializer Pipeline;
            RHICmdList.ApplyCachedRenderTargets(Pipeline);
            Pipeline.PrimitiveType = PT_TriangleList;
            Pipeline.BoundShaderState.VertexDeclarationRHI = GDeclaration.Declaration;
            Pipeline.BoundShaderState.VertexShaderRHI = VS.GetVertexShader();
            Pipeline.BoundShaderState.PixelShaderRHI = PS.GetPixelShader();
            Pipeline.RasterizerState = bReverseCulling ? TStaticRasterizerState<FM_Solid, CM_CCW>::GetRHI()
                : TStaticRasterizerState<FM_Solid, CM_CW>::GetRHI();
            Pipeline.DepthStencilState = bDepthWrite ? TStaticDepthStencilState<true, CF_GreaterEqual>::GetRHI()
                : TStaticDepthStencilState<false, CF_GreaterEqual>::GetRHI();
            // MRT0: source alpha blend, RGB only. MRT1: unblended integer owner.
            Pipeline.BlendState = TStaticBlendState<CW_RGB, BO_Add, BF_SourceAlpha, BF_InverseSourceAlpha,
                BO_Add, BF_One, BF_Zero, CW_RED, BO_Add, BF_One, BF_Zero>::GetRHI();
            SetGraphicsPipelineState(RHICmdList, Pipeline, 0);
            RHICmdList.SetScissorRect(false, 0, 0, 0, 0);
            RHICmdList.SetViewport(Rect.Min.X, Rect.Min.Y, 0.f, Rect.Max.X, Rect.Max.Y, 1.f);
            RHICmdList.SetStreamSource(0, Vertices->GetRHI(), 0);
            FT3BGEVS::FParameters V; V.WorldToClip = WorldToClip;
            SetShaderParameters(RHICmdList, VS, VS.GetVertexShader(), V);
            for (int32 I = 0; I < Frame->Sections.Num(); ++I) {
                const auto& Draw = Frame->Sections[I];
                Pipeline.RasterizerState = !Draw.Cull ? TStaticRasterizerState<FM_Solid, CM_None>::GetRHI()
                    : bReverseCulling ? TStaticRasterizerState<FM_Solid, CM_CCW>::GetRHI()
                    : TStaticRasterizerState<FM_Solid, CM_CW>::GetRHI();
                Pipeline.DepthStencilState = bDepthWrite && Draw.DepthWrite
                    ? TStaticDepthStencilState<true, CF_GreaterEqual>::GetRHI()
                    : TStaticDepthStencilState<false, CF_GreaterEqual>::GetRHI();
                Pipeline.BlendState = Draw.Blend
                    ? TStaticBlendState<CW_RGB, BO_Add, BF_SourceAlpha, BF_InverseSourceAlpha,
                        BO_Add, BF_One, BF_Zero, CW_RED, BO_Add, BF_One, BF_Zero>::GetRHI()
                    : TStaticBlendState<CW_RGB, BO_Add, BF_One, BF_Zero,
                        BO_Add, BF_One, BF_Zero, CW_RED, BO_Add, BF_One, BF_Zero>::GetRHI();
                SetGraphicsPipelineState(RHICmdList, Pipeline, 0);
                FT3BGEPS::FParameters P;
                P.Atlas = Atlases[Draw.Atlas]->GetRHI();
                P.AtlasSampler = TStaticSamplerState<SF_Bilinear, AM_Wrap, AM_Wrap, AM_Wrap>::GetRHI();
                P.ScenePreExposure = PreExposure; P.DrawId = uint32(I + 1);
                SetShaderParameters(RHICmdList, PS, PS.GetPixelShader(), P);
                RHICmdList.DrawPrimitive(Draw.First, Draw.Count / 3, 1);
            }
        });
}
