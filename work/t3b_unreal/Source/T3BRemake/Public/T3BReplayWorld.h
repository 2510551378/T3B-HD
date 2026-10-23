#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "T3BReplayWorld.generated.h"

class UProceduralMeshComponent;
class UTexture2D;
struct FT3BReplayState;
struct FT3BReplayStateDeleter { void operator()(FT3BReplayState* Ptr) const; };

// Source-preserving visuals with an explicit PC combat/collision adapter.
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
    bool IsCombatReady() const;
    bool GetCombatSpawns(FVector& AyaFeet, FVector& EnemyFeet, float& AyaYaw, float& EnemyYaw) const;
    FVector MoveCombatCapsule(const FVector& Feet, const FVector& Delta, float Radius, float Height, float StepHeight, bool& Blocked) const;
    bool TraceCombatScene(const FVector& Start, const FVector& End, FVector& Hit, float& Distance) const;
    bool TraceCombatEnemy(const FVector& Start, const FVector& End, float& Distance) const;
    bool GetCombatMuzzle(FVector& Origin, FVector& Direction) const;
    void SetCombatActors(const FVector& AyaFeet, float AyaYaw, const FVector& EnemyFeet, float EnemyYaw, float HitFraction, bool Dead);
    void SetCombatAnimation(bool Firing, bool Moving);
    int32 CombatSolidTriangles() const;
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
