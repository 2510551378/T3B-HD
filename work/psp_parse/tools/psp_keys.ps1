# psp_keys.ps1 -- inject keystrokes straight into PPSSPP with PostMessage (no focus needed).
#
#   powershell -File tools\psp_keys.ps1 -Keys "x,z,{ENTER}" [-Delay 1200]
#
# Each element is a key name understood by the small table below; after each key a
# framebuffer screenshot is taken (F12) and OCR'd so the caller sees the result.
param(
  [string]$Keys = "z",
  [int]$Delay = 1500,
  [switch]$NoShot,
  [string]$Root = "C:\Users\25105\Documents\PSP_RUN"
)
$ErrorActionPreference = 'Stop'
$sig = 'using System;using System.Runtime.InteropServices;' +
       'public class PK {' +
       '[DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);' +
       '}'
Add-Type -TypeDefinition $sig

$proc = Get-Process | Where-Object { $_.ProcessName -like "PPSSPP*" } | Select-Object -First 1
if (-not $proc) { throw "PPSSPP not running" }
$h = $proc.MainWindowHandle

$vk = @{
  'z' = 0x5A; 'x' = 0x58; 'a' = 0x41; 's' = 0x53; 'c' = 0x43
  'enter' = 0x0D; 'esc' = 0x1B; 'space' = 0x20
  'up' = 0x26; 'down' = 0x28; 'left' = 0x25; 'right' = 0x27
  'f5' = 0x74; 'f8' = 0x77; 'f12' = 0x7B
}

function Tap([int]$code) {
  [void][PK]::PostMessage($h, 0x100, [IntPtr]$code, [IntPtr]0x00000001)
  Start-Sleep -Milliseconds 90
  [void][PK]::PostMessage($h, 0x101, [IntPtr]$code, [IntPtr]0xC0000001)
  Start-Sleep -Milliseconds 120
}

function Snap([string]$tag) {
  Tap 0x7B
  Start-Sleep -Seconds 2
  $f = Get-ChildItem (Join-Path $Root 'PSP\memstick\PSP\SCREENSHOT\*.jpg') | Sort-Object LastWriteTime | Select-Object -Last 1
  $txt = & (Join-Path $Root 'work\psp_parse\tools\ocr_psp.ps1') -Path $f.FullName
  $line = (($txt | Where-Object { $_ -ne '' }) -join ' / ')
  "  [$tag] $($f.Name) :: $line"
}

foreach ($k in $Keys.Split(',')) {
  $name = $k.Trim().Trim('{','}').ToLower()
  if (-not $vk.ContainsKey($name)) { "  ? unknown key $k"; continue }
  Tap $vk[$name]
  Start-Sleep -Milliseconds $Delay
  if (-not $NoShot) { Snap "after $name" }
}
