#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "T3BCombatDirector.generated.h"

class AT3BReplayWorld;
class AT3BCombatPawn;

// PC combat adapter. Geometry, weapon poses and nearest-hit queries come from
// the original source replay; AI, health and Overdive timing are M1 rules.
UCLASS()
class T3BREMAKE_API AT3BCombatDirector : public AActor
{
    GENERATED_BODY()
public:
    AT3BCombatDirector();
    virtual void Tick(float DeltaSeconds) override;
    void SetPawn(AT3BCombatPawn* InPawn);
    UFUNCTION(BlueprintCallable) void ResetCombat();
    UFUNCTION(BlueprintCallable) void ToggleLock();
    UFUNCTION(BlueprintCallable) void SetFireHeld(bool Held);
    UFUNCTION(BlueprintCallable) bool BeginOverdive();
    UFUNCTION(BlueprintCallable) void Reload();
    UFUNCTION(BlueprintCallable) void StartSmokeTest();
    UFUNCTION(BlueprintCallable) bool WriteCombatProbe();
    FVector GetPlayerFeet() const { return PlayerFeet; }
    FVector GetEnemyFeet() const { return EnemyFeet; }
    float GetPlayerHealth() const { return PlayerHealth; }
    float GetEnemyHealth() const { return EnemyHealth; }
    int32 GetAmmo() const { return Ammo; }
    int32 MaxAmmo() const { return 30; }
    bool IsLocked() const { return bLocked; }
    bool IsOverdiving() const { return OverdivePhase != 0; }
    bool IsEnemyDead() const { return EnemyHealth <= 0; }
    bool IsReady() const { return bReady; }
    FString GetStatusText() const;
    bool GetOverdiveCamera(float& Blend, FVector& Location, FVector& Target) const;
protected:
    virtual void BeginPlay() override;
private:
    bool Initialize();
    void UpdateCombat(float DeltaSeconds);
    void UpdateEnemy(float DeltaSeconds);
    void MovePlayer(const FVector& Delta);
    void UpdateLockAim();
    void Shoot();
    bool ResolveShot(const FVector& Origin, const FVector& Direction, float Range, FVector& End, bool& Blocked);
    void Present();
    void AdvanceSmoke(float DeltaSeconds);
    void RecordSmoke(const FString& Name, bool Passed);
    UPROPERTY(Transient) TObjectPtr<AT3BReplayWorld> Replay;
    UPROPERTY(Transient) TObjectPtr<AT3BCombatPawn> Pawn;
    FVector PlayerFeet = FVector::ZeroVector;
    FVector EnemyFeet = FVector::ZeroVector;
    FVector PlayerSpawn = FVector::ZeroVector;
    FVector EnemySpawn = FVector::ZeroVector;
    FVector ShotOrigin = FVector::ZeroVector;
    FVector ShotEnd = FVector::ZeroVector;
    float PlayerYaw = 0, EnemyYaw = 0, SpawnYaw = 0, EnemySpawnYaw = 0;
    float PlayerHealth = 100, EnemyHealth = 100;
    float FireCooldown = 0, EnemyAttackCooldown = 1, HitTime = 0, ShotTime = 0;
    float ReloadTime = 0, OverdiveTime = 0, OverdiveCooldown = 0;
    int32 Ammo = 30, OverdivePhase = 0;
    int32 Shots = 0, Hits = 0, BlockedShots = 0, Misses = 0, MovementBlocks = 0;
    int32 OverdiveEntries = 0, OverdiveReturns = 0, EnemyAttacks = 0;
    bool bReady = false, bLocked = false, bFireHeld = false, bExternalFireHeld = false, bMoving = false;
    bool bSmokeRequested = false;
    bool bSmoke = false, bSmokeComplete = false, bSmokePassed = false;
    int32 SmokeStage = 0, SmokeFrames = 0;
    float SmokeTime = 0;
    float SmokeSceneDistance = -1, SmokeEnemyDistance = -1, SmokeWallStopY = 0, SmokeAttackDamage = 0;
    FString RunId;
    TArray<FString> SmokeNames;
    TArray<bool> SmokeResults;
};
