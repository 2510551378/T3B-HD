#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "T3BReplayWorld.generated.h"

class UProceduralMeshComponent;
class UTexture2D;
struct FT3BReplayState;
struct FT3BReplayStateDeleter { void operator()(FT3BReplayState* Ptr) const; };

// Visual replay only. No original collision, AI, damage or events are inferred.
UCLASS()
class T3BREMAKE_API AT3BReplayWorld : public AActor
{
    GENERATED_BODY()
public:
    AT3BReplayWorld();
    virtual ~AT3BReplayWorld() override;
    virtual void Tick(float DeltaSeconds) override;
    void SetReplaySeconds(float Seconds);
    void SetReplayPaused(bool Paused);
    // Select an explicitly staged synchronized Aya/weapon action pair.
    // Empty or "reference" restores the actor entries from manifest.json.
    void SetReplayActionClip(const FString& Label);
    bool WriteSourceProbe();
    void SetOriginalMaterials(bool Enabled);
    void SetFiring(bool Firing);
    bool WriteMotionProbe();
protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
private:
    bool LoadSourceBundle();
    void ApplyReplay(float Seconds, bool CreateSections, bool ExactSample = false);
    void StartFire();
    void StopFire();
    void FailReplay(const FString& Reason);
    UPROPERTY(Transient) TArray<TObjectPtr<UProceduralMeshComponent>> ReplayMeshes;
    UPROPERTY(Transient) TArray<TObjectPtr<UTexture2D>> ReplayAtlases;
    TUniquePtr<FT3BReplayState, FT3BReplayStateDeleter> State;
    double ReplaySeconds = 0.0;
    bool bReplayPaused = false;
    bool bReplayReady = false;
    bool bOriginalMaterials = true;
    bool bLoopPlayback = true;
};
