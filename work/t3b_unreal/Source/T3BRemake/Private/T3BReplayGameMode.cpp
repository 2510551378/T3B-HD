#include "T3BReplayGameMode.h"
#include "T3BReplayWorld.h"
#include "T3BCombatDirector.h"
#include "T3BCombatPawn.h"
#include "T3BCombatHUD.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/SpectatorPawn.h"
#include "GameFramework/PlayerController.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

AT3BReplayGameMode::AT3BReplayGameMode()
{
    const bool ReplayOnly = FParse::Param(FCommandLine::Get(), TEXT("T3BReplayOnly"));
    DefaultPawnClass = ReplayOnly ? ASpectatorPawn::StaticClass() : AT3BCombatPawn::StaticClass();
    if (!ReplayOnly) HUDClass = AT3BCombatHUD::StaticClass();
}

void AT3BReplayGameMode::StartPlay()
{
    Super::StartPlay();
    // A map may already contain the replay actor. Never create duplicate geometry.
    bool FoundReplay = false;
    for (TActorIterator<AT3BReplayWorld> It(GetWorld()); It; ++It) { FoundReplay = true; break; }
    if (!FoundReplay) GetWorld()->SpawnActor<AT3BReplayWorld>(FVector::ZeroVector, FRotator::ZeroRotator);
    if (FParse::Param(FCommandLine::Get(), TEXT("T3BReplayOnly"))) return;
    AT3BCombatDirector* Director = nullptr;
    for (TActorIterator<AT3BCombatDirector> It(GetWorld()); It; ++It) { Director = *It; break; }
    if (!Director) Director = GetWorld()->SpawnActor<AT3BCombatDirector>();
    if (Director)
        for (TActorIterator<AT3BCombatPawn> It(GetWorld()); It; ++It) { Director->SetPawn(*It); (*It)->SetDirector(Director); break; }
}

void AT3BReplayGameMode::HandleStartingNewPlayer_Implementation(APlayerController* NewPlayer)
{
    Super::HandleStartingNewPlayer_Implementation(NewPlayer);
    if (NewPlayer && NewPlayer->GetPawn())
    {
        const bool ReplayOnly = FParse::Param(FCommandLine::Get(), TEXT("T3BReplayOnly"));
        const FVector Location = ReplayOnly ? FVector(-310.0, 55.0, 155.0) : FVector::ZeroVector;
        const FRotator View = ReplayOnly ? (FVector(40.0, 0.0, 100.0) - Location).Rotation() : FRotator(-8.0, -90.0, 0.0);
        NewPlayer->GetPawn()->SetActorLocationAndRotation(Location, View);
        NewPlayer->SetControlRotation(View);
        if (AT3BCombatPawn* Pawn = Cast<AT3BCombatPawn>(NewPlayer->GetPawn()))
            for (TActorIterator<AT3BCombatDirector> It(GetWorld()); It; ++It) { (*It)->SetPawn(Pawn); Pawn->SetDirector(*It); break; }
    }
}
