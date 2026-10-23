#requires -Version 7.2
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$EngineRoot,[Parameter(Mandatory=$true)][string]$ImportReport)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$inputPath=(Resolve-Path -LiteralPath $ImportReport).Path
$source=Get-Content -LiteralPath $inputPath -Raw -Encoding UTF8|ConvertFrom-Json
if(-not $source.verified_source_material_bound){throw 'Import report must contain verified source material binding.'}
$exe=Join-Path (Resolve-Path -LiteralPath $EngineRoot).Path 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
$hostProject=Join-Path $root 'T3BNativeImport.uproject'
$script=Join-Path $PSScriptRoot 'verify_aya_native_saved.py'
foreach($path in @($exe,$hostProject,$script,$inputPath)){if(-not(Test-Path -LiteralPath $path -PathType Leaf)-or $path.Contains('"')-or $path.Contains("`n")){throw 'Invalid explicit input path.'}}
$id=[guid]::NewGuid().ToString('N');$dir=Join-Path $root "Validation/native_candidate_reload_runs/$id"
New-Item -ItemType Directory -Path $dir|Out-Null
$report=Join-Path $dir 'ue_native_saved_reload.json';$log=Join-Path $dir 'UnrealEditor-Cmd.log'
$argsLine=@(('"'+$hostProject+'"'),'-run=pythonscript',('-script="'+$script+'"'),'-unattended','-NullRHI','-nosplash','-nosound','-nop4','-NoCrashDialog','-UTF8Output','-stdout','-FullStdOutLogOutput',('-abslog="'+$log+'"'),'-ini:Engine:[/Script/EngineSettings.GameMapsSettings]:GlobalDefaultGameMode=/Script/Engine.GameModeBase')-join' '
@{run_id=$id;input_report=$inputPath;exe=$exe;arguments=$argsLine}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $dir 'request.json') -Encoding utf8
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$exe;$info.Arguments=$argsLine;$info.WorkingDirectory=$root;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.WindowStyle=[Diagnostics.ProcessWindowStyle]::Hidden
$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
$info.StandardOutputEncoding=[Text.UTF8Encoding]::new($false);$info.StandardErrorEncoding=[Text.UTF8Encoding]::new($false)
$info.Environment['T3B_NATIVE_RUN_ID']=$id;$info.Environment['T3B_NATIVE_REPORT_PATH']=$report;$info.Environment['T3B_NATIVE_SAVED_REPORT']=$inputPath
$p=[Diagnostics.Process]::new();$p.StartInfo=$info
Write-Output "Starting hidden read-only saved-native reload $id"
if(-not $p.Start()){throw 'Could not start explicit UE commandlet.'}
$o=$p.StandardOutput.ReadToEndAsync();$e=$p.StandardError.ReadToEndAsync()
if(-not $p.WaitForExit(1200000)){$p.Kill($true);$p.WaitForExit();throw "Reload timed out; diagnostics: $dir"}
[IO.File]::WriteAllText((Join-Path $dir 'stdout.log'),$o.GetAwaiter().GetResult(),[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $dir 'stderr.log'),$e.GetAwaiter().GetResult(),[Text.UTF8Encoding]::new($false))
if($p.ExitCode-ne0){throw "Native reload exit=$($p.ExitCode); diagnostics: $dir"}
$r=Get-Content -LiteralPath $report -Raw -Encoding UTF8|ConvertFrom-Json
if(-not$r.passed-or$r.run_id-ne$id-or$r.process_id-ne$p.Id-or$r.script_sha256-ne(Get-FileHash -LiteralPath $script -Algorithm SHA256).Hash.ToLowerInvariant()){throw 'Fresh read-only reload report identity/check differs.'}
@{passed=$true;run_id=$id;process_id=$p.Id;exit_code=$p.ExitCode;source_report=$report;source_report_sha256=(Get-FileHash -LiteralPath $report -Algorithm SHA256).Hash.ToLowerInvariant();asset_writes_performed=$false;ue_render_verified=$false}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $dir 'verified.json') -Encoding utf8
Write-Output "Native saved reload passed: $dir/verified.json"