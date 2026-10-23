#pragma once
#include "CoreMinimal.h"
#include "SceneViewExtension.h"
#include "T3BGEGeometry.h"
#include "RHIResources.h"

class FTextureResource;
struct FT3BGESection {
    uint32 First{}, Count{}, Atlas{};
    bool Cull = true;
    bool Blend = true;
    bool DepthWrite = true;
};
struct FT3BGEWorldFrame {
    TArray<T3BGE::GPUVertex> Vertices;
    TArray<FT3BGESection> Sections;
    uint32 SourceSample{};
};

// Explicit source-compatibility pass. It draws real world vertices with the UE
// view and writes main scene depth; it is not a bitmap overlay or material mask.
// Supports explicit per-draw blend/cull/depth and up to256 original atlases; no stencil/fog recovery.
class FT3BGEViewExtension final : public FWorldSceneViewExtension {
public:
    FT3BGEViewExtension(const FAutoRegister& Register, UWorld* World);
    void Submit(TSharedPtr<const FT3BGEWorldFrame, ESPMode::ThreadSafe> Frame,
                const TArray<FTextureResource*>& Atlases);
    virtual void PrePostProcessPass_RenderThread(FRDGBuilder& GraphBuilder, const FSceneView& InView,
                                                const FPostProcessingInputs& Inputs) override;
private:
    // Accessed only by render-thread commands and the render callback.
    TSharedPtr<const FT3BGEWorldFrame, ESPMode::ThreadSafe> RenderFrame;
    TArray<FTextureRHIRef> RenderAtlases;
};
