#include "T3BReplayWorld.h"
#include "T3BActionClip.h"
#include "T3BCombatCollision.h"
#include "T3BGEWeaponMarkers.h"
#include "T3BSourceData.h"
#include "T3BGEViewExtension.h"
#include "Engine/Texture2D.h"
#include "Components/InputComponent.h"
#include "InputCoreTypes.h"
#include "IImageWrapperModule.h"
#include "ImageCore.h"
#include "Modules/ModuleManager.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Components/SceneComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInterface.h"
#include "Misc/FileHelper.h"
#include "Misc/EngineVersion.h"
#include "Misc/Paths.h"
#include "ProceduralMeshComponent.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

DEFINE_LOG_CATEGORY_STATIC(LogT3BReplay, Log, All);

namespace
{
struct FReplayActorData
{
    FString Name;
    FString SynchronizationGroup;
    T3BSource::Skin Skin;
    std::array<float, 3> Spawn{};
    TArray<UMaterialInterface*> Materials;
    int32 Atlas = -1;
    bool Cull = false, Blend = true, DepthWrite = true;
};

struct FReplayActionClip
{
    FString Label;
    T3BAction::Pair Pair;
};

const TArray<TSharedPtr<FJsonValue>>& JsonArray(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key)
{
    const TArray<TSharedPtr<FJsonValue>>* Result = nullptr;
    if (!Object.IsValid() || !Object->TryGetArrayField(Key, Result) || !Result)
        throw T3BSource::FormatError("Manifest array missing or invalid");
    return *Result;
}

TSharedPtr<FJsonObject> JsonObject(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key)
{
    const TSharedPtr<FJsonObject>* Result = nullptr;
    if (!Object.IsValid() || !Object->TryGetObjectField(Key, Result) || !Result || !Result->IsValid())
        throw T3BSource::FormatError("Manifest object missing or invalid");
    return *Result;
}

FString JsonString(const TSharedPtr<FJsonObject>& Object, const TCHAR* Key)
{
    FString Result;
    if (!Object.IsValid() || !Object->TryGetStringField(Key, Result) || Result.IsEmpty())
        throw T3BSource::FormatError("Manifest string missing or invalid");
    return Result;
}

TSharedPtr<FJsonObject> ValueObject(const TSharedPtr<FJsonValue>& Value)
{
    if (!Value.IsValid() || Value->Type != EJson::Object)
        throw T3BSource::FormatError("Manifest array entry is not an object");
    return Value->AsObject();
}

FString BundlePath(const FString& Relative)
{
    FString Clean = Relative;
    Clean.ReplaceInline(TEXT("\\"), TEXT("/"));
    TArray<FString> Segments;
    Clean.ParseIntoArray(Segments, TEXT("/"), false);
    if (Clean.IsEmpty() || !FPaths::IsRelative(Clean) || Clean.Contains(TEXT(":")))
        throw T3BSource::FormatError("SourceData path must be a relative bundle path");
    for (const FString& Part : Segments)
        if (Part.IsEmpty() || Part == TEXT(".") || Part == TEXT(".."))
            throw T3BSource::FormatError("SourceData path contains an unsafe segment");
    return FPaths::Combine(FPaths::ProjectContentDir(), TEXT("SourceData"), Clean);
}

std::vector<std::uint8_t> ReadBundleBinary(const FString& Relative)
{
    TArray<uint8> Bytes;
    if (!FFileHelper::LoadFileToArray(Bytes, *BundlePath(Relative)))
        throw T3BSource::FormatError("Required source binary is missing or unreadable");
    return std::vector<std::uint8_t>(Bytes.GetData(), Bytes.GetData() + Bytes.Num());
}

TArray<UMaterialInterface*> LoadMaterials(const TArray<TSharedPtr<FJsonValue>>& Entries, const FString& Label)
{
    TArray<UMaterialInterface*> Result;
    for (int32 Index = 0; Index < Entries.Num(); ++Index)
    {
        const TSharedPtr<FJsonObject> Entry = ValueObject(Entries[Index]);
        const FString Asset = JsonString(Entry, TEXT("asset"));
        const FString Texture = BundlePath(JsonString(Entry, TEXT("texture")));
        if (!IFileManager::Get().FileExists(*Texture))
            throw T3BSource::FormatError("Manifest material source texture is missing");
        if (!Asset.StartsWith(TEXT("/Game/T3B/Materials/")))
            throw T3BSource::FormatError("Manifest material asset must use /Game/T3B/Materials/");
        UMaterialInterface* Material = LoadObject<UMaterialInterface>(nullptr, *Asset);
        if (!Material)
        {
            UE_LOG(LogT3BReplay, Error, TEXT("Missing required %s material[%d]: %s. Run editor source-asset creation; no default material accepted."), *Label, Index, *Asset);
            throw T3BSource::FormatError("Required UE material asset is missing");
        }
        FString Parameters;
        TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Parameters);
        FJsonSerializer::Serialize(Entry.ToSharedRef(), Writer);
        UE_LOG(LogT3BReplay, Display, TEXT("Material %s[%d] source state: %s"), *Label, Index, *Parameters);
        Result.Add(Material);
    }
    return Result;
}

FT3BGESection OrderedMaterial(const TSharedPtr<FJsonObject>& M, float ExpectedScale,
    TArray<TObjectPtr<UTexture2D>>& Atlases) {
    if (M->GetNumberField(TEXT("alpha_ref")) != 0 || !M->GetBoolField(TEXT("alpha_test")) ||
        M->GetNumberField(TEXT("rgb_scale")) != ExpectedScale || M->GetNumberField(TEXT("su")) != 1 ||
        M->GetNumberField(TEXT("sv")) != 1 || M->GetNumberField(TEXT("ou")) != 0 ||
        M->GetNumberField(TEXT("ov")) != 0 || M->GetNumberField(TEXT("wrap_s")) != 0 || M->GetNumberField(TEXT("wrap_t")) != 0)
        throw T3BSource::FormatError("Unsupported ordered source texture state");
    UTexture2D* Texture=LoadObject<UTexture2D>(nullptr,*JsonString(M,TEXT("texture_asset")));
    if (!Texture || Texture->SRGB) throw T3BSource::FormatError("Missing original linear atlas");
    int32 Index=Atlases.IndexOfByKey(Texture); if(Index==INDEX_NONE)Index=Atlases.Add(Texture);
    return {0,0,uint32(Index),M->GetNumberField(TEXT("cull"))!=0,
        M->GetNumberField(TEXT("blend"))!=0,M->GetNumberField(TEXT("depth_write"))!=0};
}

FVector UEPoint(T3BSource::Vec3 PC)
{
    const T3BSource::Vec3 U = T3BSource::ToUE(PC);
    return FVector(U.x, U.y, U.z);
}

T3BSource::Vec3 PCPoint(const FVector& UE) { return {float(-UE.Y/100),float(UE.Z/100),float(UE.X/100)}; }

bool PositiveAlphaTexture(const FString& Relative) {
    TArray<uint8> Encoded;
    if (!FFileHelper::LoadFileToArray(Encoded, *BundlePath(Relative)))
        throw T3BSource::FormatError("Collision texture is missing");
    auto& Module=FModuleManager::LoadModuleChecked<IImageWrapperModule>(TEXT("ImageWrapper"));
    FImage Image;
    if(!Module.DecompressImage(Encoded.GetData(),Encoded.Num(),Image))
        throw T3BSource::FormatError("Cannot decode collision texture alpha");
    FImage RGBA; Image.CopyTo(RGBA,ERawImageFormat::BGRA8,EGammaSpace::Linear);
    for(int64 I=3;I<RGBA.RawData.Num();I+=4) if(RGBA.RawData[I]==0)return false;
    return true;
}

void SetSection(UProceduralMeshComponent* Mesh, int32 Section, const TArray<FVector>& Points,
                const TArray<FVector2D>& UV, const TArray<FLinearColor>& Colors, bool Create)
{
    TArray<FVector> Normals;
    Normals.SetNumZeroed(Points.Num());
    for (int32 I = 0; I < Points.Num(); I += 3)
    {
        const FVector Normal = FVector::CrossProduct(Points[I + 1] - Points[I], Points[I + 2] - Points[I]).GetSafeNormal();
        Normals[I] = Normals[I + 1] = Normals[I + 2] = Normal;
    }
    TArray<FProcMeshTangent> Tangents;
    if (Create)
    {
        TArray<int32> Indices;
        Indices.Reserve(Points.Num());
        for (int32 I = 0; I < Points.Num(); ++I) Indices.Add(I);
        // Preserve source triangle/UV order. UE front-face acceptance still
        // requires an editor render check; do not silently reverse indices.
        Mesh->CreateMeshSection_LinearColor(Section, Points, Indices, Normals, UV, Colors, Tangents, false, false);
    }
    else
        Mesh->UpdateMeshSection_LinearColor(Section, Points, Normals, UV, Colors, Tangents, false);
}
}

struct FT3BReplayState
{
    T3BSource::Scene Scene;
    T3BCombat::CollisionWorld Collision;
    bool Combat=false, CombatDead=false, CombatFiring=false, CombatMoving=false;
    FVector AyaFeet=FVector::ZeroVector, EnemyFeet=FVector::ZeroVector;
    float AyaYaw=0, EnemyYaw=0, Hurt=0, DeathSeconds=0;
    TArray<FVector> EnemyVertices;
    FVector Muzzle=FVector::ZeroVector, Barrel=FVector::ForwardVector;
    bool MuzzleValid=false;
    TArray<UMaterialInterface*> SceneMaterials;
    TArray<FT3BGESection> SceneSections;
    TArray<T3BGE::GPUVertex> SceneVertices;
    std::vector<FReplayActorData> Actors;
    std::vector<FReplayActionClip> ActionClips;
    T3BGE::WeaponMarkerDefinitions WeaponMarkers;
    bool HasWeaponMarkers = false;
    FString ActiveActionClip;
    TSharedPtr<FT3BGEViewExtension, ESPMode::ThreadSafe> OrderedMaterials;
    double MaximumDuration = 0.0;
};

namespace {
const T3BSource::Skin& PlaybackSkin(const FT3BReplayState& State, const FReplayActorData& Actor) {
    for (const auto& Clip : State.ActionClips) if (Clip.Label == State.ActiveActionClip) {
        if (Actor.Name == TEXT("Aya")) return Clip.Pair.body;
        if (Actor.Name == TEXT("Weapon")) return Clip.Pair.weapon;
    }
    return Actor.Skin;
}
FVector CombatPoint(const FT3BReplayState& State,const FReplayActorData& Actor,const T3BSource::Skin& Skin,T3BSource::Vec3 P) {
    if(!State.Combat) return UEPoint(T3BSource::ToPC(Skin,P,Actor.Spawn[0],Actor.Spawn[1],Actor.Spawn[2]));
    FVector Local=UEPoint(T3BSource::ToPC(Skin,P,0,0,0));
    const bool Enemy=Actor.Name==TEXT("Twisted");
    // Death/hit are explicit PC presentation adapters, not recovered animation clips.
    const float Pitch=Enemy?(State.CombatDead?FMath::Clamp(State.DeathSeconds/.55f,0.f,1.f)*85.f:State.Hurt*9.f):0;
    return FRotator(Pitch,Enemy?State.EnemyYaw:State.AyaYaw,0).RotateVector(Local)+(Enemy?State.EnemyFeet:State.AyaFeet);
}
}
void FT3BReplayStateDeleter::operator()(FT3BReplayState* Ptr) const { delete Ptr; }

AT3BReplayWorld::AT3BReplayWorld()
{
    PrimaryActorTick.bCanEverTick = true;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("SourceReplayRoot"));
}

AT3BReplayWorld::~AT3BReplayWorld() = default;

void AT3BReplayWorld::FailReplay(const FString& Reason)
{
    bReplayReady = false;
    if (State && State->OrderedMaterials) State->OrderedMaterials->Submit(nullptr, {});
    SetActorTickEnabled(false);
    for (UProceduralMeshComponent* Mesh : ReplayMeshes) if (Mesh) Mesh->SetVisibility(false, true);
    UE_LOG(LogT3BReplay, Error, TEXT("SOURCE REPLAY FAILED: %s. Geometry hidden; no default-material success fallback."), *Reason);
    if (GEngine) GEngine->AddOnScreenDebugMessage(-1, 120.0f, FColor::Red, TEXT("T3B source replay failed. See LogT3BReplay; required data/materials must be fixed."));
}

void AT3BReplayWorld::BeginPlay()
{
    Super::BeginPlay();
    // Packed positions are already in scene world space. A map actor transform
    // must not apply an unnoticed second scale or rotation.
    if (!GetActorTransform().Equals(FTransform::Identity))
        UE_LOG(LogT3BReplay, Warning, TEXT("Resetting map replay actor transform to identity; source coordinates are absolute."));
    SetActorTransform(FTransform::Identity);
    try
    {
        bReplayReady = LoadSourceBundle();
        if (bReplayReady)
        {
            ApplyReplay(0.0f, true);
            if (FParse::Param(FCommandLine::Get(), TEXT("T3BReplayOnly"))) EnableInput(GetWorld()->GetFirstPlayerController());
            if (InputComponent && FParse::Param(FCommandLine::Get(), TEXT("T3BReplayOnly"))) {
                InputComponent->BindKey(EKeys::LeftMouseButton, IE_Pressed, this, &AT3BReplayWorld::StartFire);
                InputComponent->BindKey(EKeys::LeftMouseButton, IE_Released, this, &AT3BReplayWorld::StopFire);
            }
            UE_LOG(LogT3BReplay, Display, TEXT("Source replay loaded (visual preview only). Console: T3B.Replay.Seek seconds; T3B.Replay.Pause 0|1; T3B.Replay.Probe"));
        }
    }
    catch (const std::exception& Error) { FailReplay(UTF8_TO_TCHAR(Error.what())); }
}

void AT3BReplayWorld::EndPlay(const EEndPlayReason::Type Reason) {
    if (State && State->OrderedMaterials) State->OrderedMaterials->Submit(nullptr, {});
    State.Reset();
    Super::EndPlay(Reason);
}

bool AT3BReplayWorld::LoadSourceBundle()
{
    FString Text;
    if (!FFileHelper::LoadFileToString(Text, *BundlePath(TEXT("manifest.json"))))
        throw T3BSource::FormatError("Content/SourceData/manifest.json is missing");
    TSharedPtr<FJsonObject> Manifest;
    const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
    if (!FJsonSerializer::Deserialize(Reader, Manifest) || !Manifest.IsValid())
        throw T3BSource::FormatError("Source bundle manifest is not valid JSON");
    if (JsonString(Manifest, TEXT("schema")) != TEXT("t3b-ue-source-bundle/v1"))
        throw T3BSource::FormatError("Unsupported source bundle manifest schema");
    State = TUniquePtr<FT3BReplayState, FT3BReplayStateDeleter>(new FT3BReplayState());
    const auto SceneDescription = JsonObject(Manifest, TEXT("scene"));
    State->Scene = T3BSource::LoadScene(ReadBundleBinary(JsonString(SceneDescription, TEXT("binary"))));
    State->SceneMaterials = LoadMaterials(JsonArray(SceneDescription, TEXT("materials")), TEXT("Street"));
    if (State->Scene.draws.size() != 140 || State->Scene.materials != 81 || State->SceneMaterials.Num() != 81)
        throw T3BSource::FormatError("Original street must contain140 draws and81 materials");
    TArray<FT3BGESection> SceneProfiles;
    for(const auto& Entry:JsonArray(SceneDescription,TEXT("materials")))
        SceneProfiles.Add(OrderedMaterial(ValueObject(Entry),1.f,ReplayAtlases));
    std::vector<bool> Solid;
    for(const auto& Entry:JsonArray(SceneDescription,TEXT("materials"))) {
        const auto M=ValueObject(Entry);
        Solid.push_back(M->GetNumberField(TEXT("blend"))==0 && M->GetNumberField(TEXT("depth_write"))!=0 &&
            PositiveAlphaTexture(JsonString(M,TEXT("texture"))));
    }
    State->Collision.Build(State->Scene,Solid);
    UE_LOG(LogT3BReplay,Display,TEXT("PC visible geometry collision: %llu solid triangles"),uint64(State->Collision.SolidTriangleCount()));
    for(const auto& Draw:State->Scene.draws){
        auto Section=SceneProfiles[Draw.material];Section.First=uint32(State->SceneVertices.Num());Section.Count=Draw.count;
        State->SceneSections.Add(Section);
        for(uint32 V=Draw.first;V<Draw.first+Draw.count;++V){
            const auto& Source=State->Scene.vertices[V];const auto P=UEPoint(Source.position);
            T3BGE::GPUVertex Out{};Out.position[0]=float(P.X);Out.position[1]=float(P.Y);Out.position[2]=float(P.Z);
            Out.uv[0]=Source.uv.u;Out.uv[1]=Source.uv.v;
            // Shared shader's x2 color contract; street modulation itself is x1.
            for(int32 C=0;C<3;++C)Out.color[C]=Source.rgba[C]/510.f;
            Out.color[3]=Source.rgba[3]/255.f;State->SceneVertices.Add(Out);
        }
    }
    for (const auto& Value : JsonArray(Manifest, TEXT("actors")))
    {
        const auto Description = ValueObject(Value);
        FReplayActorData Actor;
        Actor.Name = JsonString(Description, TEXT("name"));
        if (Actor.Name != TEXT("Aya") && Actor.Name != TEXT("Weapon") && Actor.Name != TEXT("Twisted"))
            throw T3BSource::FormatError("Unexpected actor identity in original replay bundle");
        for (const auto& Existing : State->Actors)
            if (Actor.Name == Existing.Name) throw T3BSource::FormatError("Duplicate original actor in bundle");
        if (JsonString(Description, TEXT("playback")) != TEXT("clamp"))
            throw T3BSource::FormatError("Only explicit clamp source playback is accepted");
        Actor.SynchronizationGroup = JsonString(Description, TEXT("synchronization_group"));
        const auto& Spawn = JsonArray(Description, TEXT("spawn"));
        if (Spawn.Num() != 3) throw T3BSource::FormatError("Actor spawn must contain PC x,z,yaw");
        for (int32 I = 0; I < 3; ++I)
        {
            double Number = 0;
            if (!Spawn[I]->TryGetNumber(Number) || !FMath::IsFinite(Number))
                throw T3BSource::FormatError("Nonfinite actor spawn");
            Actor.Spawn[I] = static_cast<float>(Number);
        }
        Actor.Skin = T3BSource::LoadSkin(ReadBundleBinary(JsonString(Description, TEXT("binary"))));
        if (Actor.Skin.flags & ~15u) throw T3BSource::FormatError("Actor source flags exceed the documented replay material contract");
        const auto& MaterialEntries = JsonArray(Description, TEXT("materials"));
        Actor.Materials = LoadMaterials(MaterialEntries, Actor.Name);
        {
            if (MaterialEntries.Num()!=1) throw T3BSource::FormatError("Ordered actor requires one verified atlas");
            const auto Profile=OrderedMaterial(ValueObject(MaterialEntries[0]),2.f,ReplayAtlases);
            Actor.Atlas=int32(Profile.Atlas);Actor.Cull=Profile.Cull;Actor.Blend=Profile.Blend;Actor.DepthWrite=Profile.DepthWrite;
        }
        const size_t ExpectedPackets = Actor.Name == TEXT("Aya") ? 106 : Actor.Name == TEXT("Weapon") ? 1 : 28;
        if (Actor.Skin.packets.size() != ExpectedPackets || Actor.Skin.materials != static_cast<uint32>(Actor.Materials.Num()))
            throw T3BSource::FormatError("Original actor packet/material identity mismatch");
        State->MaximumDuration = FMath::Max(State->MaximumDuration, static_cast<double>(Actor.Skin.time.back()));
        UE_LOG(LogT3BReplay, Display, TEXT("%s: %llu source samples; source flags=0x%x; capture group=%s; common preview clock, clamp at %.9g seconds"), *Actor.Name, static_cast<unsigned long long>(Actor.Skin.time.size()), Actor.Skin.flags, *Actor.SynchronizationGroup, Actor.Skin.time.back());
        State->Actors.push_back(MoveTemp(Actor));
    }
    if (State->Actors.size() != 3) throw T3BSource::FormatError("Replay requires original Aya, Weapon and Twisted");
    const FReplayActorData* Aya = nullptr;
    const FReplayActorData* Weapon = nullptr;
    for (const auto& Actor : State->Actors)
    {
        if (Actor.Name == TEXT("Aya")) Aya = &Actor;
        if (Actor.Name == TEXT("Weapon")) Weapon = &Actor;
    }
    if (!Aya || !Weapon || Aya->Skin.time != Weapon->Skin.time || Aya->Spawn != Weapon->Spawn ||
        Aya->Skin.units != Weapon->Skin.units || Aya->Skin.floor != Weapon->Skin.floor ||
        Aya->SynchronizationGroup != Weapon->SynchronizationGroup)
        throw T3BSource::FormatError("Aya and weapon must share verified source timing, spawn, scale, floor and capture group");

    if (Manifest->HasField(TEXT("action_clips")))
    {
        for (const auto& Value : JsonArray(Manifest, TEXT("action_clips")))
        {
            const auto Description = ValueObject(Value);
            FReplayActionClip Clip;
            Clip.Label = JsonString(Description, TEXT("label"));
            Clip.Pair = T3BAction::LoadSynchronizedPair(
                ReadBundleBinary(JsonString(Description, TEXT("body"))),
                ReadBundleBinary(JsonString(Description, TEXT("weapon"))));
            T3BAction::ValidateCompatible(Aya->Skin, Clip.Pair.body);
            T3BAction::ValidateCompatible(Weapon->Skin, Clip.Pair.weapon);
            if (Clip.Label == TEXT("reference"))
                throw T3BSource::FormatError("action_clips cannot redefine reference playback");
            for (const auto& Existing : State->ActionClips)
                if (Existing.Label == Clip.Label) throw T3BSource::FormatError("Duplicate action clip label");
            State->MaximumDuration = FMath::Max(State->MaximumDuration, static_cast<double>(Clip.Pair.body.time.back()));
            UE_LOG(LogT3BReplay, Display, TEXT("Action clip %s: Aya/weapon synchronized 60-sample pair; opt-in preview only"), *Clip.Label);
            State->ActionClips.push_back(MoveTemp(Clip));
        }
    }

    if (Manifest->HasField(TEXT("weapon_marker_source")))
    {
        const auto MarkerDescription = JsonObject(Manifest, TEXT("weapon_marker_source"));
        State->WeaponMarkers = T3BGE::LoadWeaponMarkers(ReadBundleBinary(JsonString(MarkerDescription, TEXT("file"))));
        State->HasWeaponMarkers = true;
        UE_LOG(LogT3BReplay, Display, TEXT("Loaded original T3BWMK1 weapon marker source indices 1/2; semantic gameplay socket name remains unresolved."));
    }
    if (ReplayAtlases.IsEmpty() || ReplayAtlases.Num()>256) throw T3BSource::FormatError("Original atlas set incomplete");
    State->OrderedMaterials = FSceneViewExtensions::NewExtension<FT3BGEViewExtension>(GetWorld());
    // Keep unsupported metadata visible. Submission order alone cannot promise
    // PSP blend/depth, fog, stencil or UE transparent sorting equivalence.
    UE_LOG(LogT3BReplay, Warning, TEXT("UE rendering acceptance pending: original triangle/section order and UV retained; UE winding, transparent sorting, PSP fog/stencil and blend/depth equivalence require actual editor verification."));
    UE_LOG(LogT3BReplay, Warning, TEXT("Actor vertex RGB reproduces legacy_C_face_shade from source-local posed triangle normals; flag2 halves RGB before material rgb_scale=2. This is C-adapter golden shading, not recovered GE lighting. Scene raw RGBA has no sRGB conversion."));
    if (Manifest->HasField(TEXT("unsupported_render_states")))
    {
        FString Raw;
        TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Raw);
        FJsonSerializer::Serialize(JsonArray(Manifest, TEXT("unsupported_render_states")), Writer);
        UE_LOG(LogT3BReplay, Warning, TEXT("Manifest unsupported_render_states (preserved): %s"), *Raw);
    }
    for (int32 I = 0; I < 1 + static_cast<int32>(State->Actors.size()); ++I)
    {
        auto* Mesh = NewObject<UProceduralMeshComponent>(this, *FString::Printf(TEXT("SourceMesh_%d"), I));
        Mesh->SetupAttachment(RootComponent);
        Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Mesh->SetCastShadow(false);
        Mesh->RegisterComponent();
        ReplayMeshes.Add(Mesh);
    }
    return true;
}

void AT3BReplayWorld::ApplyReplay(float Seconds, bool CreateSections, bool ExactSample)
{
    if (!State || ReplayMeshes.Num() != 4) throw T3BSource::FormatError("Replay mesh state incomplete");
    if (CreateSections)
    {
        for (size_t Section = 0; Section < State->Scene.draws.size(); ++Section)
        {
            const auto& Draw = State->Scene.draws[Section];
            TArray<FVector> Points; TArray<FVector2D> UV; TArray<FLinearColor> Colors;
            for (uint32 V = Draw.first; V < Draw.first + Draw.count; ++V)
            {
                const auto& Vertex = State->Scene.vertices[V];
                Points.Add(UEPoint(Vertex.position)); UV.Add(FVector2D(Vertex.uv.u, Vertex.uv.v));
                Colors.Add(FLinearColor(Vertex.rgba[0] / 255.0f, Vertex.rgba[1] / 255.0f, Vertex.rgba[2] / 255.0f, Vertex.rgba[3] / 255.0f));
            }
            SetSection(ReplayMeshes[0], static_cast<int32>(Section), Points, UV, Colors, true);
            ReplayMeshes[0]->SetMaterial(static_cast<int32>(Section), State->SceneMaterials[Draw.material]);
        }
    }
    TSharedPtr<FT3BGEWorldFrame, ESPMode::ThreadSafe> OrderedFrame = MakeShared<FT3BGEWorldFrame, ESPMode::ThreadSafe>();
    ReplayMeshes[0]->SetVisibility(!bOriginalMaterials);
    if(bOriginalMaterials){OrderedFrame->Vertices=State->SceneVertices;OrderedFrame->Sections=State->SceneSections;}
    for (size_t Index = 0; Index < State->Actors.size(); ++Index)
    {
        const auto& Actor = State->Actors[Index];
        const auto& Skin = PlaybackSkin(*State, Actor);
        const auto Phase = T3BAction::PlaybackPhase(Seconds, Skin.time.back(), bLoopPlayback && !ExactSample);
        const auto Posed = T3BAction::Pose(Skin, Phase);
        UProceduralMeshComponent* Mesh = ReplayMeshes[static_cast<int32>(Index) + 1];
        const bool Enemy=Actor.Name==TEXT("Twisted");
        if(Enemy)State->EnemyVertices.Reset();
        TArray<FVector> WeaponPoints;
        Mesh->SetVisibility(!(bOriginalMaterials && Actor.Atlas >= 0));
        for (size_t Section = 0; Section < Skin.packets.size(); ++Section)
        {
            const auto& Packet = Skin.packets[Section];
            TArray<FVector> Points; TArray<FVector2D> UV; TArray<FLinearColor> Colors;
            float FaceShade = 1.0f;
            for (uint32 V = Packet.first; V < Packet.first + Packet.count; ++V)
            {
                if ((V - Packet.first) % 3 == 0)
                {
                    const auto& A = Posed[V]; const auto& B = Posed[V + 1]; const auto& C = Posed[V + 2];
                    const FVector SourceNormal = FVector::CrossProduct(FVector(B.x - A.x, B.y - A.y, B.z - A.z), FVector(C.x - A.x, C.y - A.y, C.z - A.z)).GetSafeNormal();
                    FaceShade = 0.75f + 0.25f * FMath::Max(0.0f, static_cast<float>(SourceNormal.Y * 0.7 + SourceNormal.Z * 0.3));
                    if (Skin.flags & 2) FaceShade *= 0.5f;
                }
                const FVector Point=CombatPoint(*State,Actor,Skin,Posed[V]);
                Points.Add(Point);
                if(Enemy)State->EnemyVertices.Add(Point);
                if(Actor.Name==TEXT("Weapon"))WeaponPoints.Add(Point);
                UV.Add(FVector2D(Skin.vertices[V].uv.u, Skin.vertices[V].uv.v));
                const float Flash=Enemy?State->Hurt*.45f:0;
                Colors.Add(FLinearColor(FaceShade+Flash, FaceShade+Flash*.35f, FaceShade, 1.0f));
            }
            if (Actor.Atlas >= 0 && bOriginalMaterials) {
                OrderedFrame->Sections.Add({uint32(OrderedFrame->Vertices.Num()), Packet.count,
                    uint32(Actor.Atlas), Actor.Cull, Actor.Blend, Actor.DepthWrite});
                for (int32 V=0; V<Points.Num(); ++V) {
                    T3BGE::GPUVertex Out{};
                    Out.position[0]=float(Points[V].X); Out.position[1]=float(Points[V].Y); Out.position[2]=float(Points[V].Z);
                    Out.uv[0]=float(UV[V].X); Out.uv[1]=float(UV[V].Y);
                    Out.color[0]=Colors[V].R; Out.color[1]=Colors[V].G; Out.color[2]=Colors[V].B; Out.color[3]=Colors[V].A;
                    OrderedFrame->Vertices.Add(Out);
                }
            }
            SetSection(Mesh, static_cast<int32>(Section), Points, UV, Colors, CreateSections);
            if (CreateSections) Mesh->SetMaterial(static_cast<int32>(Section), Actor.Materials[Packet.material]);
        }
        if(WeaponPoints.Num()>121) {
            // Geometry-derived barrel sections, shared with the independent motion probe.
            // This is not an inferred original source1/2 named muzzle socket.
            State->Muzzle=WeaponPoints[114];
            State->Barrel=(WeaponPoints[114]-WeaponPoints[121]).GetSafeNormal();
            State->MuzzleValid=!State->Barrel.IsNearlyZero();
        }
    }
    TArray<FTextureResource*> Resources;
    for (UTexture2D* Texture : ReplayAtlases) Resources.Add(Texture->GetResource());
    State->OrderedMaterials->Submit(bOriginalMaterials ? OrderedFrame : nullptr, Resources);
}

void AT3BReplayWorld::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!bReplayReady) return;
    if(State->Combat && State->CombatDead)State->DeathSeconds+=DeltaSeconds;
    if (bReplayPaused && !State->Combat) return;
    // Preview loop only; it does not claim the original clips loop.
    if(!State->Combat || State->CombatFiring || State->CombatMoving)ReplaySeconds += static_cast<double>(DeltaSeconds);
    // Retain elapsed remainder; body/weapon evaluate the same phase, including the seam.
    try { ApplyReplay(static_cast<float>(ReplaySeconds), false); }
    catch (const std::exception& Error) { FailReplay(UTF8_TO_TCHAR(Error.what())); }
}

void AT3BReplayWorld::SetReplaySeconds(float Seconds)
{
    if (!bReplayReady || !FMath::IsFinite(Seconds)) return;
    ReplaySeconds = FMath::Clamp(static_cast<double>(Seconds), 0.0, State->MaximumDuration);
    try { ApplyReplay(static_cast<float>(ReplaySeconds), false, true); }
    catch (const std::exception& Error) { FailReplay(UTF8_TO_TCHAR(Error.what())); }
    UE_LOG(LogT3BReplay, Display, TEXT("Preview seconds=%.9g (per-clip clamped; capture groups remain distinct)"), ReplaySeconds);
}

void AT3BReplayWorld::SetReplayActionClip(const FString& Label)
{
    if (!bReplayReady || !State) return;
    const FString Requested = (Label == TEXT("reference") || Label.IsEmpty()) ? FString() : Label;
    if (!Requested.IsEmpty())
    {
        bool Found = false;
        for (const auto& Clip : State->ActionClips) if (Clip.Label == Requested) { Found = true; break; }
        if (!Found)
        {
            UE_LOG(LogT3BReplay, Error, TEXT("Unknown action clip '%s'; use T3B.Replay.ActionClip reference or a manifest label."), *Label);
            return;
        }
    }
    State->ActiveActionClip = Requested;
    ReplaySeconds = 0.0;
    try { ApplyReplay(static_cast<float>(ReplaySeconds), false); }
    catch (const std::exception& Error) { FailReplay(UTF8_TO_TCHAR(Error.what())); return; }
    UE_LOG(LogT3BReplay, Display, TEXT("Replay action clip=%s"), Requested.IsEmpty() ? TEXT("reference") : *Requested);
}

void AT3BReplayWorld::SetReplayPaused(bool Paused) { bReplayPaused = Paused; }
bool AT3BReplayWorld::IsCombatReady() const { return bReplayReady && State && State->Collision.SolidTriangleCount()>0; }
int32 AT3BReplayWorld::CombatSolidTriangles() const { return IsCombatReady()?int32(State->Collision.SolidTriangleCount()):0; }
bool AT3BReplayWorld::GetCombatSpawns(FVector& AyaFeet,FVector& EnemyFeet,float& AyaYaw,float& EnemyYaw) const {
    if(!IsCombatReady())return false;
    for(const auto& A:State->Actors) {
        if(A.Name==TEXT("Aya")){AyaFeet=UEPoint({A.Spawn[0],0,A.Spawn[1]});AyaYaw=-FMath::RadiansToDegrees(A.Spawn[2]);}
        if(A.Name==TEXT("Twisted")){EnemyFeet=UEPoint({A.Spawn[0],0,A.Spawn[1]});EnemyYaw=-FMath::RadiansToDegrees(A.Spawn[2]);}
    }
    for(FVector* P:{&AyaFeet,&EnemyFeet}) {
        auto PC=PCPoint(*P);float Y=PC.y;
        if(State->Collision.FindGround(PC,.3f,3.f,Y))P->Z=Y*100;
    }
    return true;
}
FVector AT3BReplayWorld::MoveCombatCapsule(const FVector& Feet,const FVector& Delta,float Radius,float Height,float StepHeight,bool& Blocked) const {
    Blocked=false;if(!IsCombatReady())return Feet;
    try {
        const auto R=State->Collision.MoveCapsule(PCPoint(Feet),PCPoint(Delta),Radius/100,Height/100,StepHeight/100);
        Blocked=R.wallBlocked||R.floorBlocked;return UEPoint(R.position);
    } catch(const T3BSource::FormatError&) {Blocked=true;return Feet;}
}
bool AT3BReplayWorld::TraceCombatScene(const FVector& Start,const FVector& End,FVector& Hit,float& Distance) const {
    Distance=float(FVector::Distance(Start,End));Hit=End;if(!IsCombatReady())return false;
    if(Start.ContainsNaN()||End.ContainsNaN()||Distance<.001f)return false;
    try {
        const auto R=State->Collision.Raycast(PCPoint(Start),PCPoint(End));
        if(!R.hit)return false;Hit=UEPoint(R.position);Distance=R.distance*100;return true;
    } catch(const T3BSource::FormatError&) {return false;}
}
bool AT3BReplayWorld::TraceCombatEnemy(const FVector& Start,const FVector& End,float& Distance) const {
    Distance=float(FVector::Distance(Start,End));if(!IsCombatReady()||State->CombatDead)return false;
    if(Start.ContainsNaN()||End.ContainsNaN()||Distance<.001f||!FMath::IsFinite(Distance))return false;
    const FVector Dir=(End-Start).GetSafeNormal();bool Hit=false;
    for(int32 I=0;I+2<State->EnemyVertices.Num();I+=3) {
        const FVector A=State->EnemyVertices[I],E1=State->EnemyVertices[I+1]-A,E2=State->EnemyVertices[I+2]-A;
        const FVector P=FVector::CrossProduct(Dir,E2);const double Det=FVector::DotProduct(E1,P);
        if(FMath::Abs(Det)<1.e-10)continue;
        const FVector T=Start-A;const double U=FVector::DotProduct(T,P)/Det;if(U<0||U>1)continue;
        const FVector Q=FVector::CrossProduct(T,E1);const double V=FVector::DotProduct(Dir,Q)/Det;if(V<0||U+V>1)continue;
        const double D=FVector::DotProduct(E2,Q)/Det;
        if(D>.01&&D<Distance){Distance=float(D);Hit=true;}
    }
    return Hit;
}
bool AT3BReplayWorld::GetCombatMuzzle(FVector& Origin,FVector& Direction) const {
    if(!IsCombatReady()||!State->MuzzleValid)return false;
    Direction=State->Barrel;Origin=State->Muzzle+Direction*2;return true;
}
void AT3BReplayWorld::SetCombatActors(const FVector& AyaFeet,float AyaYaw,const FVector& EnemyFeet,float EnemyYaw,float HitFraction,bool Dead) {
    if(!IsCombatReady()||AyaFeet.ContainsNaN()||EnemyFeet.ContainsNaN()||!FMath::IsFinite(AyaYaw)||!FMath::IsFinite(EnemyYaw))return;
    State->Combat=true;State->AyaFeet=AyaFeet;State->AyaYaw=AyaYaw;State->EnemyFeet=EnemyFeet;State->EnemyYaw=EnemyYaw;
    State->Hurt=FMath::Clamp(HitFraction,0.f,1.f);
    if(!Dead)State->DeathSeconds=0;
    State->CombatDead=Dead;
    try {ApplyReplay(float(ReplaySeconds),false);} catch(const std::exception& E){FailReplay(UTF8_TO_TCHAR(E.what()));}
}
void AT3BReplayWorld::SetCombatAnimation(bool Firing,bool Moving) {
    if(!IsCombatReady())return;
    const FString Desired=Moving?TEXT("approach_fire"):TEXT("");
    if(Desired!=State->ActiveActionClip)SetReplayActionClip(Desired);
    State->CombatFiring=Firing;State->CombatMoving=Moving;
}
void AT3BReplayWorld::StartFire() { SetFiring(true); }
void AT3BReplayWorld::StopFire() { SetFiring(false); }
void AT3BReplayWorld::SetFiring(bool Firing) {
    if (!bReplayReady) return;
    bReplayPaused = !Firing;
    bLoopPlayback = true;
    if (Firing) ReplaySeconds = 0.0;
    UE_LOG(LogT3BReplay, Display, TEXT("Continuous-fire preview=%d; shared Aya/weapon source clock +120ms seam adapter"), Firing);
}
void AT3BReplayWorld::SetOriginalMaterials(bool Enabled) {
    bOriginalMaterials = Enabled;
    if (bReplayReady) ApplyReplay(static_cast<float>(ReplaySeconds), false, bReplayPaused);
}

bool AT3BReplayWorld::WriteSourceProbe()
{
    if (!bReplayReady || !State) return false;
    if(State->Combat) { UE_LOG(LogT3BReplay,Warning,TEXT("Use -T3BReplayOnly for immutable source geometry probes."));return false; }
    const FString Directory = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("SourceReplay"));
    IFileManager::Get().MakeDirectory(*Directory, true);
    const TSharedPtr<FJsonObject> Metadata = MakeShared<FJsonObject>();
    Metadata->SetStringField(TEXT("schema"), TEXT("t3b-ue-procedural-probe/v1"));
    Metadata->SetStringField(TEXT("run_id"), FGuid::NewGuid().ToString());
    Metadata->SetStringField(TEXT("engine_version"), FEngineVersion::Current().ToString());
    Metadata->SetStringField(TEXT("scope"), TEXT("actual_procedural_component_CPU_world_positions"));
    Metadata->SetBoolField(TEXT("gpu_pixels_verified"), false);
    Metadata->SetStringField(TEXT("action_clip"), State->ActiveActionClip.IsEmpty() ? TEXT("reference") : State->ActiveActionClip);
    Metadata->SetBoolField(TEXT("ordered_actor_materials"), bOriginalMaterials);
    Metadata->SetStringField(TEXT("probe_sampling"), TEXT("exact_stored_samples_no_preview_seam"));
    const auto SaveMetadata = [&Directory, &Metadata](bool Complete)
    {
        Metadata->SetBoolField(TEXT("all_csv_written"), Complete);
        FString Text;
        const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Text);
        if (!FJsonSerializer::Serialize(Metadata.ToSharedRef(), Writer)) return false;
        return FFileHelper::SaveStringToFile(Text, *FPaths::Combine(Directory, TEXT("probe_metadata.json")), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
    };
    Metadata->SetBoolField(TEXT("weapon_marker_source_loaded"), State->HasWeaponMarkers);
    Metadata->SetBoolField(TEXT("weapon_marker_semantic_socket_name_inferred"), false);
    // Invalidate a previous successful marker before writing a new set of CSVs.
    if (!SaveMetadata(false)) return false;
    const auto Save = [&Directory](const FString& Name, const FString& Text)
    {
        const FString Path = FPaths::Combine(Directory, Name + TEXT("_world.csv"));
        const bool OK = FFileHelper::SaveStringToFile(Text, *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
        UE_LOG(LogT3BReplay, Display, TEXT("Source probe %s: %s"), OK ? TEXT("written") : TEXT("FAILED"), *Path);
        return OK;
    };
    const FString Header = TEXT("sample,time,index,source_x,source_y,source_z,pc_x,pc_y,pc_z,ue_x,ue_y,ue_z,world_x,world_y,world_z\n");
    UE_LOG(LogT3BReplay, Display, TEXT("Probe ue_xyz are source-to-UE expectations; world_xyz read back the procedural component CPU vertex buffer and component world transform. This is not GPU pixel verification."));
    FString SceneCSV = Header;
    size_t SceneSection = 0;
    for (size_t I = 0; I < State->Scene.vertices.size(); ++I)
    {
        const auto P = State->Scene.vertices[I].position; const FVector U = UEPoint(P);
        while (I >= State->Scene.draws[SceneSection].first + State->Scene.draws[SceneSection].count) ++SceneSection;
        FProcMeshSection* Buffer = ReplayMeshes[0]->GetProcMeshSection(static_cast<int32>(SceneSection));
        const int32 Local = static_cast<int32>(I - State->Scene.draws[SceneSection].first);
        if (!Buffer || !Buffer->ProcVertexBuffer.IsValidIndex(Local))
        {
            FailReplay(TEXT("Actual street procedural mesh probe buffer is incomplete"));
            return false;
        }
        const FVector W = ReplayMeshes[0]->GetComponentTransform().TransformPosition(FVector(Buffer->ProcVertexBuffer[Local].Position));
        SceneCSV += FString::Printf(TEXT("0,0,%llu,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g\n"),
            static_cast<unsigned long long>(I), P.x, P.y, P.z, P.x, P.y, P.z, U.X, U.Y, U.Z, W.X, W.Y, W.Z);
    }
    bool OK = Save(TEXT("Street"), SceneCSV);
    if (State->HasWeaponMarkers)
    {
        const auto Numbers = [](const auto& Values)
        {
            TArray<TSharedPtr<FJsonValue>> Result;
            for (const auto Value : Values) Result.Add(MakeShared<FJsonValueNumber>(static_cast<double>(Value)));
            return Result;
        };
        const TSharedPtr<FJsonObject> Marker = MakeShared<FJsonObject>();
        Marker->SetStringField(TEXT("schema"), TEXT("t3b-runtime-weapon-markers/v1"));
        Marker->SetStringField(TEXT("format"), TEXT("T3BWMK1"));
        Marker->SetBoolField(TEXT("semantic_names_inferred"), false);
        Marker->SetNumberField(TEXT("original_vertex_weight"), State->WeaponMarkers.originalVertexWeight);
        Marker->SetArrayField(TEXT("source_indices"), {MakeShared<FJsonValueNumber>(1.0), MakeShared<FJsonValueNumber>(2.0)});
        Marker->SetArrayField(TEXT("expected_ge_root_3x4"), Numbers(State->WeaponMarkers.expectedGEroot));
        TArray<TSharedPtr<FJsonValue>> Locals;
        for (const auto& Matrix : State->WeaponMarkers.originalLocalMatrices)
            Locals.Add(MakeShared<FJsonValueArray>(Numbers(Matrix)));
        Marker->SetArrayField(TEXT("original_local_matrices"), Locals);
        FString MarkerText;
        const TSharedRef<TJsonWriter<>> MarkerWriter = TJsonWriterFactory<>::Create(&MarkerText);
        OK = FJsonSerializer::Serialize(Marker.ToSharedRef(), MarkerWriter) &&
             FFileHelper::SaveStringToFile(MarkerText, *FPaths::Combine(Directory, TEXT("weapon_markers.json")), FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM) && OK;
        UE_LOG(LogT3BReplay, Display, TEXT("Source probe weapon markers: %s"), OK ? TEXT("written") : TEXT("FAILED"));
    }
    try
    {
        for (size_t A = 0; A < State->Actors.size(); ++A)
        {
            const auto& Actor = State->Actors[A]; const auto& Skin = PlaybackSkin(*State, Actor); FString CSV = Header;
            for (size_t Sample = 0; Sample < Skin.time.size(); ++Sample)
            {
                ApplyReplay(Skin.time[Sample], false, true);
                const auto Posed = T3BSource::PoseOriginal(Skin, Skin.time[Sample]);
                size_t Section = 0;
                for (size_t I = 0; I < Posed.size(); ++I)
                {
                    const auto S = Posed[I]; const auto P = T3BSource::ToPC(Skin, S, Actor.Spawn[0], Actor.Spawn[1], Actor.Spawn[2]);
                    while (I >= Skin.packets[Section].first + Skin.packets[Section].count) ++Section;
                    UProceduralMeshComponent* Mesh = ReplayMeshes[static_cast<int32>(A) + 1];
                    FProcMeshSection* Buffer = Mesh->GetProcMeshSection(static_cast<int32>(Section));
                    const int32 Local = static_cast<int32>(I - Skin.packets[Section].first);
                    if (!Buffer || !Buffer->ProcVertexBuffer.IsValidIndex(Local)) throw T3BSource::FormatError("Actual procedural mesh probe buffer is incomplete");
                    const FVector U = UEPoint(P); const FVector W = Mesh->GetComponentTransform().TransformPosition(FVector(Buffer->ProcVertexBuffer[Local].Position));
                    CSV += FString::Printf(TEXT("%llu,%.9g,%llu,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g\n"),
                        static_cast<unsigned long long>(Sample), Skin.time[Sample], static_cast<unsigned long long>(I),
                        S.x, S.y, S.z, P.x, P.y, P.z, U.X, U.Y, U.Z, W.X, W.Y, W.Z);
                }
            }
            OK = Save(Actor.Name, CSV) && OK;
            UE_LOG(LogT3BReplay, Display, TEXT("Probe %s capture group=%s (independent groups are not asserted same original game frame)"), *Actor.Name, *Actor.SynchronizationGroup);
        }
        ApplyReplay(static_cast<float>(ReplaySeconds), false);
    }
    catch (const std::exception& Error) { FailReplay(FString::Printf(TEXT("Actual component probe failed: %s"), UTF8_TO_TCHAR(Error.what()))); return false; }
    return SaveMetadata(OK) && OK;
}

bool AT3BReplayWorld::WriteMotionProbe() {
    if (!bReplayReady || !State) return false;
    if(State->Combat) { UE_LOG(LogT3BReplay,Warning,TEXT("Use -T3BReplayOnly for immutable motion probes."));return false; }
    const FString ProbeDirectory=FPaths::Combine(FPaths::ProjectSavedDir(),TEXT("SourceReplay"));
    IFileManager::Get().MakeDirectory(*ProbeDirectory,true);
    if(!FFileHelper::SaveStringToFile(TEXT("{\"all_csv_written\":false}"),
        *FPaths::Combine(ProbeDirectory,TEXT("continuous_fire.json")),FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))return false;
    try {
        size_t Body=0, Weapon=0;
        for (size_t i=0; i<State->Actors.size(); ++i) {
            if (State->Actors[i].Name==TEXT("Aya")) Body=i;
            if (State->Actors[i].Name==TEXT("Weapon")) Weapon=i;
        }
        const auto& A=State->Actors[Body]; const auto& W=State->Actors[Weapon];
        const auto& BodySkin=PlaybackSkin(*State,A); const auto& GunSkin=PlaybackSkin(*State,W);
        const auto AtZero=T3BSource::PoseOriginal(BodySkin,0), GunZero=T3BSource::PoseOriginal(GunSkin,0);
        uint32 BodyContact=0, GunContact=0; double Closest=MAX_dbl;
        // Mesh-surface vertex contact candidate, not an invented named skeleton socket.
        for (uint32 i=0;i<AtZero.size();++i) for(uint32 j=0;j<GunZero.size();++j) {
            const auto& a=AtZero[i]; const auto& b=GunZero[j];
            const double D=FMath::Square(a.x-b.x)+FMath::Square(a.y-b.y)+FMath::Square(a.z-b.z);
            if(D<Closest){Closest=D;BodyContact=i;GunContact=j;}
        }
        uint32 Tip=0, Base=0;
        for(uint32 i=1;i<GunSkin.vertices.size();++i)
            if(GunSkin.vertices[i].position.x<GunSkin.vertices[Tip].position.x)Tip=i;
        const auto P=GunSkin.vertices[Tip].position; float Nearest=MAX_flt;
        for(uint32 i=0;i<GunSkin.vertices.size();++i){const auto Q=GunSkin.vertices[i].position;
            if(Q.y==P.y && Q.z==P.z && Q.x>P.x && Q.x<Nearest){Nearest=Q.x;Base=i;}}
        if(Nearest==MAX_flt)throw T3BSource::FormatError("No matching original barrel cross-section");
        const auto Actual=[&](size_t ActorIndex,uint32 Vertex){
            const auto& Skin=PlaybackSkin(*State,State->Actors[ActorIndex]);
            for(size_t i=0;i<Skin.packets.size();++i){const auto& Packet=Skin.packets[i];
                if(Vertex>=Packet.first && Vertex<Packet.first+Packet.count){
                    const auto* Buffer=ReplayMeshes[int32(ActorIndex)+1]->GetProcMeshSection(int32(i));
                    if(!Buffer || Vertex-Packet.first>=uint32(Buffer->ProcVertexBuffer.Num()))break;
                    return ReplayMeshes[int32(ActorIndex)+1]->GetComponentTransform().TransformPosition(
                        FVector(Buffer->ProcVertexBuffer[int32(Vertex-Packet.first)].Position));
                }
            }
            throw T3BSource::FormatError("Motion probe mesh vertex unavailable");
        };
        FString CSV=TEXT("sample,elapsed,source_time,next_time,seam_alpha,body_x,body_y,body_z,grip_x,grip_y,grip_z,tip_x,tip_y,tip_z,base_x,base_y,base_z\n");
        for(uint32 Step=0;Step<=360;++Step){
            const float Elapsed=float(Step)/30.f;
            ApplyReplay(Elapsed,false);
            const auto Phase=T3BAction::PlaybackPhase(Elapsed,BodySkin.time.back(),bLoopPlayback);
            const FVector B=Actual(Body,BodyContact),G=Actual(Weapon,GunContact),T=Actual(Weapon,Tip),R=Actual(Weapon,Base);
            CSV+=FString::Printf(TEXT("%u,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g\n"),
                Step,Elapsed,Phase.first,Phase.second,Phase.blend,B.X,B.Y,B.Z,G.X,G.Y,G.Z,T.X,T.Y,T.Z,R.X,R.Y,R.Z);
        }
        ApplyReplay(static_cast<float>(ReplaySeconds),false,bReplayPaused);
        const FString Directory=FPaths::Combine(FPaths::ProjectSavedDir(),TEXT("SourceReplay"));
        IFileManager::Get().MakeDirectory(*Directory,true);
        const bool Written=FFileHelper::SaveStringToFile(CSV,*FPaths::Combine(Directory,TEXT("continuous_fire.csv")),FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
        const TSharedPtr<FJsonObject> Metadata=MakeShared<FJsonObject>();
        Metadata->SetStringField(TEXT("schema"),TEXT("t3b-ue-continuous-fire/v1"));
        Metadata->SetStringField(TEXT("action_clip"),State->ActiveActionClip.IsEmpty()?TEXT("reference"):State->ActiveActionClip);
        Metadata->SetNumberField(TEXT("body_contact_vertex"),BodyContact);Metadata->SetNumberField(TEXT("weapon_contact_vertex"),GunContact);
        Metadata->SetNumberField(TEXT("barrel_tip_vertex"),Tip);Metadata->SetNumberField(TEXT("barrel_base_vertex"),Base);
        Metadata->SetNumberField(TEXT("samples"),361);Metadata->SetNumberField(TEXT("seam_seconds"),0.12f);
        Metadata->SetBoolField(TEXT("named_original_socket_recovered"),false);
        Metadata->SetBoolField(TEXT("actual_component_CPU_readback"),true);
        Metadata->SetBoolField(TEXT("all_csv_written"),Written);
        FString Text;const auto Writer=TJsonWriterFactory<>::Create(&Text);FJsonSerializer::Serialize(Metadata.ToSharedRef(),Writer);
        const bool OK=FFileHelper::SaveStringToFile(Text,*FPaths::Combine(Directory,TEXT("continuous_fire.json")),FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM)&&Written;
        UE_LOG(LogT3BReplay,Display,TEXT("Continuous fire probe=%d;361 shared-clock samples; contact vertices %u/%u; no named socket claim"),OK,BodyContact,GunContact);
        return OK;
    }catch(const std::exception& Error){FailReplay(UTF8_TO_TCHAR(Error.what()));return false;}
}

namespace
{
AT3BReplayWorld* FindReplay(UWorld* World)
{
    if (World) for (TActorIterator<AT3BReplayWorld> It(World); It; ++It) return *It;
    UE_LOG(LogT3BReplay, Error, TEXT("No T3BReplayWorld in the active world; start the replay map in PIE/game first."));
    return nullptr;
}
FAutoConsoleCommandWithWorldAndArgs MaterialsCommand(TEXT("T3B.Replay.OriginalMaterials"), TEXT("Ordered source scene/actors blend+main-depth: 1 enabled, 0 legacy UE translucent A/B."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args,UWorld* World){
        if(Args.Num()!=1 || (Args[0]!=TEXT("0") && Args[0]!=TEXT("1")))return;
        if(auto* Replay=FindReplay(World))Replay->SetOriginalMaterials(Args[0]==TEXT("1"));
    }));
FAutoConsoleCommandWithWorldAndArgs FireCommand(TEXT("T3B.Replay.Fire"), TEXT("Continuous paired source animation: 1 play, 0 hold (also left mouse)."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args,UWorld* World){
        if(Args.Num()!=1 || (Args[0]!=TEXT("0") && Args[0]!=TEXT("1")))return;
        if(auto* Replay=FindReplay(World))Replay->SetFiring(Args[0]==TEXT("1"));
    }));
FAutoConsoleCommandWithWorldAndArgs MotionCommand(TEXT("T3B.Replay.MotionProbe"),TEXT("Record actual component contact/barrel candidates over multiple fire loops."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&,UWorld* World){if(auto* Replay=FindReplay(World))Replay->WriteMotionProbe();}));
FAutoConsoleCommandWithWorldAndArgs SeekCommand(TEXT("T3B.Replay.Seek"), TEXT("Seek original source replay to seconds; clamps each clip."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
    {
        float Seconds;
        if (Args.Num() != 1 || !LexTryParseString(Seconds, *Args[0])) { UE_LOG(LogT3BReplay, Error, TEXT("Usage: T3B.Replay.Seek seconds")); return; }
        if (auto* Replay = FindReplay(World)) Replay->SetReplaySeconds(Seconds);
    }));
FAutoConsoleCommandWithWorldAndArgs PauseCommand(TEXT("T3B.Replay.Pause"), TEXT("Pause source preview: 1 pause, 0 resume."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
    {
        if (Args.Num() != 1 || (Args[0] != TEXT("0") && Args[0] != TEXT("1"))) { UE_LOG(LogT3BReplay, Error, TEXT("Usage: T3B.Replay.Pause 0|1")); return; }
        if (auto* Replay = FindReplay(World)) Replay->SetReplayPaused(Args[0] == TEXT("1"));
    }));
FAutoConsoleCommandWithWorldAndArgs ActionClipCommand(TEXT("T3B.Replay.ActionClip"), TEXT("Select staged synchronized Aya/weapon action clip, or reference."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
    {
        if (Args.Num() != 1) { UE_LOG(LogT3BReplay, Error, TEXT("Usage: T3B.Replay.ActionClip reference|<label>")); return; }
        if (auto* Replay = FindReplay(World)) Replay->SetReplayActionClip(Args[0]);
    }));
FAutoConsoleCommandWithWorldAndArgs ProbeCommand(TEXT("T3B.Replay.Probe"), TEXT("Write ALL stored source samples transformed to UE/world CSV in Saved/SourceReplay."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
    {
        if (auto* Replay = FindReplay(World)) Replay->WriteSourceProbe();
    }));
}
