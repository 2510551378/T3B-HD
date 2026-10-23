using UnrealBuildTool;
using System.Collections.Generic;

public class T3BRemakeTarget : TargetRules
{
    public T3BRemakeTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.Latest;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("T3BRemake");
    }
}
