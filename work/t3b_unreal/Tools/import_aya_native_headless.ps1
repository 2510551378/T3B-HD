#requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$EngineRoot,
    [ValidateRange(1,120)][int]$TimeoutMinutes=30,
    [string]$CandidateManifest,
    [switch]$ValidateOnly
)
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
$projectRoot=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$hostProject=Join-Path $projectRoot 'T3BNativeImport.uproject'
$script=Join-Path $PSScriptRoot 'import_aya_native_candidate.py'
$gltf=[System.IO.Path]::GetFullPath((Join-Path $projectRoot '..\psp_parse\out\AYA_NATIVE_GLTF_20261020\aya_native.gltf'))
$expectedGltf='93c78d4014a2255b15915f8150868d1654718b256a72995f25966581a578a4f7'
$expectedBin='8ce1805dcaf6cdb8f73c0d2d2784a8d20f0e611fbb2d144d0a2d025d839d8454'
$candidateKind='original';$candidateNamespace='Aya'
if($CandidateManifest){
    $manifestPath=(Resolve-Path -LiteralPath $CandidateManifest).Path
    $candidate=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8|ConvertFrom-Json
    if($candidate.schema-ne't3b-native-compact-candidate/v1'-or$candidate.source_gltf_sha256-ne$expectedGltf-or$candidate.source_bin_sha256-ne$expectedBin){throw 'Explicit compact candidate provenance differs.'}
    $gltf=Join-Path ([IO.Path]::GetDirectoryName($manifestPath)) 'aya_native.gltf'
    $expectedGltf=$candidate.gltf_sha256;$expectedBin=$candidate.bin_sha256;$candidateKind='compact';$candidateNamespace='AyaCompact'
}
$bin=Join-Path ([System.IO.Path]::GetDirectoryName($gltf)) 'aya_native.bin'
$engineDirectory=(Resolve-Path -LiteralPath $EngineRoot).Path
$executable=Join-Path $engineDirectory 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$versionPath=Join-Path $engineDirectory 'Engine\Build\Build.version'
foreach($file in @($hostProject,$script,$gltf,$bin,$executable,$versionPath)){
    if(-not(Test-Path -LiteralPath $file -PathType Leaf)){throw "Required native import file missing: $file"}
    if($file.Contains('"') -or $file.Contains("`r") -or $file.Contains("`n")){throw 'Quoted/newline command path rejected.'}
}
$version=Get-Content -LiteralPath $versionPath -Raw -Encoding UTF8 | ConvertFrom-Json
if($version.MajorVersion -ne 5 -or $version.MinorVersion -ne 8){throw 'Explicit UE5.8 installation required.'}
$gltfHash=(Get-FileHash -LiteralPath $gltf -Algorithm SHA256).Hash.ToLowerInvariant()
$binHash=(Get-FileHash -LiteralPath $bin -Algorithm SHA256).Hash.ToLowerInvariant()
if($gltfHash -ne $expectedGltf -or $binHash -ne $expectedBin){throw 'Frozen native glTF/bin identities changed.'}
$scriptHash=(Get-FileHash -LiteralPath $script -Algorithm SHA256).Hash.ToLowerInvariant()
$frozenReport=Join-Path $projectRoot 'Validation\asset_import_runs\0fac54502ca140d4accffa2e5a7bc618\ue_editor_asset_creation.json'
$frozen=Get-Content -LiteralPath $frozenReport -Raw -Encoding UTF8 | ConvertFrom-Json
foreach($asset in $frozen.saved_assets){if((Get-FileHash -LiteralPath $asset.file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $asset.sha256){throw "Existing verified asset changed: $($asset.file)"}}
Write-Output 'Validated frozen native glTF/bin and unchanged161 prior packages; isolated built-in Interchange import only.'
if($ValidateOnly){Write-Output 'Validation only: no UE process started.';return}
$runId=[guid]::NewGuid().ToString('N')
$directory=Join-Path $projectRoot "Validation\native_import_runs\$runId"
New-Item -ItemType Directory -Path $directory | Out-Null
$reportPath=Join-Path $directory 'ue_native_import.json'
$log=Join-Path $directory 'UnrealEditor-Cmd.log'
$arguments=@(('"'+$hostProject+'"'),'-run=pythonscript',('-script="'+$script+'"'),
    '-unattended','-NullRHI','-nosplash','-nosound','-nop4','-NoCrashDialog','-UTF8Output','-stdout','-FullStdOutLogOutput',
    ('-abslog="'+$log+'"'),'-ini:Engine:[/Script/EngineSettings.GameMapsSettings]:GlobalDefaultGameMode=/Script/Engine.GameModeBase') -join ' '
@{schema='t3b-native-import-request/v1';run_id=$runId;gltf=$gltf;gltf_sha256=$gltfHash;bin_sha256=$binHash;
    script_sha256=$scriptHash;executable=$executable;arguments=$arguments;candidate_kind=$candidateKind;destination="/Game/T3B/NativeCandidates/$candidateNamespace/Run_$runId";
    requested_utc=[datetime]::UtcNow.ToString('o')} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $directory 'request.json') -Encoding utf8
$info=[System.Diagnostics.ProcessStartInfo]::new()
$info.FileName=$executable;$info.Arguments=$arguments;$info.WorkingDirectory=$projectRoot
$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.WindowStyle=[System.Diagnostics.ProcessWindowStyle]::Hidden
$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
$info.StandardOutputEncoding=[System.Text.UTF8Encoding]::new($false);$info.StandardErrorEncoding=[System.Text.UTF8Encoding]::new($false)
$info.Environment['T3B_NATIVE_EXPECTED_GLTF']=$expectedGltf;$info.Environment['T3B_NATIVE_EXPECTED_BIN']=$expectedBin;$info.Environment['T3B_NATIVE_CANDIDATE_KIND']=$candidateKind;$info.Environment['T3B_NATIVE_RUN_ID']=$runId;$info.Environment['T3B_NATIVE_REPORT_PATH']=$reportPath;$info.Environment['T3B_NATIVE_GLTF']=$gltf
$process=[System.Diagnostics.Process]::new();$process.StartInfo=$info
Write-Output "Starting hidden native import run_id=$runId; logs/report: $directory"
if(-not $process.Start()){throw 'UnrealEditor-Cmd could not start.'}
$processId=$process.Id;$outputRead=$process.StandardOutput.ReadToEndAsync();$errorRead=$process.StandardError.ReadToEndAsync()
$timeout=-not $process.WaitForExit($TimeoutMinutes*60000)
if($timeout){$process.Kill($true);$process.WaitForExit()}
[System.IO.File]::WriteAllText((Join-Path $directory 'stdout.log'),$outputRead.GetAwaiter().GetResult(),[System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText((Join-Path $directory 'stderr.log'),$errorRead.GetAwaiter().GetResult(),[System.Text.UTF8Encoding]::new($false))
foreach($asset in $frozen.saved_assets){if((Get-FileHash -LiteralPath $asset.file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $asset.sha256){throw "Prior161package changed by native import: $($asset.file)"}}
if($timeout){throw "Native import timed out; partial assets and logs preserved: $directory"}
if($process.ExitCode -ne 0){throw "Native import commandlet exit=$($process.ExitCode); diagnostics/partial candidate preserved: $directory"}
if(-not(Test-Path -LiteralPath $reportPath -PathType Leaf)){throw 'Native import exit0 without fresh report.'}
$report=Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
if($report.run_id -ne $runId -or $report.process_id -ne $processId -or $report.import_script_sha256 -ne $scriptHash){throw 'Native report run_id/PID/script identity differs.'}
if(-not $report.verified_source_material_bound -or -not $report.native_import_completed -or -not $report.native_structure_verified -or -not $report.previous161_packages_unchanged -or -not $report.source_inputs_unchanged){throw 'Native classes/hierarchy/unchanged-source checks did not pass; inspect actual report.'}
if($report.UE_skinning_vertex_numeric_verified -or $report.ue_render_verified -or $report.ue_gameplay_executed -or $report.ue_cpp_build_executed -or $report.source_runtime_replaced){throw 'Candidate-only import report improperly claims runtime/numeric/render acceptance.'}
foreach($saved in $report.saved_native_packages){if((Get-FileHash -LiteralPath $saved.file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $saved.sha256){throw "Native saved package fingerprint differs: $($saved.file)"}}
$verified=@{schema='t3b-ue-native-gltf-import-verification/v1';passed=$true;run_id=$runId;process_id=$processId;exit_code=$process.ExitCode;
    source_report=$reportPath;source_report_sha256=(Get-FileHash -LiteralPath $reportPath -Algorithm SHA256).Hash.ToLowerInvariant();
    destination=$report.destination;native_class_counts=$report.native_class_counts;verified_source_material_bound=$report.verified_source_material_bound;previous161_packages_unchanged=$true;
    verified_utc=[datetime]::UtcNow.ToString('o');source_runtime_replaced=$false;UE_skinning_vertex_numeric_verified=$false;
    ue_render_verified=$false;ue_cpp_build_executed=$false;ue_gameplay_executed=$false}
$verifiedPath=Join-Path $directory 'verified.json';$verified | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $verifiedPath -Encoding utf8
Write-Output "Native candidate import and structural checks passed: $verifiedPath"
Write-Output 'Not accepted: imported skinning vertices, source render equivalence, gameplay or replacement of the existing PMC replay.'
