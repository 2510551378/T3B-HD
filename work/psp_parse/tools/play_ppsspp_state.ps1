$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$pp = (Resolve-Path (Join-Path $root 'PSP\ppsspp1204\PPSSPPWindows64.exe')).Path
$state = (Resolve-Path (Join-Path $root 'PSP\ppsspp1204\memstick\PSP\PPSSPP_STATE\ULJM05798_1.01_1.ppst')).Path
$iso = (Resolve-Path (Join-Path $root 'PSP\The_3rd_birthday_cn_full_v101.iso')).Path
$ini = (Resolve-Path (Join-Path $root 'PSP\ppsspp1204\memstick\PSP\SYSTEM\ppsspp.ini')).Path
$original = Get-Content -LiteralPath $ini -Raw -Encoding UTF8
$configured = $original -replace 'RemoteDebuggerOnStartup = False','RemoteDebuggerOnStartup = True' -replace 'RemoteDebuggerLocal = False','RemoteDebuggerLocal = True' -replace 'RemoteISOPort = 0','RemoteISOPort = 9900'
Set-Content -LiteralPath $ini -Value $configured -Encoding UTF8
Get-Process -Name PPSSPPWindows64 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $pp -ArgumentList @('--state=' + $state, $iso) -WorkingDirectory (Split-Path $pp) -PassThru
Start-Sleep -Seconds 7
$env:PPSSPP_DEBUGGER_PORT = '9900'
node (Join-Path $root 'work\psp_parse\tools\play_ppsspp_input.js')
Remove-Item Env:PPSSPP_DEBUGGER_PORT -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'work\psp_parse\tools\win_capture.ps1') -Out (Join-Path $root 'work\psp_parse\out\preview\played_debugger_input.png') -ProcessName PPSSPP
Get-Process -Name PPSSPPWindows64 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Set-Content -LiteralPath $ini -Value $original -Encoding UTF8
