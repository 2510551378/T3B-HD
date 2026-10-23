using UnrealBuildTool;
using System.Collections.Generic;

public class T3BRemakeEditorTarget : TargetRules
{
    public T3BRemakeEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("T3BRemake");
    }
}
