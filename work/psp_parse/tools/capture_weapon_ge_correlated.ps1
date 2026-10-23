param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [int]$Rows=12,
    [int]$GEFrames=4,
    [string]$ButtonsJson='{"square":true,"rtrigger":true}',
    [string]$AnalogJson='',
    [switch]$FullHandlerDL,
    [string]$CaptureScript=''
)
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$source=Join-Path $root 'PSP\ppsspp1204'
$state=Join-Path $source 'memstick\PSP\PPSSPP_STATE\ULJM05798_1.01_0.ppst'
$ini=Join-Path $source 'memstick\PSP\SYSTEM\ppsspp.ini'
$iso=Join-Path $root 'PSP\The_3rd_birthday_cn_full_v101.iso'
$script=if($CaptureScript){(Resolve-Path -LiteralPath $CaptureScript).Path}else{Join-Path $PSScriptRoot 'trace_weapon_marker_ge_emit.js'}
$out=[IO.Path]::GetFullPath($OutputDirectory)
if(Test-Path -LiteralPath $out){throw 'Never reuse capture output'}
if(Get-Process -Name PPSSPPWindows64 -ErrorAction SilentlyContinue){throw 'An existing emulator is running; left unchanged'}
if($Rows -lt 1 -or $Rows -gt 24 -or $GEFrames -lt 1 -or $GEFrames -gt 16){throw 'Unsupported capture bounds'}
$assets=Join-Path $source 'assets'
if((Get-Item -LiteralPath $assets).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Asset root is a reparse point'}
if(Get-ChildItem -LiteralPath $assets -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }){throw 'Asset tree contains a reparse point'}
$before=@($iso,$state,$ini)|ForEach-Object{[ordered]@{file=$_;sha256=(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant()}}
New-Item -ItemType Directory -Path $out | Out-Null
$portable=Join-Path $out 'portable_ppsspp'
$system=Join-Path $portable 'memstick\PSP\SYSTEM'
New-Item -ItemType Directory -Path $system -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $source 'PPSSPPWindows64.exe') -Destination $portable
Copy-Item -LiteralPath $assets -Destination $portable -Recurse
$stateCopy=Join-Path $out 'readonly_input_slot0.ppst'
Copy-Item -LiteralPath $state -Destination $stateCopy
Copy-Item -LiteralPath $script -Destination (Join-Path $out ('executed_'+[IO.Path]::GetFileName($script)))
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $out 'executed_capture_runner.ps1')
$controls=Join-Path $source 'memstick\PSP\SYSTEM\controls.ini'
if(Test-Path -LiteralPath $controls){Copy-Item -LiteralPath $controls -Destination $system}
$listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0)
$listener.Start();$port=$listener.LocalEndpoint.Port;$listener.Stop()
$configuration=Get-Content -LiteralPath $ini -Raw -Encoding UTF8
$configuration=$configuration -replace '(?m)^RemoteDebuggerOnStartup = .*$', 'RemoteDebuggerOnStartup = True'
$configuration=$configuration -replace '(?m)^RemoteDebuggerLocal = .*$', 'RemoteDebuggerLocal = True'
$configuration=$configuration -replace '(?m)^RemoteISOPort = .*$', ('RemoteISOPort = '+$port)
[IO.File]::WriteAllText((Join-Path $system 'ppsspp.ini'),$configuration,[Text.UTF8Encoding]::new($false))
$exe=Join-Path $portable 'PPSSPPWindows64.exe'
$arguments=@(('"--state='+$stateCopy+'"'),('"'+$iso+'"'))
$process=$null;$nodeCode=$null
[ordered]@{started_at_utc=[datetime]::UtcNow.ToString('o');protected_files=$before;executable=$exe;executable_sha256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant();arguments=$arguments;port=$port;original_configuration_modified=$false;state_copy=$stateCopy;producer_sha256=(Get-FileHash -LiteralPath $script -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $out 'request.json') -Encoding utf8
try{
    $process=Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $portable -WindowStyle Hidden -PassThru
    [ordered]@{pid=$process.Id;started_at_utc=[datetime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'process_started.json') -Encoding utf8
    Write-Output ('Owned isolated PPSSPP PID '+$process.Id+' port '+$port+' output '+$out)
    Start-Sleep -Seconds 7
    if($process.HasExited){throw 'Isolated PPSSPP exited before capture'}
    $env:PPSSPP_DEBUGGER_PORT=[string]$port
    $env:MARKER_GE_EMIT_OUT_DIR=$out
    $env:MARKER_MAX_ROWS=[string]$Rows
    $env:MARKER_MAX_STOPS='1600'
    $env:MARKER_DURATION_MS='30000'
    $env:MARKER_STAGE_TIMEOUT_MS='8000'
    $env:MARKER_BUTTONS_JSON=$ButtonsJson
    if($AnalogJson){$env:MARKER_ANALOG_JSON=$AnalogJson}else{Remove-Item Env:MARKER_ANALOG_JSON -ErrorAction SilentlyContinue}
    $env:MARKER_CAPTURE_SOURCE_WORLD='1'
    if($FullHandlerDL){$env:MARKER_CAPTURE_FULL_HANDLER_DL='1'}else{Remove-Item Env:MARKER_CAPTURE_FULL_HANDLER_DL -ErrorAction SilentlyContinue}
    $env:MARKER_GE_CAPTURE_FRAMES=[string]$GEFrames
    $env:MARKER_GE_CAPTURE_ARM='target'
    & 'C:\Program Files\nodejs\node.exe' $script 1> (Join-Path $out 'node_stdout.log') 2> (Join-Path $out 'node_stderr.log')
    $nodeCode=$LASTEXITCODE
    if($nodeCode -ne 0){throw ('Capture returned '+$nodeCode+'; evidence retained')}
}finally{
    Remove-Item Env:PPSSPP_DEBUGGER_PORT,Env:MARKER_GE_EMIT_OUT_DIR,Env:MARKER_MAX_ROWS,Env:MARKER_MAX_STOPS,Env:MARKER_DURATION_MS,Env:MARKER_STAGE_TIMEOUT_MS,Env:MARKER_BUTTONS_JSON,Env:MARKER_CAPTURE_SOURCE_WORLD,Env:MARKER_GE_CAPTURE_FRAMES,Env:MARKER_GE_CAPTURE_ARM,Env:MARKER_ANALOG_JSON,Env:MARKER_CAPTURE_FULL_HANDLER_DL -ErrorAction SilentlyContinue
    if($process -and -not $process.HasExited){Stop-Process -Id $process.Id -Force;$process.WaitForExit()}
    $after=@($before|ForEach-Object{$digest=(Get-FileHash -LiteralPath $_.file -Algorithm SHA256).Hash.ToLowerInvariant();[ordered]@{file=$_.file;sha256=$digest;expected_sha256=$_.sha256;unchanged=($digest -eq $_.sha256)}})
    $passed=@($after|Where-Object{-not $_.unchanged}).Count -eq 0
    [ordered]@{completed_at_utc=[datetime]::UtcNow.ToString('o');node_exit_code=$nodeCode;owned_emulator_stopped=($process -and $process.HasExited);protected_files=$after;protection_passed=$passed} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $out 'process_completed.json') -Encoding utf8
    if(-not $passed){throw 'Original file hash changed'}
}
Write-Output ('Capture finished; inspect original raw CPU and GE evidence in '+$out)
