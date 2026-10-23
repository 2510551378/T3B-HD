#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "T3BCombatPawn.generated.h"

class UCameraComponent;
class AT3BCombatDirector;
class AT3BReplayWorld;
struct FKey;

// Input and camera only. The director owns collision-resolved movement and combat.
UCLASS()
class T3BREMAKE_API AT3BCombatPawn : public APawn
{
    GENERATED_BODY()
public:
    AT3BCombatPawn();
    virtual void Tick(float DeltaSeconds) override;
    virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
    void SetCombatPose(const FVector& Feet, float YawDegrees);
    FVector2D GetMoveInput() const; // X = camera forward, Y = camera right.
    FVector GetAimDirection() const;
    void GetCameraAimRay(FVector& Origin, FVector& Direction) const;
    bool IsSprinting() const;
    bool IsFireHeld() const;
    bool ConsumeLockPressed();
    bool ConsumeOverdivePressed();
    bool ConsumeReloadPressed();
    bool ConsumeResetPressed();
    void SetDirector(AT3BCombatDirector* InDirector);
protected:
    virtual void BeginPlay() override;
private:
    void LookYaw(float Value);
    void LookPitch(float Value);
    void LockPressed();
    void OverdivePressed();
    void ReloadPressed();
    void ResetPressed();
    void ReleaseMouse();
    void CaptureMouse();
    bool KeyHeld(const FKey& Key) const;
    UPROPERTY(VisibleAnywhere) TObjectPtr<UCameraComponent> ShoulderCamera;
    UPROPERTY(Transient) TObjectPtr<AT3BCombatDirector> Director;
    UPROPERTY(Transient) TObjectPtr<AT3BReplayWorld> ReplayWorld;
    bool bLockPressed = false;
    bool bOverdivePressed = false;
    bool bReloadPressed = false;
    bool bResetPressed = false;
};
