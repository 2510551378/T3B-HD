#pragma once
#include "CoreMinimal.h"
#include "SceneViewExtension.h"
#include "T3BGEScene.h"
#include "RHIResources.h"
class FTextureResource;
// Explicit source-camera calibration. Renders real geometry using original draw
// projections with a separate source depth target; not PC-camera gameplay depth.
class FT3BGESceneViewExtension final:public FWorldSceneViewExtension {
public:
    FT3BGESceneViewExtension(const FAutoRegister& Register,UWorld* World);
    void Submit(TSharedPtr<const T3BGE::SceneFrame,ESPMode::ThreadSafe> Frame,const TArray<FTextureResource*>& Atlases);
    virtual void PrePostProcessPass_RenderThread(FRDGBuilder&,const FSceneView&,const FPostProcessingInputs&) override;
private:
    TSharedPtr<const T3BGE::SceneFrame,ESPMode::ThreadSafe> RenderFrame;
    TArray<FTextureRHIRef> RenderAtlases;
};
