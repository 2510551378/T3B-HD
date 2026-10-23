[CmdletBinding()]
param(
    [string]$EngineRoot='C:\Program Files\Epic Games\UE_5.8',
    [string]$ReportPath
)
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
# Read-only inventory: no installation, process control or editor launch.
$engineDirectory=[System.IO.Path]::GetFullPath($EngineRoot)
$required=@('Engine\Build\Build.version','Engine\Build\BatchFiles\Build.bat',
    'Engine\Binaries\Win64\UnrealEditor-Cmd.exe','Engine\Binaries\Win64\UnrealEditor.exe')
$fileChecks=@($required | ForEach-Object {
    $candidate=Join-Path $engineDirectory $_
    [ordered]@{path=$candidate; exists=(Test-Path -LiteralPath $candidate -PathType Leaf)}
})
$engineVersion=$null
$versionPath=Join-Path $engineDirectory $required[0]
if(Test-Path -LiteralPath $versionPath -PathType Leaf){
    $engineVersion=Get-Content -LiteralPath $versionPath -Encoding UTF8 -Raw | ConvertFrom-Json
}
$launcherFile=Join-Path $env:ProgramData 'Epic\UnrealEngineLauncher\LauncherInstalled.dat'
$launcherEntries=@()
if(Test-Path -LiteralPath $launcherFile -PathType Leaf){
    $launcherData=Get-Content -LiteralPath $launcherFile -Encoding UTF8 -Raw | ConvertFrom-Json
    $launcherEntries=@($launcherData.InstallationList | Where-Object {$_.InstallLocation -ieq $engineDirectory})
}
# Current Launcher builds also register engines through per-app .item files.
# Bridge/Fab plugins can share the install directory; require the engine app ID.
$modernLauncherEntries=@()
$manifestDirectory=Join-Path $env:ProgramData 'Epic\EpicGamesLauncher\Data\Manifests'
if(Test-Path -LiteralPath $manifestDirectory -PathType Container){
    foreach($manifestFile in Get-ChildItem -LiteralPath $manifestDirectory -Filter '*.item' -File){
        try{$manifest=Get-Content -LiteralPath $manifestFile.FullName -Encoding UTF8 -Raw | ConvertFrom-Json}
        catch{continue}
        if($manifest.AppName -eq 'UE_5.8' -and $manifest.InstallLocation -ieq $engineDirectory){
            $modernLauncherEntries += [ordered]@{source_file=$manifestFile.FullName;
                app_name=$manifest.AppName;app_version=$manifest.AppVersionString;
                install_location=$manifest.InstallLocation;incomplete=$manifest.bIsIncompleteInstall}
        }
    }
}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$vsInstances=@()
$discovery='vswhere unavailable; compiler discovery incomplete'
if(Test-Path -LiteralPath $vswhere -PathType Leaf){
    $raw=& $vswhere -all -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -format json -utf8
    if($LASTEXITCODE -ne 0){throw "vswhere failed: $LASTEXITCODE"}
    $vsInstances=@(($raw -join "`n") | ConvertFrom-Json)
    $discovery='vswhere queried all products for VC.Tools.x86.x64'
}
$compilers=@()
foreach($instance in $vsInstances){
    $toolsDirectory=Join-Path $instance.installationPath 'VC\Tools\MSVC'
    if(Test-Path -LiteralPath $toolsDirectory -PathType Container){
        foreach($tool in Get-ChildItem -LiteralPath $toolsDirectory -Directory){
            $cl=Join-Path $tool.FullName 'bin\Hostx64\x64\cl.exe'
            if(Test-Path -LiteralPath $cl -PathType Leaf){
                $compilers += [ordered]@{visual_studio_version=$instance.installationVersion; msvc_version=$tool.Name; path=$cl}
            }
        }
    }
}
$sdkRoots=@()
foreach($registryPath in @('HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows Kits\Installed Roots')){
    if(Test-Path -LiteralPath $registryPath){
        $kit=Get-ItemProperty -LiteralPath $registryPath
        if($kit.KitsRoot10){$sdkRoots += $kit.KitsRoot10}
    }
}
$sdkRoots += (Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10')
$sdks=@()
foreach($sdkRoot in @($sdkRoots | Select-Object -Unique)){
    $includes=Join-Path $sdkRoot 'Include'
    if(Test-Path -LiteralPath $includes -PathType Container){
        foreach($sdk in Get-ChildItem -LiteralPath $includes -Directory){
            $header=Join-Path $sdk.FullName 'um\Windows.h'
            $library=Join-Path $sdkRoot "Lib\$($sdk.Name)\um\x64\kernel32.lib"
            $resourceCompiler=Join-Path $sdkRoot "bin\$($sdk.Name)\x64\rc.exe"
            $sdks += [ordered]@{version=$sdk.Name;root=$sdkRoot;
                windows_header=(Test-Path -LiteralPath $header -PathType Leaf);
                kernel32_library=(Test-Path -LiteralPath $library -PathType Leaf);
                resource_compiler=(Test-Path -LiteralPath $resourceCompiler -PathType Leaf)}
        }
    }
}
$reasons=@()
if(@($fileChecks | Where-Object {-not $_.exists}).Count){$reasons+='Required engine files missing; installation is not ready for build.'}
if($null -eq $engineVersion -or $engineVersion.MajorVersion -ne 5 -or $engineVersion.MinorVersion -ne 8){$reasons+='UE 5.8 Build.version not confirmed.'}
if(-not $compilers.Count){$reasons+='MSVC x64 compiler not discovered; do not infer absence solely from PATH.'}
if(-not @($sdks | Where-Object {$_.windows_header -and $_.kernel32_library -and $_.resource_compiler}).Count){$reasons+='Windows SDK header, x64 library and resource compiler not discovered together.'}
$report=[ordered]@{
    schema='t3b-unreal-environment-inventory/v1'
    checked_at_utc=[DateTime]::UtcNow.ToString('o')
    engine_root=$engineDirectory
    engine_files=$fileChecks
    engine_version=$engineVersion
    launcher_registration=$launcherEntries
    launcher_item_registration=$modernLauncherEntries
    compiler_discovery=$discovery
    msvc_compilers=$compilers
    windows_sdks=$sdks
    inventory_gaps=$reasons
    ready_for_build_attempt=($reasons.Count -eq 0)
    toolchain_compatibility_verified=$false
    unreal_build_executed=$false
    scope='File/component discovery only; UnrealBuildTool determines actual compatibility.'
    requirements_source='https://dev.epicgames.com/documentation/en-us/unreal-engine/setting-up-visual-studio-development-environment-for-cplusplus-projects-in-unreal-engine'
}
$json=$report | ConvertTo-Json -Depth 8
if($ReportPath){
    $absoluteReport=[System.IO.Path]::GetFullPath($ReportPath)
    $parent=[System.IO.Path]::GetDirectoryName($absoluteReport)
    if(-not(Test-Path -LiteralPath $parent -PathType Container)){throw "Report parent missing: $parent"}
    [System.IO.File]::WriteAllText($absoluteReport,$json+[Environment]::NewLine,[System.Text.UTF8Encoding]::new($false))
}
Write-Output $json
