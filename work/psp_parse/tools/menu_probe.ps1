# menu_probe.ps1 -- click along PPSSPP's menu bar and OCR whatever drops down.
#
#   powershell -File tools\menu_probe.ps1 -Xs "20,70,125,178,230"
param(
  [string]$Xs = "20,70,125,178,230",
  [int]$Y = 40,
  [string]$Root = "C:\Users\25105\Documents\PSP_RUN"
)
$ErrorActionPreference = 'Stop'
$sig = 'using System;using System.Runtime.InteropServices;' +
       'public class MP {' +
       '[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);' +
       '[DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);' +
       '[DllImport("user32.dll")] public static extern void mouse_event(uint f,uint dx,uint dy,uint d,IntPtr e);' +
       '[DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);' +
       '[StructLayout(LayoutKind.Sequential)] public struct RECT { public int L; public int T; public int R; public int B; }' +
       '}'
Add-Type -TypeDefinition $sig
$p = Get-Process | Where-Object { $_.ProcessName -like "PPSSPP*" } | Select-Object -First 1
$r = New-Object MP+RECT
[void][MP]::GetWindowRect($p.MainWindowHandle, [ref]$r)
$shot = Join-Path $Root "work\psp_parse\out\preview"
New-Item -ItemType Directory -Force -Path $shot | Out-Null

function ClickAt([int]$x, [int]$y) {
  [void][MP]::SetCursorPos($r.L + $x, $r.T + $y)
  Start-Sleep -Milliseconds 250
  [MP]::mouse_event(0x0002, 0, 0, 0, [IntPtr]::Zero)
  Start-Sleep -Milliseconds 80
  [MP]::mouse_event(0x0004, 0, 0, 0, [IntPtr]::Zero)
  Start-Sleep -Milliseconds 700
}

foreach ($x in $Xs.Split(',')) {
  $xi = [int]$x
  ClickAt $xi $Y
  $png = Join-Path $shot ("menu_x{0}.png" -f $xi)
  & (Join-Path $Root "work\psp_parse\tools\win_capture.ps1") -Out $png -ProcessName PPSSPP | Out-Null
  "== clicked x=$xi"
  $boxes = & (Join-Path $Root "work\psp_parse\tools\ocr_boxes.ps1") -Path $png
  $boxes | Where-Object { $_ -match '^\d+\t(\d+)\t' -and [int]($_ -split "`t")[1] -gt 50 } |
    ForEach-Object { $f = $_ -split "`t"; "   y=$($f[1]) x=$($f[0])  $($f[4])" }
  # close whatever opened
  [void][MP]::PostMessage($p.MainWindowHandle, 0x100, [IntPtr]0x1B, [IntPtr]1)
  Start-Sleep -Milliseconds 80
  [void][MP]::PostMessage($p.MainWindowHandle, 0x101, [IntPtr]0x1B, [IntPtr]0xC0000001)
  Start-Sleep -Milliseconds 500
}
