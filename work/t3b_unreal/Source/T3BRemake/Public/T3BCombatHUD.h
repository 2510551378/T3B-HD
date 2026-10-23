#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "T3BCombatHUD.generated.h"

class AT3BCombatDirector;
class AT3BReplayWorld;

UCLASS()
class T3BREMAKE_API AT3BCombatHUD : public AHUD
{
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
private:
    UPROPERTY(Transient) TObjectPtr<AT3BCombatDirector> Director;
    UPROPERTY(Transient) TObjectPtr<AT3BReplayWorld> ReplayWorld;
};
