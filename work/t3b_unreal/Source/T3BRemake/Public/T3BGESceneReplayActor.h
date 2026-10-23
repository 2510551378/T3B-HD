#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "T3BGESceneReplayActor.generated.h"
class UTexture2D;
struct FT3BGESceneActorState;
struct FT3BGESceneActorStateDeleter { void operator()(FT3BGESceneActorState* Ptr) const; };
// Opt-in source-camera calibration, not a default M1 or authored animation.
UCLASS()
class T3BREMAKE_API AT3BGESceneReplayActor:public AActor {
    GENERATED_BODY()
public:
    AT3BGESceneReplayActor();
    virtual ~AT3BGESceneReplayActor() override;
    UFUNCTION(BlueprintCallable,Category="T3B|Source Scene") bool LoadSourceScene(const FString& ScenePath,const FString& EffectPath);
    UFUNCTION(BlueprintCallable,Category="T3B|Source Scene") bool SetCapturedSample(int32 Sample);
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="T3B|Source Scene") FString SceneFile;
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="T3B|Source Scene") FString EffectBindingsFile;
    // Enabling replaces the color view using original projections and own depth.
    UPROPERTY(EditAnywhere,BlueprintReadWrite,Category="T3B|Source Scene") bool bEnableSourceCalibration=false;
    UPROPERTY(BlueprintReadOnly,Category="T3B|Source Scene") int32 CapturedSample=0;
    UPROPERTY(BlueprintReadOnly,Category="T3B|Source Scene") int32 CapturedSampleCount=0;
    UPROPERTY(BlueprintReadOnly,Category="T3B|Source Scene") bool bSourceReady=false;
    virtual void Tick(float DeltaSeconds) override;
protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
private:
    void ClearFrame();
    void SubmitFrame();
    UPROPERTY(Transient) TArray<TObjectPtr<UTexture2D>> Atlases;
    TUniquePtr<FT3BGESceneActorState, FT3BGESceneActorStateDeleter> State;
};
