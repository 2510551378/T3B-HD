#include "T3BGESceneReplayActor.h"
#include "T3BGEScene.h"
#include "T3BGESceneViewExtension.h"
#include "Components/SceneComponent.h"
#include "Engine/Texture2D.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include <exception>
#include <stdexcept>
DEFINE_LOG_CATEGORY_STATIC(LogT3BSourceScene,Log,All);
struct FT3BGESceneActorState {
    T3BGE::SceneGeometry Scene;
    T3BGE::SceneEffectBindings Effects;
    TSharedPtr<FT3BGESceneViewExtension,ESPMode::ThreadSafe> Extension;
    TSharedPtr<const T3BGE::SceneFrame,ESPMode::ThreadSafe> Frame;
};
void FT3BGESceneActorStateDeleter::operator()(FT3BGESceneActorState* Ptr) const { delete Ptr; }
AT3BGESceneReplayActor::AT3BGESceneReplayActor(){PrimaryActorTick.bCanEverTick=true;RootComponent=CreateDefaultSubobject<USceneComponent>(TEXT("SourceSceneRoot"));}
AT3BGESceneReplayActor::~AT3BGESceneReplayActor()=default;
void AT3BGESceneReplayActor::ClearFrame(){if(State&&State->Extension)State->Extension->Submit(nullptr,{});}
void AT3BGESceneReplayActor::BeginPlay(){Super::BeginPlay();if(!SceneFile.IsEmpty()&&!EffectBindingsFile.IsEmpty())LoadSourceScene(SceneFile,EffectBindingsFile);}
void AT3BGESceneReplayActor::EndPlay(const EEndPlayReason::Type Reason){ClearFrame();State.Reset();Atlases.Reset();bSourceReady=false;Super::EndPlay(Reason);}
bool AT3BGESceneReplayActor::LoadSourceScene(const FString& ScenePath,const FString& EffectPath){
    ClearFrame();State.Reset();Atlases.Reset();bSourceReady=false;CapturedSampleCount=0;
    try{
        const auto Read=[](const FString& Path){TArray<uint8> Bytes;if(!FFileHelper::LoadFileToArray(Bytes,*FPaths::ConvertRelativePathToFull(Path)))throw std::runtime_error("Source bundle unreadable");return std::vector<std::uint8_t>(Bytes.GetData(),Bytes.GetData()+Bytes.Num());};
        auto Next=TUniquePtr<FT3BGESceneActorState,FT3BGESceneActorStateDeleter>(new FT3BGESceneActorState());Next->Scene=T3BGE::LoadSceneGeometry(Read(ScenePath));Next->Effects=T3BGE::LoadSceneEffectBindings(Read(EffectPath));
        // Validate every frame before publishing any of the loaded scene.
        for(uint32 I=0;I<Next->Scene.frames.size();++I)T3BGE::EvaluateSceneFrame(Next->Scene,I,&Next->Effects);
        for(const auto& T:Next->Scene.atlases){
            UTexture2D* Texture=UTexture2D::CreateTransient(T.width,T.height,PF_R8G8B8A8,NAME_None,TConstArrayView64<uint8>(T.rgba.data(),int64(T.rgba.size())));
            if(!Texture)throw std::runtime_error("Source atlas creation failed");Atlases.Add(Texture);Texture->SRGB=false;Texture->NeverStream=true;Texture->Filter=TF_Trilinear;Texture->UpdateResource();
        }
        Next->Extension=FSceneViewExtensions::NewExtension<FT3BGESceneViewExtension>(GetWorld());State=MoveTemp(Next);CapturedSampleCount=State->Scene.frames.size();CapturedSample=0;bSourceReady=true;
        if(!SetCapturedSample(0))return false;
        UE_LOG(LogT3BSourceScene,Display,TEXT("Loaded %d source-camera samples with original color bindings. Calibration only; no source clock or default M1 replacement."),CapturedSampleCount);return true;
    }catch(const std::exception& E){ClearFrame();State.Reset();Atlases.Reset();bSourceReady=false;CapturedSampleCount=0;UE_LOG(LogT3BSourceScene,Error,TEXT("Source scene rejected: %s"),UTF8_TO_TCHAR(E.what()));return false;}
}
bool AT3BGESceneReplayActor::SetCapturedSample(int32 Sample){
    if(!bSourceReady||!State||Sample<0||Sample>=CapturedSampleCount)return false;
    try{
        auto Frame=MakeShared<T3BGE::SceneFrame,ESPMode::ThreadSafe>(T3BGE::EvaluateSceneFrame(State->Scene,uint32(Sample),&State->Effects));
        State->Frame=MoveTemp(Frame);CapturedSample=Sample;SubmitFrame();return true;
    }catch(const std::exception& E){ClearFrame();UE_LOG(LogT3BSourceScene,Error,TEXT("Source frame rejected: %s"),UTF8_TO_TCHAR(E.what()));return false;}
}
void AT3BGESceneReplayActor::SubmitFrame(){
    if(!State||!State->Extension)return;
    // Matrices already include source-camera placement. Actor transforms would
    // silently mix source and UE coordinate systems, so reject them here.
    if(!bEnableSourceCalibration||IsHidden()||!GetActorTransform().Equals(FTransform::Identity)){ClearFrame();return;}
    TArray<FTextureResource*> Resources;for(UTexture2D* T:Atlases)Resources.Add(T->GetResource());State->Extension->Submit(State->Frame,Resources);
}
void AT3BGESceneReplayActor::Tick(float DeltaSeconds){Super::Tick(DeltaSeconds);if(bSourceReady)SubmitFrame();}
