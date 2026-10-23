[CmdletBinding()]
param([switch]$HDSampling,[switch]$TestSourceSpawn)
$ErrorActionPreference='Stop'
$repoRoot=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$projectRoot=Join-Path $repoRoot 'work\t3b_hd'
foreach($relative in @('t3b_hd.exe','SDL2.dll','assets\models\original_actor_source.bin')) {
    if(-not(Test-Path -LiteralPath (Join-Path $projectRoot $relative) -PathType Leaf)) {
        throw "Runtime bundle missing: $relative. Install the private ZIP first."
    }
}
$runtimeArgs=@()
if($HDSampling){$runtimeArgs+='--hd-sampling'}
if($TestSourceSpawn){$runtimeArgs+='--test-source-spawn'}
Push-Location -LiteralPath $projectRoot
try {
    & (Join-Path $projectRoot 't3b_hd.exe') @runtimeArgs
    if($LASTEXITCODE -ne 0){throw "M1 runtime failed: exit $LASTEXITCODE"}
} finally { Pop-Location }
