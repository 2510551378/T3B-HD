#include "T3BCombatDirector.h"
#include "T3BCombatPawn.h"
#include "T3BReplayWorld.h"
#include "Dom/JsonObject.h"
#include "DrawDebugHelpers.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "Misc/FileHelper.h"
#include "Misc/EngineVersion.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "HAL/PlatformMisc.h"
#include "Serialization/JsonSerializer.h"

DEFINE_LOG_CATEGORY_STATIC(LogT3BCombat, Log, All);

AT3BCombatDirector::AT3BCombatDirector()
{
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.TickGroup = TG_PrePhysics;
}

void AT3BCombatDirector::BeginPlay()
{
    Super::BeginPlay();
    bSmokeRequested = FParse::Param(FCommandLine::Get(), TEXT("T3BCombatSmoke"));
    Initialize();
}

void AT3BCombatDirector::SetPawn(AT3BCombatPawn* InPawn) { Pawn = InPawn; }

bool AT3BCombatDirector::Initialize()
{
    if (!Replay) for (TActorIterator<AT3BReplayWorld> It(GetWorld()); It; ++It) { Replay = *It; break; }
    if (!Pawn) for (TActorIterator<AT3BCombatPawn> It(GetWorld()); It; ++It) { Pawn = *It; break; }
    if (!Replay || !Replay->IsCombatReady()) return false;
    if (!Replay->GetCombatSpawns(PlayerSpawn, EnemySpawn, SpawnYaw, EnemySpawnYaw)) return false;
    bReady = true;
    AddTickPrerequisiteActor(Replay);
    ResetCombat();
    UE_LOG(LogT3BCombat, Display, TEXT("M1 combat ready: source collision, posed target triangles, synchronized weapon, PC combat rules."));
    return true;
}

void AT3BCombatDirector::ResetCombat()
{
    if (!bReady) return;
    bSmokeComplete = bSmokePassed = false;
    if (!bSmoke)
    {
        SmokeNames.Reset(); SmokeResults.Reset(); SmokeFrames = 0; SmokeTime = 0;
        SmokeSceneDistance = SmokeEnemyDistance = -1; SmokeWallStopY = SmokeAttackDamage = 0;
    }
    RunId = FGuid::NewGuid().ToString(EGuidFormats::DigitsWithHyphens);
    PlayerFeet = PlayerSpawn; EnemyFeet = EnemySpawn;
    PlayerYaw = SpawnYaw; EnemyYaw = EnemySpawnYaw;
    PlayerHealth = EnemyHealth = 100;
    Ammo = MaxAmmo(); FireCooldown = ReloadTime = HitTime = ShotTime = 0;
    EnemyAttackCooldown = 1; OverdivePhase = 0; OverdiveTime = OverdiveCooldown = 0;
    bLocked = bFireHeld = bExternalFireHeld = bMoving = false;
    Shots = Hits = BlockedShots = Misses = MovementBlocks = 0;
    OverdiveEntries = OverdiveReturns = EnemyAttacks = 0;
    Present();
}

void AT3BCombatDirector::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!bReady && !Initialize()) return;
    if (bSmokeRequested) { bSmokeRequested = false; StartSmokeTest(); }
    if (!Pawn) for (TActorIterator<AT3BCombatPawn> It(GetWorld()); It; ++It) { Pawn = *It; break; }
    // Bound large hitches and substep movement/AI so a stalled editor cannot
    // teleport a capsule through a thin source triangle or discharge a burst.
    const float FrameDelta = FMath::Clamp(DeltaSeconds, 0.f, .25f);
    if (bSmoke) AdvanceSmoke(FrameDelta);
    if (Pawn && !bSmoke)
    {
        if (Pawn->ConsumeResetPressed()) ResetCombat();
        if (Pawn->ConsumeReloadPressed()) { if (PlayerHealth <= 0 || IsEnemyDead()) ResetCombat(); else Reload(); }
        if (Pawn->ConsumeLockPressed()) ToggleLock();
        if (Pawn->ConsumeOverdivePressed()) BeginOverdive();
        bFireHeld = Pawn->IsFireHeld() || bExternalFireHeld;
        const FVector2D Input = Pawn->GetMoveInput().GetClampedToMaxSize(1.f);
        bMoving = Input.SizeSquared() > .001 && PlayerHealth > 0 && !IsOverdiving();
        if (bMoving)
        {
            FVector Forward = Pawn->GetAimDirection(); Forward.Z = 0; Forward.Normalize();
            const FVector Right(-Forward.Y, Forward.X, 0);
            const FVector Velocity = (Forward * Input.X + Right * Input.Y) * (Pawn->IsSprinting() ? 260.f : 160.f);
            for (float Left = FrameDelta; Left > SMALL_NUMBER; Left -= 1.f / 60.f)
                MovePlayer(Velocity * FMath::Min(Left, 1.f / 60.f));
        }
        if (!bLocked && !IsOverdiving() && PlayerHealth > 0)
            PlayerYaw = Pawn->GetAimDirection().Rotation().Yaw;
    }
    UpdateCombat(FrameDelta);
    Present();
    if (ShotTime > 0) DrawDebugLine(GetWorld(), ShotOrigin, ShotEnd, FColor(255, 180, 45), false, 0, 0, 1.5f);
}

void AT3BCombatDirector::MovePlayer(const FVector& Delta)
{
    bool Blocked = false;
    PlayerFeet = Replay->MoveCombatCapsule(PlayerFeet, Delta, 22.f, 170.f, 25.f, Blocked);
    if (Blocked) ++MovementBlocks;
}

void AT3BCombatDirector::ToggleLock()
{
    if (!bReady || PlayerHealth <= 0 || IsOverdiving()) return;
    if (bLocked) { bLocked = false; return; }
    if (IsEnemyDead() || FVector::DistSquared(PlayerFeet, EnemyFeet) > FMath::Square(1000.f)) return;
    FVector Hit; float Distance = 0;
    const FVector Start = PlayerFeet + FVector(0, 0, 130);
    const FVector End = EnemyFeet + FVector(0, 0, 105);
    if (Replay->TraceCombatScene(Start, End, Hit, Distance) && Distance < FVector::Distance(Start, End) - 1.f) return;
    bLocked = true;
    UpdateLockAim();
    Present();
}

void AT3BCombatDirector::UpdateLockAim()
{
    if (!bLocked) return;
    if (IsEnemyDead() || PlayerHealth <= 0 || FVector::DistSquared(PlayerFeet, EnemyFeet) > FMath::Square(1100.f))
    { bLocked = false; return; }
    FVector Hit; float Distance = 0;
    const FVector Start = PlayerFeet + FVector(0, 0, 130), Target = EnemyFeet + FVector(0, 0, 105);
    if (Replay->TraceCombatScene(Start, Target, Hit, Distance) && Distance < FVector::Distance(Start, Target) - 1.f)
    { bLocked = false; return; }
    PlayerYaw = (Target - PlayerFeet).Rotation().Yaw;
    // Correct the source clip's horizontal barrel heading, preserving its raw
    // affine weapon pose. A lock never bypasses the actual muzzle ray below.
    for (int32 I = 0; I < 2; ++I)
    {
        Replay->SetCombatActors(PlayerFeet, PlayerYaw, EnemyFeet, EnemyYaw, HitTime / .28f, IsEnemyDead());
        FVector Origin, Direction;
        if (!Replay->GetCombatMuzzle(Origin, Direction)) break;
        const float Correction = FMath::FindDeltaAngleDegrees(Direction.Rotation().Yaw, (Target - Origin).Rotation().Yaw);
        PlayerYaw = FMath::UnwindDegrees(PlayerYaw + Correction);
    }
}

void AT3BCombatDirector::SetFireHeld(bool Held) { bExternalFireHeld = bFireHeld = Held; }

void AT3BCombatDirector::Reload()
{
    if (!bReady || PlayerHealth <= 0 || IsOverdiving() || Ammo == MaxAmmo() || ReloadTime > 0) return;
    ReloadTime = 1.2f;
}

bool AT3BCombatDirector::ResolveShot(const FVector& Origin, const FVector& Direction, float Range, FVector& End, bool& Blocked)
{
    const FVector Unit = Direction.GetSafeNormal();
    End = Origin + Unit * Range; Blocked = false;
    if (Unit.IsNearlyZero()) return false;
    float SceneDistance = Range, EnemyDistance = Range;
    FVector ScenePoint;
    const bool SceneHit = Replay->TraceCombatScene(Origin, End, ScenePoint, SceneDistance);
    const bool EnemyHit = !IsEnemyDead() && Replay->TraceCombatEnemy(Origin, End, EnemyDistance);
    // Equal distances select the scene so an actor cannot be hit through a
    // coplanar wall. Both tests use the same finite world-space segment.
    if (SceneHit && (!EnemyHit || SceneDistance <= EnemyDistance + .05f))
    { End = ScenePoint; Blocked = true; return false; }
    if (EnemyHit) { End = Origin + Unit * EnemyDistance; return true; }
    return false;
}

void AT3BCombatDirector::Shoot()
{
    if (!bReady || PlayerHealth <= 0 || IsEnemyDead() || IsOverdiving() || ReloadTime > 0 || FireCooldown > 0 || Ammo <= 0) return;
    FVector Direction;
    if (!Replay->GetCombatMuzzle(ShotOrigin, Direction)) return;
    FireCooldown = .22f; ShotTime = .075f; --Ammo; ++Shots;
    bool Blocked = false;
    const bool Hit = ResolveShot(ShotOrigin, Direction, bLocked ? 1000.f : 800.f, ShotEnd, Blocked);
    if (Blocked) ++BlockedShots;
    else if (Hit)
    {
        ++Hits; HitTime = .28f;
        EnemyHealth = FMath::Max(0.f, EnemyHealth - 25.f);
        if (IsEnemyDead()) { bLocked = false; bFireHeld = false; }
    }
    else ++Misses;
    UE_LOG(LogT3BCombat, Display, TEXT("Shot %d: hit=%d blocked=%d ammo=%d enemyHP=%.0f; source muzzle %.3f %.3f %.3f"), Shots, Hit, Blocked, Ammo, EnemyHealth, ShotOrigin.X, ShotOrigin.Y, ShotOrigin.Z);
}

bool AT3BCombatDirector::BeginOverdive()
{
    if (!bReady || !bLocked || IsEnemyDead() || PlayerHealth <= 0 || IsOverdiving() || OverdiveCooldown > 0) return false;
    OverdivePhase = 1; OverdiveTime = 0; ++OverdiveEntries; bFireHeld = false;
    return true;
}

bool AT3BCombatDirector::GetOverdiveCamera(float& Blend, FVector& Location, FVector& Target) const
{
    if (!IsOverdiving()) { Blend = 0; return false; }
    Blend = OverdivePhase == 1 ? OverdiveTime / .32f : (OverdivePhase == 2 ? 1.f : 1.f - OverdiveTime / .32f);
    Blend = FMath::SmoothStep(0.f, 1.f, FMath::Clamp(Blend, 0.f, 1.f));
    // Keep the inspection camera outside the large original Twisted body.
    // The C adapter's 85 cm offset entered this source mesh on UE renders.
    Location = EnemyFeet + FVector(-220, -180, 160); Target = EnemyFeet + FVector(0, 0, 105);
    return true;
}

void AT3BCombatDirector::UpdateCombat(float Delta)
{
    FireCooldown = FMath::Max(0.f, FireCooldown - Delta);
    ShotTime = FMath::Max(0.f, ShotTime - Delta); HitTime = FMath::Max(0.f, HitTime - Delta);
    OverdiveCooldown = FMath::Max(0.f, OverdiveCooldown - Delta);
    if (ReloadTime > 0) { ReloadTime = FMath::Max(0.f, ReloadTime - Delta); if (ReloadTime == 0) Ammo = MaxAmmo(); }
    if (IsOverdiving())
    {
        OverdiveTime += Delta;
        const float Duration = OverdivePhase == 2 ? 1.f : .32f;
        if (OverdiveTime >= Duration || IsEnemyDead() || PlayerHealth <= 0)
        {
            OverdiveTime = 0;
            if (OverdivePhase == 3 || IsEnemyDead() || PlayerHealth <= 0)
            { OverdivePhase = 0; OverdiveCooldown = 3.f; ++OverdiveReturns; }
            else ++OverdivePhase;
        }
    }
    if (!bSmoke) UpdateEnemy(Delta);
    Present(); // Select this frame's action and place the moved target first.
    UpdateLockAim();
    Present(); // Calibrated muzzle and posed target now belong to the same frame.
    if (bFireHeld) Shoot();
    if (PlayerHealth <= 0) { bFireHeld = bLocked = false; }
}

void AT3BCombatDirector::UpdateEnemy(float Delta)
{
    if (!IsEnemyDead() && PlayerHealth > 0 && !IsOverdiving())
    {
        FVector ToPlayer = PlayerFeet - EnemyFeet; ToPlayer.Z = 0;
        const float Distance = ToPlayer.Size(); EnemyYaw = ToPlayer.Rotation().Yaw;
        if (Distance > 150.f && HitTime <= 0)
        {
            bool Blocked = false;
            for (float Left = Delta; Left > SMALL_NUMBER; Left -= 1.f / 60.f)
                EnemyFeet = Replay->MoveCombatCapsule(EnemyFeet, ToPlayer.GetSafeNormal() * 55.f * FMath::Min(Left, 1.f / 60.f), 26.f, 170.f, 25.f, Blocked);
        }
        EnemyAttackCooldown = FMath::Max(0.f, EnemyAttackCooldown - Delta);
        if (Distance < 175.f && EnemyAttackCooldown <= 0 && HitTime <= 0)
        {
            FVector Hit; float WallDistance = 0;
            if (!Replay->TraceCombatScene(EnemyFeet + FVector(0, 0, 100), PlayerFeet + FVector(0, 0, 100), Hit, WallDistance))
            { PlayerHealth = FMath::Max(0.f, PlayerHealth - 20.f); ++EnemyAttacks; }
            EnemyAttackCooldown = 1.4f;
        }
    }
}

void AT3BCombatDirector::Present()
{
    if (!Replay) return;
    Replay->SetCombatActors(PlayerFeet, PlayerYaw, EnemyFeet, EnemyYaw, HitTime / .28f, IsEnemyDead());
    Replay->SetCombatAnimation(bFireHeld && PlayerHealth > 0 && !IsEnemyDead() && Ammo > 0 && !IsOverdiving() && ReloadTime <= 0, bMoving);
    if (Pawn) Pawn->SetCombatPose(PlayerFeet, PlayerYaw);
}

FString AT3BCombatDirector::GetStatusText() const
{
    if (!bReady) return TEXT("Loading M1...");
    if (PlayerHealth <= 0) return TEXT("AYA DOWN | R / Backspace: Restart");
    if (IsEnemyDead()) return TEXT("M1 CLEAR | R / Backspace: Restart");
    if (IsOverdiving()) return TEXT("OVERDIVE");
    if (ReloadTime > 0) return TEXT("RELOADING");
    if (Ammo == 0) return TEXT("EMPTY | R: Reload");
    return FString::Printf(TEXT("%s | Overdive %s"), bLocked ? TEXT("LOCKED") : TEXT("FREE AIM"), OverdiveCooldown > 0 ? TEXT("cooldown") : TEXT("ready"));
}

void AT3BCombatDirector::RecordSmoke(const FString& Name, bool Passed)
{
    SmokeNames.Add(Name); SmokeResults.Add(Passed);
    UE_LOG(LogT3BCombat, Display, TEXT("Combat smoke %s=%d"), *Name, Passed);
}

void AT3BCombatDirector::StartSmokeTest()
{
    if (!bReady && !Initialize()) return;
    ResetCombat(); bSmoke = true; bSmokeComplete = bSmokePassed = false;
    SmokeStage = SmokeFrames = 0; SmokeTime = 0; SmokeNames.Reset(); SmokeResults.Reset();
    // This measured source wall is triangle 6612 / material 35, not a missing
    // floor edge. Sweep through it with the same capsule method as player input.
    PlayerFeet = FVector(0, 0, .17093f);
    MovePlayer(FVector(0, -2000, 0));
    SmokeWallStopY = float(PlayerFeet.Y);
    RecordSmoke(TEXT("source_capsule_wall_blocks_movement"), MovementBlocks > 0 && PlayerFeet.Y > -1560 && PlayerFeet.Y < -1500);
    // Put a real posed target behind that wall. Require both intersections
    // before checking that the production nearest-hit resolver selects scene.
    PlayerFeet = FVector(0, -1200, .170725f); EnemyFeet = FVector(0, -1800, .17062f);
    EnemyYaw = EnemySpawnYaw; Present();
    const FVector Origin = PlayerFeet + FVector(0, 0, 130), Target = EnemyFeet + FVector(0, 0, 105);
    FVector Wall, End; float SceneDistance = 0, EnemyDistance = 0;
    const bool SceneHit = Replay->TraceCombatScene(Origin, Target, Wall, SceneDistance);
    const bool TargetHit = Replay->TraceCombatEnemy(Origin, Target, EnemyDistance);
    SmokeSceneDistance = SceneHit ? SceneDistance : -1;
    SmokeEnemyDistance = TargetHit ? EnemyDistance : -1;
    const float PreviousHealth = EnemyHealth; bool Blocked = false;
    const bool Hit = ResolveShot(Origin, Target - Origin, FVector::Distance(Origin, Target), End, Blocked);
    RecordSmoke(TEXT("source_wall_occludes_real_enemy"), SceneHit && TargetHit && SceneDistance < EnemyDistance && !Hit && Blocked && EnemyHealth == PreviousHealth && FVector::Distance(End, Wall) < .01f);
    // Exercise real close-range AI damage and reload/reset state transitions;
    // the visible encounter below then starts from the unchanged source spawn.
    PlayerFeet = EnemySpawn + FVector(0, 140, 0); EnemyFeet = EnemySpawn; EnemyAttackCooldown = 0;
    Present(); UpdateEnemy(1.f / 60.f);
    SmokeAttackDamage = 100 - PlayerHealth;
    RecordSmoke(TEXT("enemy_production_melee_damages_aya"), PlayerHealth == 80 && EnemyAttacks == 1);
    Ammo = MaxAmmo() - 1; Reload();
    const bool ReloadStarted = ReloadTime > 0 && Ammo == MaxAmmo() - 1;
    UpdateCombat(.6f); const bool ReloadWaits = Ammo == MaxAmmo() - 1;
    UpdateCombat(.61f);
    RecordSmoke(TEXT("reload_timer_restores_full_ammo"), ReloadStarted && ReloadWaits && Ammo == MaxAmmo());
    ResetCombat();
    RecordSmoke(TEXT("reset_restores_health_ammo_spawn"), PlayerHealth == 100 && EnemyHealth == 100 && Ammo == MaxAmmo() && PlayerFeet.Equals(PlayerSpawn) && EnemyFeet.Equals(EnemySpawn) && !bLocked);
    ToggleLock(); RecordSmoke(TEXT("lock_visible_live_target"), bLocked);
    RecordSmoke(TEXT("overdive_enter"), BeginOverdive());
    RecordSmoke(TEXT("overdive_reentry_denied"), !BeginOverdive());
    WriteCombatProbe();
}

void AT3BCombatDirector::AdvanceSmoke(float Delta)
{
    SmokeTime += Delta; ++SmokeFrames;
    if (SmokeStage == 0 && (OverdiveReturns > 0 || SmokeTime > 5.f))
    {
        RecordSmoke(TEXT("overdive_automatic_return"), OverdiveReturns > 0 && !IsOverdiving());
        RecordSmoke(TEXT("overdive_cooldown_denies_entry"), !BeginOverdive());
        SmokeStage = 1; bFireHeld = true;
    }
    if (SmokeStage == 1 && (IsEnemyDead() || SmokeTime > 14.f))
    {
        RecordSmoke(TEXT("source_muzzle_hits_posed_enemy_triangles"), Hits > 0);
        RecordSmoke(TEXT("enemy_hit_and_death"), Hits >= 4 && IsEnemyDead());
        RecordSmoke(TEXT("continuous_shooting_ammo_rate"), Shots >= 4 && Ammo == MaxAmmo() - Shots);
        RecordSmoke(TEXT("dead_target_unlocks"), !bLocked);
        bSmokeComplete = true; bSmokePassed = true;
        for (bool Result : SmokeResults) bSmokePassed &= Result;
        bSmoke = false; bFireHeld = false;
        WriteCombatProbe();
        UE_LOG(LogT3BCombat, Display, TEXT("Combat smoke completed passed=%d frames=%d elapsed=%.4f"), bSmokePassed, SmokeFrames, SmokeTime);
        if (FParse::Param(FCommandLine::Get(), TEXT("T3BCombatSmokeExit"))) FPlatformMisc::RequestExit(false);
    }
}

bool AT3BCombatDirector::WriteCombatProbe()
{
    const auto Object = MakeShared<FJsonObject>();
    Object->SetStringField(TEXT("schema"), TEXT("t3b-ue-combat-slice/v1"));
    Object->SetStringField(TEXT("engine_version"), FEngineVersion::Current().ToString());
    Object->SetStringField(TEXT("run_id"), RunId);
    Object->SetNumberField(TEXT("solid_triangles"), Replay ? Replay->CombatSolidTriangles() : 0);
    Object->SetBoolField(TEXT("ready"), bReady);
    Object->SetBoolField(TEXT("smoke_complete"), bSmokeComplete);
    Object->SetBoolField(TEXT("passed"), bSmokeComplete && bSmokePassed);
    Object->SetNumberField(TEXT("smoke_frames"), SmokeFrames); Object->SetNumberField(TEXT("elapsed_seconds"), SmokeTime);
    Object->SetNumberField(TEXT("player_health"), PlayerHealth); Object->SetNumberField(TEXT("enemy_health"), EnemyHealth);
    Object->SetNumberField(TEXT("ammo"), Ammo); Object->SetNumberField(TEXT("shots"), Shots); Object->SetNumberField(TEXT("hits"), Hits);
    Object->SetNumberField(TEXT("blocked_shots"), BlockedShots); Object->SetNumberField(TEXT("misses"), Misses);
    Object->SetNumberField(TEXT("movement_blocks"), MovementBlocks); Object->SetNumberField(TEXT("enemy_attacks"), EnemyAttacks);
    Object->SetNumberField(TEXT("smoke_wall_stop_y_cm"), SmokeWallStopY);
    Object->SetNumberField(TEXT("smoke_occluder_distance_cm"), SmokeSceneDistance);
    Object->SetNumberField(TEXT("smoke_occluded_enemy_distance_cm"), SmokeEnemyDistance);
    Object->SetNumberField(TEXT("smoke_enemy_attack_damage"), SmokeAttackDamage);
    Object->SetNumberField(TEXT("overdive_entries"), OverdiveEntries); Object->SetNumberField(TEXT("overdive_returns"), OverdiveReturns);
    Object->SetBoolField(TEXT("locked"), bLocked); Object->SetBoolField(TEXT("enemy_dead"), IsEnemyDead());
    Object->SetStringField(TEXT("enemy_hit_geometry"), TEXT("current_source_posed_triangles"));
    Object->SetStringField(TEXT("collision_source"), TEXT("source_visible_triangle_adapter"));
    Object->SetStringField(TEXT("overdive_scope"), TEXT("C_M1_camera_enter_hold_return_adapter"));
    Object->SetBoolField(TEXT("original_AI_or_damage_recovered"), false);
    Object->SetBoolField(TEXT("original_hit_or_death_animation_recovered"), false);
    TArray<TSharedPtr<FJsonValue>> Checks;
    for (int32 I = 0; I < SmokeNames.Num(); ++I)
    {
        const auto Check = MakeShared<FJsonObject>(); Check->SetStringField(TEXT("name"), SmokeNames[I]); Check->SetBoolField(TEXT("passed"), SmokeResults[I]);
        Checks.Add(MakeShared<FJsonValueObject>(Check));
    }
    Object->SetArrayField(TEXT("checks"), Checks);
    FString Text; FJsonSerializer::Serialize(Object, TJsonWriterFactory<>::Create(&Text));
    const FString Directory = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Combat"));
    IFileManager::Get().MakeDirectory(*Directory, true);
    return FFileHelper::SaveStringToFile(Text, *FPaths::Combine(Directory, TEXT("m1_combat_probe.json")), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
}

namespace
{
AT3BCombatDirector* FindCombat(UWorld* World)
{
    if (World) for (TActorIterator<AT3BCombatDirector> It(World); It; ++It) return *It;
    return nullptr;
}
FAutoConsoleCommandWithWorldAndArgs SmokeCommand(TEXT("T3B.Combat.Smoke"), TEXT("Run real-world M1 collision/lock/Overdive/continuous-fire acceptance; Saved/Combat/m1_combat_probe.json."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World) { if (auto* Combat = FindCombat(World)) Combat->StartSmokeTest(); }));
FAutoConsoleCommandWithWorldAndArgs ProbeCommand(TEXT("T3B.Combat.Probe"), TEXT("Write current M1 gameplay state."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World) { if (auto* Combat = FindCombat(World)) Combat->WriteCombatProbe(); }));
FAutoConsoleCommandWithWorldAndArgs ResetCommand(TEXT("T3B.Combat.Reset"), TEXT("Restart M1 combat."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World) { if (auto* Combat = FindCombat(World)) Combat->ResetCombat(); }));
FAutoConsoleCommandWithWorldAndArgs LockCommand(TEXT("T3B.Combat.Lock"), TEXT("Toggle target lock."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World) { if (auto* Combat = FindCombat(World)) Combat->ToggleLock(); }));
FAutoConsoleCommandWithWorldAndArgs FireCommand(TEXT("T3B.Combat.Fire"), TEXT("Held fire: 0|1."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World) { if (Args.Num() == 1) if (auto* Combat = FindCombat(World)) Combat->SetFireHeld(Args[0] == TEXT("1")); }));
FAutoConsoleCommandWithWorldAndArgs OverdiveCommand(TEXT("T3B.Combat.Overdive"), TEXT("Enter locked target Overdive preview and automatically return."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World) { if (auto* Combat = FindCombat(World)) Combat->BeginOverdive(); }));
}
