#include "T3BCombatPawn.h"
#include "T3BCombatDirector.h"
#include "T3BReplayWorld.h"
#include "Camera/CameraComponent.h"
#include "Components/InputComponent.h"
#include "Components/SceneComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"

AT3BCombatPawn::AT3BCombatPawn()
{
    PrimaryActorTick.bCanEverTick = true;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("CombatRoot"));
    ShoulderCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("ShoulderCamera"));
    ShoulderCamera->SetupAttachment(RootComponent);
    ShoulderCamera->FieldOfView = 65.0f;
    ShoulderCamera->bUsePawnControlRotation = false;
}

void AT3BCombatPawn::BeginPlay()
{
    Super::BeginPlay();
    for (TActorIterator<AT3BReplayWorld> It(GetWorld()); It; ++It) { ReplayWorld = *It; break; }
}

void AT3BCombatPawn::SetDirector(AT3BCombatDirector* InDirector)
{
    if (Director) RemoveTickPrerequisiteActor(Director);
    Director = InDirector;
    if (Director) AddTickPrerequisiteActor(Director);
}

void AT3BCombatPawn::SetupPlayerInputComponent(UInputComponent* Input)
{
    Super::SetupPlayerInputComponent(Input);
    Input->BindAxisKey(EKeys::MouseX, this, &AT3BCombatPawn::LookYaw);
    Input->BindAxisKey(EKeys::MouseY, this, &AT3BCombatPawn::LookPitch);
    Input->BindKey(EKeys::Tab, IE_Pressed, this, &AT3BCombatPawn::LockPressed);
    Input->BindKey(EKeys::RightMouseButton, IE_Pressed, this, &AT3BCombatPawn::LockPressed);
    Input->BindKey(EKeys::E, IE_Pressed, this, &AT3BCombatPawn::OverdivePressed);
    Input->BindKey(EKeys::Q, IE_Pressed, this, &AT3BCombatPawn::OverdivePressed);
    Input->BindKey(EKeys::F, IE_Pressed, this, &AT3BCombatPawn::OverdivePressed);
    Input->BindKey(EKeys::R, IE_Pressed, this, &AT3BCombatPawn::ReloadPressed);
    Input->BindKey(EKeys::BackSpace, IE_Pressed, this, &AT3BCombatPawn::ResetPressed);
    Input->BindKey(EKeys::Escape, IE_Pressed, this, &AT3BCombatPawn::ReleaseMouse);
    Input->BindKey(EKeys::LeftMouseButton, IE_Pressed, this, &AT3BCombatPawn::CaptureMouse);
    if (APlayerController* PC = Cast<APlayerController>(GetController()))
    {
        PC->bShowMouseCursor = false;
        PC->SetInputMode(FInputModeGameOnly());
    }
}

void AT3BCombatPawn::SetCombatPose(const FVector& Feet, float YawDegrees)
{
    SetActorLocationAndRotation(Feet, FRotator(0.0f, YawDegrees, 0.0f));
}

bool AT3BCombatPawn::KeyHeld(const FKey& Key) const
{
    const APlayerController* PC = Cast<APlayerController>(GetController());
    return PC && !PC->bShowMouseCursor && PC->IsInputKeyDown(Key);
}

FVector2D AT3BCombatPawn::GetMoveInput() const
{
    return FVector2D(float(KeyHeld(EKeys::W)) - float(KeyHeld(EKeys::S)),
                     float(KeyHeld(EKeys::D)) - float(KeyHeld(EKeys::A))).GetClampedToMaxSize(1.0f);
}

FVector AT3BCombatPawn::GetAimDirection() const
{
    return GetController() ? GetController()->GetControlRotation().Vector() : FVector(0.0, -1.0, 0.0);
}

void AT3BCombatPawn::GetCameraAimRay(FVector& Origin, FVector& Direction) const
{
    Origin = ShoulderCamera->GetComponentLocation();
    Direction = ShoulderCamera->GetForwardVector();
}

bool AT3BCombatPawn::IsSprinting() const { return KeyHeld(EKeys::LeftShift) || KeyHeld(EKeys::RightShift); }
bool AT3BCombatPawn::IsFireHeld() const { return KeyHeld(EKeys::LeftMouseButton); }
bool AT3BCombatPawn::ConsumeLockPressed() { const bool Value = bLockPressed; bLockPressed = false; return Value; }
bool AT3BCombatPawn::ConsumeOverdivePressed() { const bool Value = bOverdivePressed; bOverdivePressed = false; return Value; }
bool AT3BCombatPawn::ConsumeReloadPressed() { const bool Value = bReloadPressed; bReloadPressed = false; return Value; }
bool AT3BCombatPawn::ConsumeResetPressed() { const bool Value = bResetPressed; bResetPressed = false; return Value; }
void AT3BCombatPawn::LockPressed() { if (const auto* PC = Cast<APlayerController>(GetController()); PC && !PC->bShowMouseCursor) bLockPressed = true; }
void AT3BCombatPawn::OverdivePressed() { if (const auto* PC = Cast<APlayerController>(GetController()); PC && !PC->bShowMouseCursor) bOverdivePressed = true; }
void AT3BCombatPawn::ReloadPressed() { if (const auto* PC = Cast<APlayerController>(GetController()); PC && !PC->bShowMouseCursor) bReloadPressed = true; }
void AT3BCombatPawn::ResetPressed() { if (const auto* PC = Cast<APlayerController>(GetController()); PC && !PC->bShowMouseCursor) bResetPressed = true; }

void AT3BCombatPawn::ReleaseMouse()
{
    if (APlayerController* PC = Cast<APlayerController>(GetController()))
    {
        PC->bShowMouseCursor = true;
        bLockPressed = bOverdivePressed = bReloadPressed = bResetPressed = false;
        FInputModeGameAndUI Mode;
        Mode.SetHideCursorDuringCapture(false);
        Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
        PC->SetInputMode(Mode);
    }
}

void AT3BCombatPawn::CaptureMouse()
{
    if (APlayerController* PC = Cast<APlayerController>(GetController()))
    {
        PC->bShowMouseCursor = false;
        PC->SetInputMode(FInputModeGameOnly());
    }
}

void AT3BCombatPawn::LookYaw(float Value)
{
    if (!GetController() || Value == 0.0f) return;
    if (const auto* PC = Cast<APlayerController>(GetController()); PC && PC->bShowMouseCursor) return;
    FRotator View = GetController()->GetControlRotation();
    View.Yaw += Value * 1.5f;
    GetController()->SetControlRotation(View);
}

void AT3BCombatPawn::LookPitch(float Value)
{
    if (!GetController() || Value == 0.0f) return;
    if (const auto* PC = Cast<APlayerController>(GetController()); PC && PC->bShowMouseCursor) return;
    FRotator View = GetController()->GetControlRotation();
    View.Pitch = FMath::Clamp(FRotator::NormalizeAxis(View.Pitch) - Value * 1.1f, -55.0f, 50.0f);
    GetController()->SetControlRotation(View);
}

void AT3BCombatPawn::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!ReplayWorld)
        for (TActorIterator<AT3BReplayWorld> It(GetWorld()); It; ++It) { ReplayWorld = *It; break; }
    if (!Director)
        for (TActorIterator<AT3BCombatDirector> It(GetWorld()); It; ++It) { SetDirector(*It); break; }

    AController* ViewController = GetController();
    FRotator View = ViewController ? ViewController->GetControlRotation() : FRotator(-8.0, -90.0, 0.0);
    const FVector Pivot = GetActorLocation() + FVector(0.0, 0.0, 132.0);
    if (Director && Director->IsLocked() && !Director->IsEnemyDead() && ViewController)
    {
        FRotator Desired = (Director->GetEnemyFeet() + FVector(0.0, 0.0, 100.0) - Pivot).Rotation();
        Desired.Pitch = FMath::Clamp(Desired.Pitch, -55.0f, 50.0f);
        View = FMath::RInterpTo(View, Desired, DeltaSeconds, 8.0f);
        View.Roll = 0.0f;
        ViewController->SetControlRotation(View);
    }
    const FVector Right = FRotationMatrix(View).GetUnitAxis(EAxis::Y);
    FVector CameraLocation = Pivot + Right * 42.0 - View.Vector() * 265.0;
    FVector Hit;
    float Distance = 0.0f;
    if (ReplayWorld && ReplayWorld->TraceCombatScene(Pivot, CameraLocation, Hit, Distance))
    {
        const FVector Ray = (CameraLocation - Pivot).GetSafeNormal();
        CameraLocation = Pivot + Ray * FMath::Max(12.0f, Distance - 12.0f);
    }

    float DiveBlend = 0.0f;
    FVector DiveLocation, DiveTarget;
    if (Director && Director->GetOverdiveCamera(DiveBlend, DiveLocation, DiveTarget))
    {
        CameraLocation = FMath::Lerp(CameraLocation, DiveLocation, FMath::Clamp(DiveBlend, 0.0f, 1.0f));
        const FQuat DiveView = (DiveTarget - CameraLocation).Rotation().Quaternion();
        View = FQuat::Slerp(View.Quaternion(), DiveView, FMath::Clamp(DiveBlend, 0.0f, 1.0f)).Rotator();
    }
    // Resolve the final blended path too, so entering or returning cannot move through a wall.
    if (ReplayWorld && ReplayWorld->TraceCombatScene(Pivot, CameraLocation, Hit, Distance))
        CameraLocation = Pivot + (CameraLocation - Pivot).GetSafeNormal() * FMath::Max(12.0f, Distance - 12.0f);
    ShoulderCamera->SetWorldLocationAndRotation(CameraLocation, View);
}
