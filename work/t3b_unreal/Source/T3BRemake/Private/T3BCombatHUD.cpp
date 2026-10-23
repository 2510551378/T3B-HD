#include "T3BCombatHUD.h"
#include "T3BCombatDirector.h"
#include "T3BReplayWorld.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"

void AT3BCombatHUD::DrawHUD()
{
    Super::DrawHUD();
    if (!Canvas) return;
    if (!Director)
        for (TActorIterator<AT3BCombatDirector> It(GetWorld()); It; ++It) { Director = *It; break; }
    if (!Director) return;
    if (!ReplayWorld)
        for (TActorIterator<AT3BReplayWorld> It(GetWorld()); It; ++It) { ReplayWorld = *It; break; }
    UFont* Font = GEngine ? GEngine->GetSmallFont() : nullptr;
    const FLinearColor White(0.93f, 0.95f, 1.0f);
    const FLinearColor Cyan(0.2f, 0.9f, 1.0f);
    const float Width = float(Canvas->SizeX);
    const float Height = float(Canvas->SizeY);
    DrawRect(FLinearColor(0.015f, 0.025f, 0.045f, 0.8f), 18.0f, 18.0f, 310.0f, 104.0f);
    DrawText(TEXT("THE 3RD BIRTHDAY  /  M1"), Cyan, 30.0f, 27.0f, Font, 1.1f);
    DrawText(FString::Printf(TEXT("AYA  HP %.0f     AMMO %d / %d"), Director->GetPlayerHealth(),
        Director->GetAmmo(), Director->MaxAmmo()), White, 30.0f, 51.0f, Font);
    DrawRect(FLinearColor(0.1f, 0.16f, 0.2f, 0.9f), 30.0f, 75.0f, 278.0f, 7.0f);
    DrawRect(Director->GetPlayerHealth() > 25.0f ? Cyan : FLinearColor(1.0f, 0.2f, 0.1f),
        30.0f, 75.0f, 278.0f * FMath::Clamp(Director->GetPlayerHealth() / 100.0f, 0.0f, 1.0f), 7.0f);
    DrawText(Director->GetStatusText(), White, 30.0f, 94.0f, Font);

    const FLinearColor Reticle = Director->IsLocked() ? Cyan : White;
    // The recovered clip supplies a real affine barrel direction. Project that
    // finite ray rather than imply the shoulder camera center is the shot path.
    FVector Origin, Direction;
    FVector2D Crosshair;
    if (ReplayWorld && PlayerOwner && !Director->IsOverdiving() &&
        ReplayWorld->GetCombatMuzzle(Origin, Direction))
    {
        const FVector End = Origin + Direction.GetSafeNormal() * 650.0f;
        FVector ScenePoint;
        float SceneDistance = 650.0f, EnemyDistance = 650.0f;
        const bool SceneHit = ReplayWorld->TraceCombatScene(Origin, End, ScenePoint, SceneDistance);
        const bool EnemyHit = !Director->IsEnemyDead() && ReplayWorld->TraceCombatEnemy(Origin, End, EnemyDistance);
        const FVector AimPoint = SceneHit && (!EnemyHit || SceneDistance <= EnemyDistance + 0.05f) ? ScenePoint :
            (EnemyHit ? Origin + Direction.GetSafeNormal() * EnemyDistance : End);
        if (PlayerOwner->ProjectWorldLocationToScreen(AimPoint, Crosshair))
        {
            const float CX = Crosshair.X, CY = Crosshair.Y;
            DrawLine(CX - 10.0f, CY, CX - 4.0f, CY, Reticle, 1.4f);
            DrawLine(CX + 4.0f, CY, CX + 10.0f, CY, Reticle, 1.4f);
            DrawLine(CX, CY - 10.0f, CX, CY - 4.0f, Reticle, 1.4f);
            DrawLine(CX, CY + 4.0f, CX, CY + 10.0f, Reticle, 1.4f);
        }
    }

    if (!Director->IsEnemyDead() && PlayerOwner)
    {
        FVector2D Screen;
        if (PlayerOwner->ProjectWorldLocationToScreen(Director->GetEnemyFeet() + FVector(0.0, 0.0, 165.0), Screen))
        {
            const float X = Screen.X - 65.0f, Y = Screen.Y;
            DrawText(Director->IsLocked() ? TEXT("TWISTED  [LOCK]") : TEXT("TWISTED"), Reticle, X, Y - 18.0f, Font);
            DrawRect(FLinearColor(0.1f, 0.1f, 0.12f, 0.9f), X, Y, 130.0f, 5.0f);
            DrawRect(FLinearColor(1.0f, 0.25f, 0.16f), X, Y, 130.0f * FMath::Clamp(Director->GetEnemyHealth() / 100.0f, 0.0f, 1.0f), 5.0f);
        }
    }
    if (Director->GetPlayerHealth() <= 0.0f || Director->IsEnemyDead())
    {
        const FString Message = Director->IsEnemyDead() ? TEXT("TWISTED DEFEATED  -  BACKSPACE TO RESTART") : TEXT("AYA DOWN  -  BACKSPACE TO RESTART");
        DrawRect(FLinearColor(0.015f, 0.025f, 0.045f, 0.85f), Width * 0.5f - 235.0f, Height * 0.28f, 470.0f, 42.0f);
        DrawText(Message, White, Width * 0.5f - 220.0f, Height * 0.28f + 12.0f, Font);
    }
    DrawRect(FLinearColor(0.015f, 0.025f, 0.045f, 0.75f), 18.0f, Height - 58.0f, FMath::Min(Width - 36.0f, 1040.0f), 40.0f);
    DrawText(TEXT("WASD Move   Mouse View   Shift Run   RMB / Tab Lock   LMB Fire"), White, 30.0f, Height - 52.0f, Font);
    DrawText(TEXT("E Overdive   R Reload   Backspace Restart   Esc Release Mouse"), White, 30.0f, Height - 34.0f, Font);
}
