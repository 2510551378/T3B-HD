# menu_click.ps1 -- drive PPSSPP's menu bar with posted mouse messages (no focus needed).
#
#   powershell -File tools\menu_click.ps1 -X 120 -Y 8
#   powershell -File tools\menu_click.ps1 -Xs "20,70,120,175,230" -Y 8 -Probe
param(
  [int[]]$Xs = @(20, 70, 120, 175, 230),
  [int]$Y = 8,
  [switch]$Probe,
  [string]$Root = "C:\Users\25105\Documents\PSP_RUN"
)
$ErrorActionPreference = 'Stop'
$sig = 'using System;using System.Runtime.InteropServices;' +
       'public class MC {' +
       '[DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);' +
       '}'
Add-Type -TypeDefinition $sig
$p = Get-Process | Where-Object { $_.ProcessName -like "PPSSPP*" } | Select-Object -First 1
$h = $p.MainWindowHandle
$shot = Join-Path $Root "work\psp_parse\out\preview"

function Click([int]$x, [int]$y) {
  $lp = [IntPtr](($y -shl 16) -bor ($x -band 0xFFFF))
  [void][MC]::PostMessage($h, 0x0201, [IntPtr]0x0001, $lp)   # WM_LBUTTONDOWN
  Start-Sleep -Milliseconds 90
  [void][MC]::PostMessage($h, 0x0202, [IntPtr]0, $lp)        # WM_LBUTTONUP
  Start-Sleep -Milliseconds 600
}

foreach ($x in $Xs) {
  Click $x $Y
  $png = Join-Path $shot ("m_{0}.png" -f $x)
  & (Join-Path $Root "work\psp_parse\tools\win_capture.ps1") -Out $png | Out-Null
  "== x=$x"
  $boxes = & (Join-Path $Root "work\psp_parse\tools\ocr_boxes.ps1") -Path $png
  $rows = @()
  foreach ($b in $boxes) {
    $f = $b -split "`t"
    if ($f.Count -ge 5 -and [int]$f[1] -gt 45) { $rows += ("   y={0,3} x={1,3}  {2}" -f $f[1], $f[0], $f[4]) }
  }
  if ($rows.Count -eq 0) { "   (nothing below the menu bar)" } else { $rows | Select-Object -First 14 }
  # close the menu
  Click 5 300
  [void][MC]::PostMessage($h, 0x100, [IntPtr]0x1B, [IntPtr]1)
  Start-Sleep -Milliseconds 80
  [void][MC]::PostMessage($h, 0x101, [IntPtr]0x1B, [IntPtr]0xC0000001)
  Start-Sleep -Milliseconds 400
}
