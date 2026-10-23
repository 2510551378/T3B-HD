#include "Modules/ModuleManager.h"
#include "Misc/Paths.h"
#include "ShaderCore.h"
#include "HAL/PlatformProperties.h"

class FT3BRemakeModule final : public FDefaultGameModuleImpl {
public:
    virtual void StartupModule() override {
        FDefaultGameModuleImpl::StartupModule();
        if (!FPlatformProperties::RequiresCookedData() && !AllShaderSourceDirectoryMappings().Contains(TEXT("/T3B")))
            AddShaderSourceDirectoryMapping(TEXT("/T3B"), FPaths::Combine(FPaths::ProjectDir(), TEXT("Shaders")));
    }
};
IMPLEMENT_PRIMARY_GAME_MODULE(FT3BRemakeModule, T3BRemake, "T3BRemake");
