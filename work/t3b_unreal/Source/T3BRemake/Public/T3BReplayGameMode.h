#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "T3BReplayGameMode.generated.h"

UCLASS()
class T3BREMAKE_API AT3BReplayGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    AT3BReplayGameMode();
    virtual void StartPlay() override;
    virtual void HandleStartingNewPlayer_Implementation(APlayerController* NewPlayer) override;
};
