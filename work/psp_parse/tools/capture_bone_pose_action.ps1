param(
  [Parameter(Mandatory=$true)][string]$Action,
  [int]$Frames = 24,
  [string]$ButtonsJson = '{}',
  [string]$AnalogJson = '',
  [string]$StatePath = '',
  [string]$CaptureScript = '',
  [int]$StartupSeconds = 7,
  [int]$WarmupSeconds = 0,
  [switch]$ShowWindow,
  [switch]$DenseSource,
  [string]$WorldBinding = '',
  [int]$PreRollFrames = 0,
  [string]$PreRollAnalogJson = '',
  [int]$InspectionSeconds = 0,
  [int]$Port = 9900
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$pp = (Resolve-Path (Join-Path $root 'PSP\ppsspp1204\PPSSPPWindows64.exe')).Path
$state = if ($StatePath) { (Resolve-Path -LiteralPath $StatePath).Path } else { (Resolve-Path (Join-Path $root 'PSP\ppsspp1204\memstick\PSP\PPSSPP_STATE\ULJM05798_1.01_1.ppst')).Path }
$iso = (Resolve-Path (Join-Path $root 'PSP\The_3rd_birthday_cn_full_v101.iso')).Path
$ini = (Resolve-Path (Join-Path $root 'PSP\ppsspp1204\memstick\PSP\SYSTEM\ppsspp.ini')).Path
$outRoot = Join-Path $root ('work\psp_parse\out\AYA_BONE_GE_ACTIONS\' + $Action)
$script = if ($CaptureScript) { (Resolve-Path -LiteralPath $CaptureScript).Path } else { Join-Path $root 'work\psp_parse\tools\trace_bone_ge_pairs.js' }
if (Get-Process -Name PPSSPPWindows64 -ErrorAction SilentlyContinue) { throw 'PPSSPP is already running. Close it before an isolated capture.' }
New-Item -ItemType Directory -Force -Path $outRoot | Out-Null
$originalBytes = [System.IO.File]::ReadAllBytes($ini)
$original = Get-Content -LiteralPath $ini -Raw -Encoding UTF8
$configured = $original -replace 'RemoteDebuggerOnStartup = False','RemoteDebuggerOnStartup = True' -replace 'RemoteDebuggerLocal = False','RemoteDebuggerLocal = True' -replace 'RemoteISOPort = 0',('RemoteISOPort = ' + $Port)
Set-Content -LiteralPath $ini -Value $configured -Encoding UTF8
try {
  $captureWindowStyle = if ($ShowWindow) { 'Normal' } else { 'Hidden' }
  $p = Start-Process -FilePath $pp -ArgumentList @(('"--state=' + $state + '"'), ('"' + $iso + '"')) -WorkingDirectory (Split-Path $pp) -WindowStyle $captureWindowStyle -PassThru
  Start-Sleep -Seconds ([Math]::Max(1, $StartupSeconds) + [Math]::Max(0, $WarmupSeconds))
  $env:PPSSPP_DEBUGGER_PORT = [string]$Port
  $env:BONE_PAIR_FRAMES = [string]$Frames
  $env:BONE_PAIR_DIR = $outRoot
  $env:BONE_PAIR_BUTTONS_JSON = $ButtonsJson
  $env:BONE_SOURCE_DENSE = if ($DenseSource) { '1' } else { '0' }
  $env:BONE_PREROLL_FRAMES = [string]$PreRollFrames
  if ($PreRollAnalogJson) { $env:BONE_PREROLL_ANALOG = $PreRollAnalogJson } else { Remove-Item Env:BONE_PREROLL_ANALOG -ErrorAction SilentlyContinue }
  if ($WorldBinding) { $env:BONE_WORLD_BINDING = (Resolve-Path -LiteralPath $WorldBinding).Path } else { Remove-Item Env:BONE_WORLD_BINDING -ErrorAction SilentlyContinue }
  $env:BONE_ACTION_HOLD_MS = [string]([Math]::Max(0, [Math]::Min(60, $InspectionSeconds)) * 1000)
  if ($AnalogJson) { $env:BONE_PAIR_ANALOG_JSON = $AnalogJson } else { Remove-Item Env:BONE_PAIR_ANALOG_JSON -ErrorAction SilentlyContinue }
  node $script
  if ($LASTEXITCODE -ne 0) { throw ('Capture failed with exit code ' + $LASTEXITCODE) }
} finally {
  Remove-Item Env:PPSSPP_DEBUGGER_PORT,Env:BONE_PAIR_FRAMES,Env:BONE_PAIR_DIR,Env:BONE_PAIR_BUTTONS_JSON,Env:BONE_PAIR_ANALOG_JSON,Env:BONE_ACTION_HOLD_MS,Env:BONE_SOURCE_DENSE,Env:BONE_WORLD_BINDING,Env:BONE_PREROLL_FRAMES,Env:BONE_PREROLL_ANALOG -ErrorAction SilentlyContinue
  if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
  [System.IO.File]::WriteAllBytes($ini, $originalBytes)
}
