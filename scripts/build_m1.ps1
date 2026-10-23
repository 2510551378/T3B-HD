[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$SDL2Root,
    [string]$Compiler='gcc'
)
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
$repoRoot=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$projectRoot=Join-Path $repoRoot 'work\t3b_hd'
$sdlDirectory=(Resolve-Path -LiteralPath $SDL2Root).Path
foreach($relative in @('include\SDL2\SDL.h','lib\libSDL2.dll.a','bin\SDL2.dll')) {
    if(-not(Test-Path -LiteralPath (Join-Path $sdlDirectory $relative) -PathType Leaf)) {
        throw "SDL2 MinGW x64 development file missing: $relative"
    }
}
$compilerPath=(Get-Command $Compiler -CommandType Application -ErrorAction Stop).Source
$target=& $compilerPath -dumpmachine
if($LASTEXITCODE -ne 0 -or $target -notmatch 'x86_64.*mingw') {
    throw "Expected a Windows x64 MinGW compiler; observed: $target"
}
$outputFile=Join-Path $projectRoot 't3b_hd.exe'
$sourceFile=Join-Path $projectRoot 'src\m1_main.c'
& $compilerPath -O2 -Wall -Wextra -std=c11 -D_MINGW32 -DSDL_MAIN_HANDLED "-I$sdlDirectory/include/SDL2" -o $outputFile $sourceFile "-L$sdlDirectory/lib" -lSDL2 -lopengl32 -lm
if($LASTEXITCODE -ne 0){throw "M1 compile failed: $LASTEXITCODE"}
Copy-Item -LiteralPath (Join-Path $sdlDirectory 'bin\SDL2.dll') -Destination (Join-Path $projectRoot 'SDL2.dll') -Force
Write-Output "Built $outputFile. Runtime assets and visual checks are separate."
