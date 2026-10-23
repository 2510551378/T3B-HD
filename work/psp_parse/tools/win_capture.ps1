# win_capture.ps1 -- copy a window's pixels with PrintWindow (works even when occluded),
# so the OCR helper can read what the emulator is showing.
#
#   powershell -File tools\win_capture.ps1 -Out shot.png [-ProcessName PPSSPP]
param(
  [string]$Out = "shot.png",
  [string]$ProcessName = "PPSSPP"
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$sig = 'using System;using System.Runtime.InteropServices;using System.Drawing;' +
       'public class WC {' +
       '[DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);' +
       '[DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);' +
       '[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);' +
       '[StructLayout(LayoutKind.Sequential)] public struct RECT { public int L; public int T; public int R; public int B; }' +
       '}'
Add-Type -TypeDefinition $sig

$p = Get-Process | Where-Object { $_.ProcessName -like "$ProcessName*" } | Select-Object -First 1
if (-not $p) { throw "process not running" }
$h = $p.MainWindowHandle
$r = New-Object WC+RECT
[void][WC]::GetWindowRect($h, [ref]$r)
$w = $r.R - $r.L
$ht = $r.B - $r.T
if ($w -le 0 -or $ht -le 0) { throw "window has no size" }
$bmp = New-Object System.Drawing.Bitmap $w, $ht
$g = [System.Drawing.Graphics]::FromImage($bmp)
$dc = $g.GetHdc()
$ok = [WC]::PrintWindow($h, $dc, 2)   # PW_RENDERFULLCONTENT
$g.ReleaseHdc($dc)
$g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
"captured ${w}x${ht} -> $Out (PrintWindow=$ok)"
