#include "T3BReplayGameMode.h"
#include "T3BReplayWorld.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/SpectatorPawn.h"
#include "GameFramework/PlayerController.h"

AT3BReplayGameMode::AT3BReplayGameMode()
{
    DefaultPawnClass = ASpectatorPawn::StaticClass();
}

void AT3BReplayGameMode::StartPlay()
{
    Super::StartPlay();
    // A map may already contain the replay actor. Never create duplicate geometry.
    for (TActorIterator<AT3BReplayWorld> It(GetWorld()); It; ++It) return;
    GetWorld()->SpawnActor<AT3BReplayWorld>(FVector::ZeroVector, FRotator::ZeroRotator);
}

void AT3BReplayGameMode::HandleStartingNewPlayer_Implementation(APlayerController* NewPlayer)
{
    Super::HandleStartingNewPlayer_Implementation(NewPlayer);
    if (NewPlayer && NewPlayer->GetPawn())
    {
        const FVector Location(-310.0, 55.0, 155.0);
        const FRotator View = (FVector(40.0, 0.0, 100.0) - Location).Rotation();
        NewPlayer->GetPawn()->SetActorLocationAndRotation(Location, View);
        NewPlayer->SetControlRotation(View);
    }
}
