#requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$EngineRoot,
    [Parameter(Mandatory=$true)][string]$ImportReport,
    [Parameter(Mandatory=$true)][string]$SkinningReport,
    [Parameter(Mandatory=$true)][string]$FullUVReport
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$enginePath=(Resolve-Path -LiteralPath $EngineRoot).Path
$inputPath=(Resolve-Path -LiteralPath $ImportReport).Path
$skinningPath=(Resolve-Path -LiteralPath $SkinningReport).Path
$fullUVPath=(Resolve-Path -LiteralPath $FullUVReport).Path
$exe=Join-Path $enginePath 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
$project=Join-Path $projectRoot 'T3BNativeProbe.uproject'
$script=Join-Path $PSScriptRoot 'capture_aya_cull_comparison.py'
foreach($item in @($exe,$project,$script,$inputPath,$skinningPath,$fullUVPath)){
    if(-not(Test-Path -LiteralPath $item -PathType Leaf)-or$item.Contains('"')-or$item.Contains("`n")){throw 'Invalid explicit input path.'}
}
$id=[guid]::NewGuid().ToString('N')
$dir=Join-Path $projectRoot "Validation/native_cull_comparison_runs/$id"
New-Item -ItemType Directory -Path $dir|Out-Null
$executed=Join-Path $dir 'capture_aya_cull_comparison_executed.py'
Copy-Item -LiteralPath $script -Destination $executed
$report=Join-Path $dir 'ue_aya_cull_comparison.json'
$log=Join-Path $dir 'UnrealEditor-Cmd.log'
$arguments=@(('"'+$project+'"'),'-run=pythonscript',('-script="'+$executed+'"'),'-unattended','-AllowCommandletRendering','-RenderOffScreen','-d3d11','-nosplash','-nosound','-nop4','-NoCrashDialog','-UTF8Output','-stdout','-FullStdOutLogOutput',('-abslog="'+$log+'"'),'-ini:Engine:[/Script/EngineSettings.GameMapsSettings]:GlobalDefaultGameMode=/Script/Engine.GameModeBase')-join' '
$scriptSHA=(Get-FileHash -LiteralPath $executed -Algorithm SHA256).Hash.ToLowerInvariant()
@{run_id=$id;exe=$exe;arguments=$arguments;script_sha256=$scriptSHA;import_report=$inputPath;skinning_report=$skinningPath;full_uv_report=$fullUVPath;desktop_automation=$false;null_rhi=$false;timeout_kill=$false}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $dir 'request.json') -Encoding utf8
$info=[Diagnostics.ProcessStartInfo]::new()
$info.FileName=$exe;$info.Arguments=$arguments;$info.WorkingDirectory=$projectRoot
$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.WindowStyle=[Diagnostics.ProcessWindowStyle]::Hidden
$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
$info.StandardOutputEncoding=[Text.UTF8Encoding]::new($false);$info.StandardErrorEncoding=[Text.UTF8Encoding]::new($false)
$info.Environment['T3B_AYA_CAPTURE_RUN_ID']=$id
$info.Environment['T3B_AYA_CAPTURE_REPORT']=$report
$info.Environment['T3B_AYA_CAPTURE_IMPORT']=$inputPath
$info.Environment['T3B_AYA_CAPTURE_SKINNING']=$skinningPath
$info.Environment['T3B_AYA_CAPTURE_FULLUV']=$fullUVPath
$process=[Diagnostics.Process]::new();$process.StartInfo=$info
if(-not$process.Start()){throw 'Could not start explicit offscreen capture.'}
@{run_id=$id;process_id=$process.Id;started_utc=[DateTime]::UtcNow.ToString('o');exe=$exe;run_directory=$dir;kill_on_timeout=$false}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $dir 'live_process.json') -Encoding utf8
Write-Output "Hidden SceneCapture2D run=$id PID=$($process.Id) dir=$dir"
$stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
$lastNotice=[DateTime]::UtcNow
while(-not$process.WaitForExit(1000)){
    if(([DateTime]::UtcNow-$lastNotice).TotalSeconds-ge30){
        $lastNotice=[DateTime]::UtcNow
        Write-Output "Still live PID=$($process.Id); waiting without restart/kill; log=$log"
    }
}
[IO.File]::WriteAllText((Join-Path $dir 'stdout.log'),$stdout.GetAwaiter().GetResult(),[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $dir 'stderr.log'),$stderr.GetAwaiter().GetResult(),[Text.UTF8Encoding]::new($false))
@{run_id=$id;process_id=$process.Id;exit_code=$process.ExitCode;finished_utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $dir 'process_completed.json') -Encoding utf8
if($process.ExitCode-ne0){throw "Culling A/B process exit=$($process.ExitCode); failed images/diagnostics preserved: $dir"}
$result=Get-Content -LiteralPath $report -Raw -Encoding UTF8|ConvertFrom-Json
if(-not$result.passed-or$result.run_id-ne$id-or$result.process_id-ne$process.Id-or$result.script_sha256-ne$scriptSHA-or-not$result.all_original_packages_unchanged){throw "Offscreen report identity/foreground/package check failed; retained: $dir"}
foreach($originalPackage in $result.protected_packages_before){
    if(-not(Test-Path -LiteralPath $originalPackage.file -PathType Leaf)-or(Get-FileHash -LiteralPath $originalPackage.file -Algorithm SHA256).Hash.ToLowerInvariant()-ne$originalPackage.sha256){throw "Original package changed after process exit: $($originalPackage.file)"}
}
@{passed=$true;scope='Same-process FullUV Aya controlled TwoSided A/B acquisition; visual result separately reviewed';run_id=$id;process_id=$process.Id;report=$report;report_sha256=(Get-FileHash -LiteralPath $report -Algorithm SHA256).Hash.ToLowerInvariant();original_pixel_equivalence_verified=$false;HD_verified=$false;gameplay_verified=$false;packages_unchanged=$true;original_package_hashes_checked_after_process=$result.protected_packages_before.Count}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $dir 'verified.json') -Encoding utf8
Write-Output "Actual controlled A/B acquisition passed: $dir/verified.json"
