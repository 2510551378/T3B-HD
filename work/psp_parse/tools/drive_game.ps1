# drive_game.ps1 -- push the running PPSSPP forward and report what the screen says.
#
#   powershell -File tools\drive_game.ps1 -Steps 6 -Key 0x5A
param(
  [int]$Steps = 6,
  [int]$Key = 0x5A,
  [string]$Root = "C:\Users\25105\Documents\寄生前夜第四日"
)
$ErrorActionPreference = 'Stop'
Add-Type @"
using System;using System.Runtime.InteropServices;
public class DG {
 [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
}
"@
$p = Get-Process | Where-Object { $_.ProcessName -like "PPSSPP*" } | Select-Object -First 1
if (-not $p) { "PPSSPP not running"; exit 1 }
$h = $p.MainWindowHandle
$shot = Join-Path $Root "work\psp_parse\out\preview"

function Tap([int]$k) {
  [void][DG]::PostMessage($h, 0x100, [IntPtr]$k, [IntPtr]1)
  Start-Sleep -Milliseconds 120
  [void][DG]::PostMessage($h, 0x101, [IntPtr]$k, [IntPtr]0xC0000001)
}

for ($i = 0; $i -lt $Steps; $i++) {
  Tap $Key
  Start-Sleep -Seconds 3
  $png = Join-Path $shot ("drive{0}.png" -f $i)
  & (Join-Path $Root "work\psp_parse\tools\win_capture.ps1") -Out $png | Out-Null
  $big = Join-Path $shot ("drive{0}_big.png" -f $i)
  $py = "from PIL import Image; im=Image.open(r'$png'); w,h=im.size; im.crop((0,50,w,h)).resize((w*2,(h-50)*2), Image.LANCZOS).save(r'$big')"
  python -c $py
  $txt = (& (Join-Path $Root "work\psp_parse\tools\ocr_boxes.ps1") -Path $big) -join ' '
  $words = (($txt -split "`t") | Where-Object { $_ -match '[\u4e00-\u9fff]' }) -join ''
  "step $i : $words"
}
