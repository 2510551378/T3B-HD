[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$EngineRoot,
    [switch]$Build,
    [switch]$ImportSourceAssets,
    [switch]$Game,
    [switch]$ValidateOnly
)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$projectDirectory = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$projectDescriptor = Join-Path $projectDirectory 'T3BRemake.uproject'
$engineDirectory = (Resolve-Path -LiteralPath $EngineRoot).Path
& (Join-Path $PSScriptRoot 'build_unreal.ps1') -EngineRoot $engineDirectory -ValidateOnly
$editorExecutable = Join-Path $engineDirectory 'Engine\Binaries\Win64\UnrealEditor.exe'
$commandletExecutable = Join-Path $engineDirectory 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
foreach ($requiredExecutable in @($editorExecutable,$commandletExecutable)) {
    if (-not (Test-Path -LiteralPath $requiredExecutable -PathType Leaf)) { throw "Required official UE executable missing: $requiredExecutable" }
}
$bundleManifest = Join-Path $projectDirectory 'Content\SourceData\manifest.json'
if (-not (Test-Path -LiteralPath $bundleManifest -PathType Leaf)) { throw 'Stage the verified source bundle with Tools/stage_source_bundle.py first.' }
if ($ValidateOnly) { Write-Output 'Paths validated; no build, import or editor was executed.'; return }
if ($Build) { & (Join-Path $PSScriptRoot 'build_unreal.ps1') -EngineRoot $engineDirectory }
if ($ImportSourceAssets) {
    $priorRunId = $env:T3B_EDITOR_RUN_ID
    $editorRunId = [guid]::NewGuid().ToString()
    $env:T3B_EDITOR_RUN_ID = $editorRunId
    try {
        $importScript = Join-Path $PSScriptRoot 'editor_build_source_assets.py'
        & $commandletExecutable $projectDescriptor "-ExecutePythonScript=$importScript" -unattended -nop4 -nosplash -stdout -FullStdOutLogOutput
        if ($LASTEXITCODE -ne 0) { throw "Unreal asset creation failed: exit $LASTEXITCODE" }
        $creationReport = Join-Path $projectDirectory 'Validation\ue_editor_asset_creation.json'
        if (-not (Test-Path -LiteralPath $creationReport -PathType Leaf)) { throw 'UE did not produce an asset-creation report.' }
        $creation = Get-Content -LiteralPath $creationReport -Raw -Encoding UTF8 | ConvertFrom-Json
        $bundleHash = (Get-FileHash -LiteralPath $bundleManifest -Algorithm SHA256).Hash.ToLowerInvariant()
        if (-not $creation.asset_creation_completed -or $creation.run_id -ne $editorRunId -or $creation.manifest_sha256 -ne $bundleHash) {
            throw 'UE asset creation report is failed, stale, or belongs to a different source bundle.'
        }
        Write-Output 'Source assets created by the editor. Runtime geometry, materials and gameplay remain separate acceptance checks.'
    } finally {
        if ($null -eq $priorRunId) { Remove-Item Env:T3B_EDITOR_RUN_ID -ErrorAction SilentlyContinue }
        else { $env:T3B_EDITOR_RUN_ID = $priorRunId }
    }
}
$editorArguments = @($projectDescriptor)
if ($Game) { $editorArguments += @('-game','-log') }
& $editorExecutable @editorArguments
if ($LASTEXITCODE -ne 0) { throw "Unreal Editor exited with code $LASTEXITCODE" }
