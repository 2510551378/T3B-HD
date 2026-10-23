#requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$EngineRoot,
    [ValidateRange(1,120)][int]$TimeoutMinutes=20,
    [switch]$ValidateOnly
)
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
$projectRoot=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$hostProject=Join-Path $projectRoot 'T3BAssetImport.uproject'
$verifyScript=Join-Path $PSScriptRoot 'verify_saved_source_assets.py'
$frozenVerified=Join-Path $projectRoot 'Validation\asset_import_runs\0fac54502ca140d4accffa2e5a7bc618\verified.json'
$engineDirectory=(Resolve-Path -LiteralPath $EngineRoot).Path
$editorCommand=Join-Path $engineDirectory 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$versionPath=Join-Path $engineDirectory 'Engine\Build\Build.version'
foreach($file in @($hostProject,$verifyScript,$frozenVerified,$editorCommand,$versionPath)){
    if(-not(Test-Path -LiteralPath $file -PathType Leaf)){throw "Required reload verification file missing: $file"}
    if($file.Contains('"') -or $file.Contains("`n") -or $file.Contains("`r")){throw 'Quoted/newline native command path rejected.'}
}
$version=Get-Content -LiteralPath $versionPath -Raw -Encoding UTF8 | ConvertFrom-Json
if($version.MajorVersion -ne 5 -or $version.MinorVersion -ne 8){throw 'Explicit UE5.8 engine root required.'}
$frozen=Get-Content -LiteralPath $frozenVerified -Raw -Encoding UTF8 | ConvertFrom-Json
if(-not $frozen.passed -or $frozen.exit_code -ne 0 -or $frozen.saved_packages_verified -ne 161){throw 'Frozen asset creation was not verified.'}
$importReport=$frozen.source_report
$import=Get-Content -LiteralPath $importReport -Raw -Encoding UTF8 | ConvertFrom-Json
foreach($saved in $import.saved_assets){
    if((Get-FileHash -LiteralPath $saved.file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $saved.sha256){throw "Frozen package changed before reload: $($saved.file)"}
}
$verifierHash=(Get-FileHash -LiteralPath $verifyScript -Algorithm SHA256).Hash.ToLowerInvariant()
$frozenHash=(Get-FileHash -LiteralPath $importReport -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output 'Validated frozen76textures84materials1map; second-process read-only NullRHI verification, no import/save/C++ build.'
if($ValidateOnly){Write-Output 'Validation only: no UE process started.';return}
$runId=[guid]::NewGuid().ToString('N')
$runDirectory=Join-Path $projectRoot "Validation\asset_reload_runs\$runId"
New-Item -ItemType Directory -Path $runDirectory | Out-Null
$reportPath=Join-Path $runDirectory 'ue_saved_assets_reload.json'
$engineLog=Join-Path $runDirectory 'UnrealEditor-Cmd.log'
$arguments=@(('"'+$hostProject+'"'),'-run=pythonscript',('-script="'+$verifyScript+'"'),
    '-unattended','-NullRHI','-nosplash','-nosound','-nop4','-NoCrashDialog','-UTF8Output','-stdout','-FullStdOutLogOutput',
    ('-abslog="'+$engineLog+'"'),'-ini:Engine:[/Script/EngineSettings.GameMapsSettings]:GlobalDefaultGameMode=/Script/Engine.GameModeBase') -join ' '
$request=@{schema='t3b-ue-saved-assets-reload-request/v1';run_id=$runId;requested_utc=[datetime]::UtcNow.ToString('o');
    executable=$editorCommand;arguments=$arguments;verifier_sha256=$verifierHash;frozen_import_report=$importReport;
    frozen_import_sha256=$frozenHash;report=$reportPath;read_only=$true}
$request | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $runDirectory 'request.json') -Encoding utf8
$info=[System.Diagnostics.ProcessStartInfo]::new()
$info.FileName=$editorCommand;$info.Arguments=$arguments;$info.WorkingDirectory=$projectRoot
$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.WindowStyle=[System.Diagnostics.ProcessWindowStyle]::Hidden
$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
$info.StandardOutputEncoding=[System.Text.UTF8Encoding]::new($false);$info.StandardErrorEncoding=[System.Text.UTF8Encoding]::new($false)
$info.Environment['T3B_VERIFY_RUN_ID']=$runId;$info.Environment['T3B_VERIFY_REPORT_PATH']=$reportPath;$info.Environment['T3B_VERIFY_IMPORT_REPORT']=$importReport
$process=[System.Diagnostics.Process]::new();$process.StartInfo=$info
$startUtc=[datetime]::UtcNow
Write-Output "Starting hidden read-only reload commandlet run_id=$runId; $runDirectory"
if(-not $process.Start()){throw 'Failed to start UnrealEditor-Cmd.'}
$processId=$process.Id;$outputRead=$process.StandardOutput.ReadToEndAsync();$errorRead=$process.StandardError.ReadToEndAsync()
$timedOut=-not $process.WaitForExit($TimeoutMinutes*60000)
if($timedOut){$process.Kill($true);$process.WaitForExit()}
$stdout=$outputRead.GetAwaiter().GetResult();$stderr=$errorRead.GetAwaiter().GetResult()
[System.IO.File]::WriteAllText((Join-Path $runDirectory 'stdout.log'),$stdout,[System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText((Join-Path $runDirectory 'stderr.log'),$stderr,[System.Text.UTF8Encoding]::new($false))
if($timedOut){throw "Reload verification timed out; preserved logs: $runDirectory"}
if($process.ExitCode -ne 0){throw "Reload commandlet failed exit=$($process.ExitCode); preserved report/logs: $runDirectory"}
if(-not(Test-Path -LiteralPath $reportPath -PathType Leaf)){throw 'Exit0 without a fresh reload report is not accepted.'}
$report=Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
if($report.schema -ne 't3b-ue-saved-assets-reload/v1' -or -not $report.passed -or $report.run_id -ne $runId -or $report.process_id -ne $processId){throw 'Reload report failed schema/success/run_id/PID validation.'}
if($report.frozen_import_report_sha256 -ne $frozenHash -or $report.verifier_sha256 -ne $verifierHash){throw 'Reload report input/script identities differ.'}
if([System.IO.Path]::GetFullPath($report.project_file) -ne [System.IO.Path]::GetFullPath($hostProject)){throw 'Reload report came from a different project host.'}
if((Get-Item -LiteralPath $reportPath).LastWriteTimeUtc -lt $startUtc.AddSeconds(-2)){throw 'Stale reload report timestamp.'}
if($report.textures_reloaded -ne 76 -or $report.materials_reloaded -ne 84 -or $report.package_files_checked -ne 161 -or -not $report.package_files_unchanged -or -not $report.empty_content_map){throw 'Reload inventory or read-only package validation incomplete.'}
if($report.ue_render_verified -or $report.ue_cpp_build_executed -or $report.ue_gameplay_executed){throw 'Read-only reload incorrectly claims render/gameplay/build acceptance.'}
foreach($saved in $import.saved_assets){
    if((Get-FileHash -LiteralPath $saved.file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $saved.sha256){throw "Package changed after read-only reload: $($saved.file)"}
}
$missing=@(($stdout+"`n"+$stderr) -split "`n" | Where-Object {$_ -match '(?i)(Failed to (load|find).*[/]Game[/]T3B|Can.t find file.*[/]Game[/]T3B|Error:.*[/]Game[/]T3B)'})
if($missing.Count){$missing | Set-Content -LiteralPath (Join-Path $runDirectory 'missing_reference_log_errors.txt') -Encoding utf8;throw 'Commandlet logs contain T3B asset missing-reference errors.'}
$verified=@{schema='t3b-ue-saved-assets-reload-verification/v1';passed=$true;run_id=$runId;process_id=$processId;exit_code=$process.ExitCode;
    source_report=$reportPath;source_report_sha256=(Get-FileHash -LiteralPath $reportPath -Algorithm SHA256).Hash.ToLowerInvariant();
    textures=76;materials=84;empty_maps=1;package_files_unchanged=161;missing_T3B_reference_log_errors=0;
    verified_utc=[datetime]::UtcNow.ToString('o');ue_render_verified=$false;ue_cpp_build_executed=$false;ue_gameplay_executed=$false}
$verifiedPath=Join-Path $runDirectory 'verified.json';$verified | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $verifiedPath -Encoding utf8
Write-Output "Second-process saved-asset reload passed. Report: $verifiedPath"
Write-Output 'Scope: texture settings, material metadata/graph, map/package references and unchanged161files. No pixels/shaders/gameplay/C++ runtime accepted.'
