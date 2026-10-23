#include "T3BGEReplayActor.h"
#include "T3BGEGeometry.h"
#include "T3BGEViewExtension.h"
#include "Components/SceneComponent.h"
#include "Engine/Texture2D.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include <exception>
#include <stdexcept>

DEFINE_LOG_CATEGORY_STATIC(LogT3BGEPass, Log, All);
struct FT3BGEReplayActorState {
    T3BGE::GPUGeometry Geometry;
    TSharedPtr<FT3BGEViewExtension, ESPMode::ThreadSafe> Extension;
    TSharedPtr<const FT3BGEWorldFrame, ESPMode::ThreadSafe> LastSubmittedFrame;
};
void FT3BGEReplayActorStateDeleter::operator()(FT3BGEReplayActorState* Ptr) const { delete Ptr; }
AT3BGEReplayActor::AT3BGEReplayActor() {
    PrimaryActorTick.bCanEverTick = true;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("OriginalGERoot"));
}
AT3BGEReplayActor::~AT3BGEReplayActor() = default;
void AT3BGEReplayActor::BeginPlay() {
    Super::BeginPlay();
    if (!BundleFile.IsEmpty()) LoadOriginalGEBundle(BundleFile);
}
void AT3BGEReplayActor::ClearRenderFrame() {
    if (State) State->LastSubmittedFrame.Reset();
    if (State && State->Extension) State->Extension->Submit(nullptr, {});
}
void AT3BGEReplayActor::EndPlay(const EEndPlayReason::Type Reason) {
    ClearRenderFrame(); State.Reset(); Atlases.Reset(); bSourceReady = false;
    Super::EndPlay(Reason);
}
bool AT3BGEReplayActor::LoadOriginalGEBundle(const FString& Path) {
    ClearRenderFrame(); State.Reset(); Atlases.Reset(); bSourceReady = false; CapturedSampleCount = 0;
    try {
        TArray<uint8> Bytes;
        const FString FullPath = FPaths::ConvertRelativePathToFull(Path);
        if (!FFileHelper::LoadFileToArray(Bytes, *FullPath)) throw std::runtime_error("GE bundle unreadable");
        auto Next = TUniquePtr<FT3BGEReplayActorState, FT3BGEReplayActorStateDeleter>(new FT3BGEReplayActorState());
        Next->Geometry = T3BGE::LoadGPUGeometry(std::vector<std::uint8_t>(Bytes.GetData(), Bytes.GetData() + Bytes.Num()));
        for (const auto& Source : Next->Geometry.atlases) {
            UTexture2D* Texture = UTexture2D::CreateTransient(Source.width, Source.height, PF_R8G8B8A8, NAME_None,
                TConstArrayView64<uint8>(Source.rgba.data(), int64(Source.rgba.size())));
            if (!Texture) throw std::runtime_error("Original RGBA atlas creation failed");
            Atlases.Add(Texture);
            Texture->SRGB = false; Texture->NeverStream = true; Texture->Filter = TF_Bilinear;
            Texture->AddressX = Texture->AddressY = TA_Wrap; Texture->UpdateResource();
        }
        Next->Extension = FSceneViewExtensions::NewExtension<FT3BGEViewExtension>(GetWorld());
        CapturedSampleCount = int32(Next->Geometry.frames.size()); State = MoveTemp(Next);
        CapturedSample = 0; PreviewSamplePosition = 0.; bSourceReady = true; PublishSample();
        UE_LOG(LogT3BGEPass, Display, TEXT("Loaded %d captured GE samples. Preview clock only; original timing/PSP pixels and M1 remain unverified."), CapturedSampleCount);
        return true;
    } catch (const std::exception& Error) {
        ClearRenderFrame(); State.Reset(); Atlases.Reset(); bSourceReady = false; CapturedSampleCount = 0;
        UE_LOG(LogT3BGEPass, Error, TEXT("Original GE pass failed: %s; no placeholder rendered."), UTF8_TO_TCHAR(Error.what()));
        return false;
    }
}
void AT3BGEReplayActor::SetCapturedSample(int32 Sample) {
    if (!bSourceReady) return;
    CapturedSample = FMath::Clamp(Sample, 0, CapturedSampleCount - 1);
    PreviewSamplePosition = CapturedSample; PublishSample();
}
void AT3BGEReplayActor::Tick(float DeltaSeconds) {
    Super::Tick(DeltaSeconds);
    if (!bSourceReady) return;
    if (bPlayPreview && FMath::IsFinite(PreviewSamplesPerSecond) && PreviewSamplesPerSecond > 0.f) {
        PreviewSamplePosition = FMath::Min(PreviewSamplePosition + DeltaSeconds * PreviewSamplesPerSecond, double(CapturedSampleCount - 1));
        CapturedSample = int32(PreviewSamplePosition);
    }
    PublishSample();
}
void AT3BGEReplayActor::PublishSample() {
    if (!bSourceReady || !State || !State->Extension) return;
    if (!bEnableGEPass || IsHidden()) { ClearRenderFrame(); return; }
    const FTransform World = GetActorTransform();
    if (World.ContainsNaN() || !World.GetScale3D().Equals(FVector::OneVector, 1.e-6)) {
        ClearRenderFrame(); return; // No unverified negative-scale/culling policy.
    }
    auto Frame = MakeShared<FT3BGEWorldFrame, ESPMode::ThreadSafe>();
    Frame->SourceSample = CapturedSample;
    const auto& Source = State->Geometry.frames[CapturedSample];
    for (const auto& Draw : Source.draws) {
        Frame->Sections.Add({uint32(Frame->Vertices.Num()), uint32(Draw.vertices.size()), Draw.texture});
        for (const auto& V : Draw.vertices) {
            auto Out = V;
            const FVector P = World.TransformPosition(FVector(V.position[0], V.position[1], V.position[2]));
            Out.position[0] = float(P.X); Out.position[1] = float(P.Y); Out.position[2] = float(P.Z);
            if (!FMath::IsFinite(Out.position[0]) || !FMath::IsFinite(Out.position[1]) || !FMath::IsFinite(Out.position[2])) {
                ClearRenderFrame(); return;
            }
            Frame->Vertices.Add(Out);
        }
    }
    TArray<FTextureResource*> Resources;
    for (UTexture2D* Texture : Atlases) Resources.Add(Texture->GetResource());
    State->LastSubmittedFrame = Frame;
    State->Extension->Submit(Frame, Resources);
}
bool AT3BGEReplayActor::WriteSubmittedFrame(const FString& Path) const {
    if (!State || !State->LastSubmittedFrame || IFileManager::Get().FileExists(*Path)) return false;
    const auto& Frame = *State->LastSubmittedFrame;
    TArray<uint8> Bytes;
    const auto Append = [&Bytes](const void* Data, int32 Size) { Bytes.Append(static_cast<const uint8*>(Data), Size); };
    Append("T3BSUB1\0", 8);
    const uint32 Header[] = {Frame.SourceSample, uint32(Frame.Sections.Num()), uint32(Frame.Vertices.Num())};
    Append(Header, sizeof(Header));
    for (const auto& Section : Frame.Sections) {
        const uint32 Row[] = {Section.First, Section.Count, Section.Atlas}; Append(Row, sizeof(Row));
    }
    Append(Frame.Vertices.GetData(), Frame.Vertices.Num() * sizeof(T3BGE::GPUVertex));
    return FFileHelper::SaveArrayToFile(Bytes, *Path);
}
