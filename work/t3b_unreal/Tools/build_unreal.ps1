[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$EngineRoot,
    [ValidateSet('Development','DebugGame','Shipping')][string]$Configuration='Development',
    [ValidateSet('Editor','Game')][string]$Target='Editor',
    [switch]$ValidateOnly
)
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
$projectRoot=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$projectFile=Join-Path $projectRoot 'T3BRemake.uproject'
$engineDirectory=(Resolve-Path -LiteralPath $EngineRoot -ErrorAction Stop).Path
$buildFile=Join-Path $engineDirectory 'Engine\Build\BatchFiles\Build.bat'
$versionFile=Join-Path $engineDirectory 'Engine\Build\Build.version'
if(-not(Test-Path -LiteralPath $projectFile -PathType Leaf)){throw "Project descriptor missing: $projectFile"}
if(-not(Test-Path -LiteralPath $buildFile -PathType Leaf)){throw "Official UE Build.bat missing under explicit EngineRoot: $buildFile"}
if(-not(Test-Path -LiteralPath $versionFile -PathType Leaf)){throw "UE Build.version missing: $versionFile"}
$version=Get-Content -LiteralPath $versionFile -Encoding UTF8 -Raw | ConvertFrom-Json
if($version.MajorVersion -ne 5 -or $version.MinorVersion -ne 8){throw "UE 5.8 required; explicit EngineRoot reports $($version.MajorVersion).$($version.MinorVersion)"}
if($Target -eq 'Editor' -and $Configuration -eq 'Shipping'){throw 'Shipping is a Game target configuration; select -Target Game.'}
$buildTarget=if($Target -eq 'Editor'){'T3BRemakeEditor'}else{'T3BRemake'}
Write-Output "Validated UE $($version.MajorVersion).$($version.MinorVersion), project $projectFile; no engine is downloaded or installed by this script."
if($ValidateOnly){Write-Output 'Validation only: no Unreal build was executed.';exit 0}
& $buildFile $buildTarget Win64 $Configuration "-Project=$projectFile" -WaitMutex -NoHotReloadFromIDE
if($LASTEXITCODE -ne 0){throw "Official Unreal build failed, exit code $LASTEXITCODE"}
Write-Output 'Official Build.bat returned success. Editor runtime and visual acceptance remain separate checks.'
