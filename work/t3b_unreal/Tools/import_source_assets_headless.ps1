#requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$EngineRoot,
    [ValidateRange(1,120)][int]$TimeoutMinutes=45,
    [switch]$ValidateOnly
)
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
$projectRoot=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$hostProject=Join-Path $projectRoot 'T3BAssetImport.uproject'
$importScript=Join-Path $PSScriptRoot 'editor_build_source_assets.py'
$sourceManifest=Join-Path $projectRoot 'Content\SourceData\manifest.json'
$engineDirectory=(Resolve-Path -LiteralPath $EngineRoot -ErrorAction Stop).Path
$editorCommand=Join-Path $engineDirectory 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$versionFile=Join-Path $engineDirectory 'Engine\Build\Build.version'
foreach($requiredFile in @($hostProject,$importScript,$sourceManifest,$editorCommand,$versionFile)){
    if(-not(Test-Path -LiteralPath $requiredFile -PathType Leaf)){throw "Required file missing: $requiredFile"}
    if($requiredFile.Contains('"') -or $requiredFile.Contains("`n") -or $requiredFile.Contains("`r")){throw 'Unsafe quoted/newline file path.'}
}
$version=Get-Content -LiteralPath $versionFile -Encoding UTF8 -Raw | ConvertFrom-Json
if($version.MajorVersion -ne 5 -or $version.MinorVersion -ne 8){throw 'This host requires the explicitly selected UE5.8 installation.'}
$hostDescription=Get-Content -LiteralPath $hostProject -Encoding UTF8 -Raw | ConvertFrom-Json
if($hostDescription.PSObject.Properties.Name -contains 'Modules'){throw 'Asset-import host must remain content-only with no Modules field.'}
$manifest=Get-Content -LiteralPath $sourceManifest -Encoding UTF8 -Raw | ConvertFrom-Json
if($manifest.schema -ne 't3b-ue-source-bundle/v1'){throw 'Unsupported source bundle schema.'}
$textureCount=@($manifest.textures).Count
$materialEntries=@($manifest.scene.materials)+@($manifest.actors | ForEach-Object {$_.materials})
$materialCount=$materialEntries.Count
if($textureCount -ne 76 -or $materialCount -ne 84){throw "Expected current76textures84materials; got $textureCount textures and $materialCount materials. Review source bundle before importing."}
$manifestHash=(Get-FileHash -LiteralPath $sourceManifest -Algorithm SHA256).Hash.ToLowerInvariant()
$scriptHash=(Get-FileHash -LiteralPath $importScript -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output "Validated content-only UE $($version.MajorVersion).$($version.MinorVersion).$($version.PatchVersion) asset host,76 textures84 materials; no C++ build or gameplay is requested."
if($ValidateOnly){Write-Output 'Validation only: UnrealEditor-Cmd was not started.';return}

$runId=[guid]::NewGuid().ToString('N')
$runDirectory=Join-Path $projectRoot "Validation\asset_import_runs\$runId"
New-Item -ItemType Directory -Path $runDirectory -ErrorAction Stop | Out-Null
$reportPath=Join-Path $runDirectory 'ue_editor_asset_creation.json'
$engineLog=Join-Path $runDirectory 'UnrealEditor-Cmd.log'
$stdoutPath=Join-Path $runDirectory 'stdout.log'
$stderrPath=Join-Path $runDirectory 'stderr.log'
# ProcessStartInfo invokes the CLI executable directly, with no shell. Keep
# -Script="..." as required by the installed commandlet's manual parser.
$arguments=@(('"'+$hostProject+'"'),'-run=pythonscript',('-script="'+$importScript+'"'),
    '-unattended','-NullRHI','-nosplash','-nosound','-nop4','-NoCrashDialog',
    '-UTF8Output','-stdout','-FullStdOutLogOutput',('-abslog="'+$engineLog+'"'),
    '-ini:Engine:[/Script/EngineSettings.GameMapsSettings]:GlobalDefaultGameMode=/Script/Engine.GameModeBase') -join ' '
$request=@{schema='t3b-ue-headless-asset-import-request/v1';run_id=$runId;requested_utc=[datetime]::UtcNow.ToString('o');
    engine_root=$engineDirectory;engine_version=$version;host_project=$hostProject;importer=$importScript;
    importer_sha256=$scriptHash;manifest_sha256=$manifestHash;expected_textures=$textureCount;expected_materials=$materialCount;
    report=$reportPath;executable=$editorCommand;arguments=$arguments;mode='headless content assets only; no C++ build/gameplay'}
$request | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $runDirectory 'request.json') -Encoding utf8
$startInfo=[System.Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName=$editorCommand
$startInfo.Arguments=$arguments
$startInfo.WorkingDirectory=$projectRoot
$startInfo.UseShellExecute=$false
$startInfo.CreateNoWindow=$true
$startInfo.WindowStyle=[System.Diagnostics.ProcessWindowStyle]::Hidden
$startInfo.RedirectStandardOutput=$true
$startInfo.RedirectStandardError=$true
$startInfo.StandardOutputEncoding=[System.Text.UTF8Encoding]::new($false)
$startInfo.StandardErrorEncoding=[System.Text.UTF8Encoding]::new($false)
$startInfo.Environment['T3B_EDITOR_RUN_ID']=$runId
$startInfo.Environment['T3B_EDITOR_REPORT_PATH']=$reportPath
$process=[System.Diagnostics.Process]::new()
$process.StartInfo=$startInfo
$startedUtc=[datetime]::UtcNow
Write-Output "Starting unattended NullRHI asset commandlet run_id=$runId; logs/report: $runDirectory"
if(-not $process.Start()){throw 'UnrealEditor-Cmd process could not be started.'}
$processId=$process.Id
$outputRead=$process.StandardOutput.ReadToEndAsync()
$errorRead=$process.StandardError.ReadToEndAsync()
if(-not $process.WaitForExit($TimeoutMinutes*60000)){
    $process.Kill($true);$process.WaitForExit()
    [System.IO.File]::WriteAllText($stdoutPath,$outputRead.GetAwaiter().GetResult(),[System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllText($stderrPath,$errorRead.GetAwaiter().GetResult(),[System.Text.UTF8Encoding]::new($false))
    throw "Asset commandlet timed out after $TimeoutMinutes minutes; inspect $runDirectory. No game build/runtime success is implied."
}
[System.IO.File]::WriteAllText($stdoutPath,$outputRead.GetAwaiter().GetResult(),[System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($stderrPath,$errorRead.GetAwaiter().GetResult(),[System.Text.UTF8Encoding]::new($false))
$exitCode=$process.ExitCode
if($exitCode -ne 0){throw "Unreal asset commandlet failed exit=$exitCode; inspect $runDirectory. C++ SDK/build is a separate requirement."}
if(-not(Test-Path -LiteralPath $reportPath -PathType Leaf)){throw "Commandlet returned0 but produced no fresh report: $reportPath"}
$report=Get-Content -LiteralPath $reportPath -Encoding UTF8 -Raw | ConvertFrom-Json
if($report.schema -ne 't3b-ue-editor-asset-creation/v1' -or $report.run_id -ne $runId -or $report.process_id -ne $processId){throw 'Asset report schema/run_id/PID mismatch; stale or unrelated reports are not accepted.'}
if((Get-Item -LiteralPath $reportPath).LastWriteTimeUtc -lt $startedUtc.AddSeconds(-2)){throw 'Asset report timestamp precedes this commandlet run.'}
if(-not $report.asset_creation_completed -or -not $report.headless_asset_creation_only){throw 'Fresh report does not confirm completed content-only asset creation.'}
if($report.ue_cpp_build_executed -or $report.ue_gameplay_executed -or $report.ue_render_verified){throw 'Asset-only report improperly claims build/gameplay/render acceptance.'}
if([System.IO.Path]::GetFullPath($report.project_file) -ne [System.IO.Path]::GetFullPath($hostProject)){throw 'Asset report belongs to a different project host.'}
if($report.engine_version -notlike '5.8.*' -or $report.command_line -notmatch '(?i)-run=pythonscript' -or $report.command_line -notmatch '(?i)-NullRHI' -or $report.command_line -notmatch '(?i)-unattended'){throw 'Fresh engine report does not identify the requested UE5.8 headless Python commandlet mode.'}
if($report.manifest_sha256 -ne $manifestHash -or $report.script_sha256 -ne $scriptHash){throw 'Asset report input/script identities differ from requested run.'}
if((Get-FileHash -LiteralPath $sourceManifest -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifestHash){throw 'Manifest changed during import; report cannot establish the requested asset set.'}
if($report.textures -ne $textureCount -or $report.materials -ne $materialCount -or $report.map -ne '/Game/T3B/Maps/M1_SourceReplay'){throw 'Fresh report asset counts/map differ from expected source bundle.'}
$expectedObjects=@($manifest.textures | ForEach-Object {$_.asset})+@($materialEntries | ForEach-Object {$_.asset})+@('/Game/T3B/Maps/M1_SourceReplay.M1_SourceReplay')
$actualObjects=@($report.saved_assets | ForEach-Object {$_.object_path})
if($actualObjects.Count -ne 161 -or @(Compare-Object ($expectedObjects | Sort-Object) ($actualObjects | Sort-Object)).Count -ne 0){throw 'Saved-asset report does not contain the exact76+84+1 package set.'}
$contentRoot=[System.IO.Path]::GetFullPath((Join-Path $projectRoot 'Content'))+[System.IO.Path]::DirectorySeparatorChar
foreach($saved in $report.saved_assets){
    $savedPath=[System.IO.Path]::GetFullPath($saved.file)
    if(-not $savedPath.StartsWith($contentRoot,[System.StringComparison]::OrdinalIgnoreCase)){throw "Saved package outside shared Content: $savedPath"}
    if(-not(Test-Path -LiteralPath $savedPath -PathType Leaf)){throw "Reported saved package missing: $savedPath"}
    if((Get-Item -LiteralPath $savedPath).Length -ne $saved.bytes -or (Get-FileHash -LiteralPath $savedPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $saved.sha256){throw "Saved package identity mismatch: $savedPath"}
}
$verified=@{schema='t3b-ue-headless-asset-import-verification/v1';passed=$true;run_id=$runId;process_id=$processId;exit_code=$exitCode;
    verified_utc=[datetime]::UtcNow.ToString('o');source_report=$reportPath;textures=$textureCount;materials=$materialCount;map=$report.map;
    saved_packages_verified=161;headless_asset_creation_only=$true;ue_cpp_build_executed=$false;ue_gameplay_executed=$false;ue_render_verified=$false;
    unsupported_render_states=$report.unsupported_render_states}
$verifiedPath=Join-Path $runDirectory 'verified.json'
$verified | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $verifiedPath -Encoding utf8
Write-Output "Headless content creation verified:76 textures84 materials1 empty map. Report: $verifiedPath"
Write-Output 'C++ compilation, source replay runtime, shaders/pixels and gameplay remain separate unverified stages.'
