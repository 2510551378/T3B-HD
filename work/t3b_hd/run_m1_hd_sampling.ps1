param(
    [switch]$Preview,
    [switch]$TestSourceSpawn,
    [switch]$TestApproachFire
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root

$args = @('--hd-sampling')
if ($Preview) { $args += '--preview' }
if ($TestSourceSpawn) { $args += '--test-source-spawn' }
if ($TestApproachFire) { $args += '--test-approach-fire' }

& (Join-Path $root 't3b_hd.exe') @args
exit $LASTEXITCODE
