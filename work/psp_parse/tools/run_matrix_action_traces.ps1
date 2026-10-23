param(
  [int]$DurationMs = 1500,
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
)
$ErrorActionPreference = 'Stop'
$exe = (Resolve-Path -LiteralPath (Join-Path $Root 'PSP\ppsspp1204\PPSSPPWindows64.exe')).Path
$state = (Resolve-Path -LiteralPath (Join-Path $Root 'PSP\ppsspp1204\memstick\PSP\PPSSPP_STATE\ULJM05798_1.01_1.ppst')).Path
$iso = (Resolve-Path -LiteralPath (Join-Path $Root 'PSP\The_3rd_birthday_cn_full_v101.iso')).Path
$ini = (Resolve-Path -LiteralPath (Join-Path $Root 'PSP\ppsspp1204\memstick\PSP\SYSTEM\ppsspp.ini')).Path
$original = Get-Content -LiteralPath $ini -Raw -Encoding UTF8
$configured = $original -replace 'RemoteDebuggerOnStartup = False','RemoteDebuggerOnStartup = True' -replace 'RemoteDebuggerLocal = False','RemoteDebuggerLocal = True' -replace 'RemoteISOPort = 0','RemoteISOPort = 9900'
Set-Content -LiteralPath $ini -Value $configured -Encoding UTF8
$square = @{ square = $true } | ConvertTo-Json -Compress
$ltriggerSquare = @{ square = $true; ltrigger = $true } | ConvertTo-Json -Compress
$rtriggerSquare = @{ square = $true; rtrigger = $true } | ConvertTo-Json -Compress
$left = @{ stick = 'left'; x = -1; y = 0 } | ConvertTo-Json -Compress
$right = @{ stick = 'left'; x = 1; y = 0 } | ConvertTo-Json -Compress
$actions = @(
  @{ Name='square'; Buttons=$square; Analog='' },
  @{ Name='ltrigger_square'; Buttons=$ltriggerSquare; Analog='' },
  @{ Name='rtrigger_square'; Buttons=$rtriggerSquare; Analog='' },
  @{ Name='ltrigger_square_strafe_left'; Buttons=$ltriggerSquare; Analog=$left },
  @{ Name='square_strafe_right'; Buttons=$square; Analog=$right }
)
try {
  foreach ($action in $actions) {
    Get-Process -Name PPSSPPWindows64 -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Milliseconds 400
    $p = Start-Process -FilePath $exe -ArgumentList @(("--state=$state"),$iso) -WorkingDirectory (Split-Path $exe) -PassThru
    Start-Sleep -Seconds 6
    $env:MATRIX_TRACE_OUT = Join-Path $Root ("work\psp_parse\out\AYA_MATRIX_ACTION_" + $action.Name + '.json')
    $env:MATRIX_TRACE_TARGETS = '0x08bfff98'
    $env:MATRIX_TRACE_MS = [string]$DurationMs
    $env:MATRIX_TRACE_BUTTONS_JSON = $action.Buttons
    $env:MATRIX_TRACE_ANALOG_JSON = $action.Analog
    node (Join-Path $Root 'work\psp_parse\tools\trace_matrix_calls.js')
    Get-Process -Name PPSSPPWindows64 -ErrorAction SilentlyContinue | Stop-Process -Force
  }
}
finally {
  Set-Content -LiteralPath $ini -Value $original -Encoding UTF8
  Remove-Item Env:MATRIX_TRACE_OUT,Env:MATRIX_TRACE_TARGETS,Env:MATRIX_TRACE_MS,Env:MATRIX_TRACE_BUTTONS_JSON,Env:MATRIX_TRACE_ANALOG_JSON -ErrorAction SilentlyContinue
}
