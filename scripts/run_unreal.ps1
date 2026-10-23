[CmdletBinding()]
param(
    [string]$EngineRoot='C:\Program Files\Epic Games\UE_5.8',
    [switch]$Build,
    [switch]$Game,
    [switch]$ValidateOnly
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$repoRoot=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$projectRoot=Join-Path $repoRoot 'work\t3b_unreal'
$editorFile=Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe'
if(-not(Test-Path -LiteralPath $editorFile -PathType Leaf)){throw "Install Unreal Engine 5.8 first: $editorFile"}
foreach($relative in @('Content\SourceData\manifest.json','Content\T3B\Maps\M1_SourceReplay.umap')) {
    if(-not(Test-Path -LiteralPath (Join-Path $projectRoot $relative) -PathType Leaf)){throw "Runtime bundle missing: $relative"}
}
if(-not $Build){
    $installedFile=Join-Path $repoRoot 'build\runtime_bundle\installed_manifest.json'
    if(-not(Test-Path -LiteralPath $installedFile -PathType Leaf)){throw 'Install the private bundle, or use -Build for your local sources.'}
    $bundle=Get-Content -LiteralPath $installedFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $engineModules=Get-Content -LiteralPath (Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.modules') -Raw -Encoding UTF8 | ConvertFrom-Json
    if($engineModules.BuildId -ne $bundle.engine_build_id){throw 'Precompiled module uses a different UE build. Install the matching engine or run with -Build.'}
    foreach($entry in $bundle.required_module_sources.PSObject.Properties){
        $path=Join-Path $repoRoot $entry.Name
        if(-not(Test-Path -LiteralPath $path -PathType Leaf) -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value){
            throw "Sources differ from the precompiled module: $($entry.Name). Run with -Build."
        }
    }
    foreach($entry in @($bundle.files | Where-Object {$_.path -like 'work/t3b_unreal/Binaries/*'})){
        $path=Join-Path $repoRoot $entry.path
        if(-not(Test-Path -LiteralPath $path -PathType Leaf) -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256){throw "Precompiled module missing or changed: $($entry.path). Reinstall bundle or use -Build."}
    }
}
if($ValidateOnly){Write-Output 'UE launch prerequisites validated; editor not started.';return}
if($Build){& (Join-Path $projectRoot 'Tools\build_unreal.ps1') -EngineRoot $EngineRoot -Target Editor}
$editorArgs=@((Join-Path $projectRoot 'T3BRemake.uproject'))
if($Game){$editorArgs+=@('/Game/T3B/Maps/M1_SourceReplay','-game')}
Start-Process -FilePath $editorFile -ArgumentList ($editorArgs | ForEach-Object {'"'+$_+'"'}) -WorkingDirectory $projectRoot
