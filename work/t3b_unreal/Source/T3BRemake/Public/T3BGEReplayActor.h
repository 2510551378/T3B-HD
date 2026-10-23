#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "T3BGEReplayActor.generated.h"

class UTexture2D;
struct FT3BGEReplayActorState;
struct FT3BGEReplayActorStateDeleter { void operator()(FT3BGEReplayActorState* Ptr) const; };

// Experimental source-compatibility 3D replay. Not an authored animation clock,
// named weapon socket, original AI/collision, or completed M1 replacement.
UCLASS()
class T3BREMAKE_API AT3BGEReplayActor : public AActor {
    GENERATED_BODY()
public:
    AT3BGEReplayActor();
    virtual ~AT3BGEReplayActor() override;
    virtual void Tick(float DeltaSeconds) override;
    UFUNCTION(BlueprintCallable, Category="T3B|Original GE") bool LoadOriginalGEBundle(const FString& Path);
    UFUNCTION(BlueprintCallable, Category="T3B|Original GE") void SetCapturedSample(int32 Sample);
    // Debug artifact is CPU submission data, not an RHI/GPU vertex readback.
    UFUNCTION(BlueprintCallable, Category="T3B|Original GE") bool WriteSubmittedFrame(const FString& Path) const;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="T3B|Original GE") FString BundleFile;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="T3B|Original GE") bool bEnableGEPass = true;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="T3B|Original GE") bool bPlayPreview = false;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="T3B|Original GE", meta=(ClampMin="1",ClampMax="120")) float PreviewSamplesPerSecond = 30.f;
    UPROPERTY(BlueprintReadOnly, Category="T3B|Original GE") int32 CapturedSample = 0;
    UPROPERTY(BlueprintReadOnly, Category="T3B|Original GE") int32 CapturedSampleCount = 0;
    UPROPERTY(BlueprintReadOnly, Category="T3B|Original GE") bool bSourceReady = false;
protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
private:
    void PublishSample();
    void ClearRenderFrame();
    UPROPERTY(Transient) TArray<TObjectPtr<UTexture2D>> Atlases;
    TUniquePtr<FT3BGEReplayActorState, FT3BGEReplayActorStateDeleter> State;
    double PreviewSamplePosition = 0.;
};
