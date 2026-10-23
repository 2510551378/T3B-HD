#requires -Version 7.2
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$EngineRoot,[Parameter(Mandatory=$true)][string]$ImportReport)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$inputPath=(Resolve-Path -LiteralPath $ImportReport).Path
$enginePath=(Resolve-Path -LiteralPath $EngineRoot).Path
$exe=Join-Path $enginePath 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
$hostProject=Join-Path $projectRoot 'T3BNativeProbe.uproject'
$script=Join-Path $PSScriptRoot 'probe_aya_render_data.py'
foreach($path in @($inputPath,$exe,$hostProject,$script)){
    if(-not(Test-Path -LiteralPath $path -PathType Leaf)-or $path.Contains('"')-or $path.Contains("`n")){throw 'Invalid explicit input path.'}
}
$id=[guid]::NewGuid().ToString('N')
$dir=Join-Path $projectRoot "Validation/native_render_data_runs/$id"
New-Item -ItemType Directory -Path $dir|Out-Null
Copy-Item -LiteralPath $script -Destination (Join-Path $dir 'probe_aya_render_data_executed.py')
$report=Join-Path $dir 'ue_render_data_probe.json'
$log=Join-Path $dir 'UnrealEditor-Cmd.log'
$arguments=@(('"'+$hostProject+'"'),'-run=pythonscript',('-script="'+$script+'"'),'-unattended','-AllowCommandletRendering','-RenderOffScreen','-d3d11','-nosplash','-nosound','-nop4','-NoCrashDialog','-UTF8Output','-stdout','-FullStdOutLogOutput',('-abslog="'+$log+'"'),'-ini:Engine:[/Script/EngineSettings.GameMapsSettings]:GlobalDefaultGameMode=/Script/Engine.GameModeBase')-join' '
@{run_id=$id;input_report=$inputPath;exe=$exe;arguments=$arguments;script_sha256=(Get-FileHash -LiteralPath $script -Algorithm SHA256).Hash.ToLowerInvariant();desktop_automation=$false}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $dir 'request.json') -Encoding utf8
$info=[Diagnostics.ProcessStartInfo]::new()
$info.FileName=$exe;$info.Arguments=$arguments;$info.WorkingDirectory=$projectRoot
$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.WindowStyle=[Diagnostics.ProcessWindowStyle]::Hidden
$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
$info.StandardOutputEncoding=[Text.UTF8Encoding]::new($false);$info.StandardErrorEncoding=[Text.UTF8Encoding]::new($false)
$info.Environment['T3B_RENDER_DATA_RUN_ID']=$id
$info.Environment['T3B_RENDER_DATA_REPORT']=$report
$info.Environment['T3B_RENDER_DATA_IMPORT_REPORT']=$inputPath
$process=[Diagnostics.Process]::new();$process.StartInfo=$info
if(-not $process.Start()){throw 'Could not start explicit offscreen commandlet.'}
Write-Output "Hidden offscreen RenderData probe run=$id PID=$($process.Id)"
$stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
if(-not $process.WaitForExit(1200000)){$process.Kill($true);$process.WaitForExit();throw "Probe timed out: $dir"}
[IO.File]::WriteAllText((Join-Path $dir 'stdout.log'),$stdout.GetAwaiter().GetResult(),[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $dir 'stderr.log'),$stderr.GetAwaiter().GetResult(),[Text.UTF8Encoding]::new($false))
if($process.ExitCode-ne0){throw "RenderData probe exit=$($process.ExitCode); diagnostics: $dir"}
$result=Get-Content -LiteralPath $report -Raw -Encoding UTF8|ConvertFrom-Json
if(-not$result.passed-or$result.run_id-ne$id-or$result.process_id-ne$process.Id-or$result.script_sha256-ne(Get-FileHash -LiteralPath $script -Algorithm SHA256).Hash.ToLowerInvariant()){throw 'Fresh RenderData probe report identity/check differs.'}
@{passed=$true;acceptance_scope='RenderData CPU-to-DynamicMesh data acquisition only';run_id=$id;process_id=$process.Id;exit_code=$process.ExitCode;report=$report;report_sha256=(Get-FileHash -LiteralPath $report -Algorithm SHA256).Hash.ToLowerInvariant();topology_fidelity_verified=$false;rendered_pixels_verified=$false;GPU_skinned_vertices_read=$false}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $dir 'verified.json') -Encoding utf8
Write-Output "RenderData probe passed: $dir/verified.json"
