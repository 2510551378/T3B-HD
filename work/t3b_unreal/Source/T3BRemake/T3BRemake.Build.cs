using UnrealBuildTool;
using System.IO;

public class T3BRemake : ModuleRules
{
    public T3BRemake(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        CppStandard = CppStandardVersion.Cpp20;
        bEnableExceptions = true; // Engine-independent binary readers reject invalid source data.
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "ProceduralMeshComponent" });
        PrivateDependencyModuleNames.AddRange(new[] { "InputCore", "Json", "JsonUtilities", "RenderCore", "RHI", "Renderer", "ImageWrapper", "ImageCore" });
        // UE5.8-specific view callback exposes FViewInfo/PostProcess inputs here.
        PrivateIncludePaths.Add(Path.Combine(EngineDirectory, "Source/Runtime/Renderer/Private"));
        PrivateIncludePaths.Add(Path.Combine(EngineDirectory, "Source/Runtime/Renderer/Internal"));
    }
}
