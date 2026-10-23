# read_psp_ram.ps1 -- dump PPSSPP's guest RAM straight out of the emulator process.
#
#   powershell -ExecutionPolicy Bypass -File tools\read_psp_ram.ps1 -Out raw\psp_ram.bin [-MinMB 16] [-MaxMB 64]
#
# PSP guest RAM is one 32 MiB block (VRAM 2 MiB, scratchpad 2 MiB).  We enumerate the
# process' committed regions, keep the big ones, and write each to <Out>.<n>.bin.
param(
  [string]$Out = "work\psp_parse\raw\psp_ram.bin",
  [int]$MinMB = 16,
  [int]$MaxMB = 80
)
$ErrorActionPreference = 'Stop'

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class VM {
  [DllImport("kernel32.dll")] public static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
  [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
  [DllImport("kernel32.dll")] public static extern IntPtr VirtualQueryEx(IntPtr h, IntPtr addr, out MEMORY_BASIC_INFORMATION64 mbi, IntPtr len);
  [DllImport("kernel32.dll")] public static extern bool ReadProcessMemory(IntPtr h, IntPtr addr, byte[] buf, IntPtr size, out IntPtr read);
  [StructLayout(LayoutKind.Sequential)] public struct MEMORY_BASIC_INFORMATION64 {
    public ulong BaseAddress; public ulong AllocationBase; public uint AllocationProtect;
    public uint __alignment1; public ulong RegionSize; public uint State; public uint Protect; public uint Type; public uint __alignment2;
  }
}
"@

$proc = Get-Process | Where-Object { $_.ProcessName -like "PPSSPP*" } | Select-Object -First 1
if (-not $proc) { throw "PPSSPP is not running" }
Write-Host "process: $($proc.ProcessName) pid=$($proc.Id)"

$h = [VM]::OpenProcess(0x0410, $false, $proc.Id)   # QUERY_INFORMATION | VM_READ
if ($h -eq [IntPtr]::Zero) { throw "OpenProcess failed (try running elevated)" }

$cur = [uint64]0
$regions = @()
$mbi = New-Object VM+MEMORY_BASIC_INFORMATION64
$sz = [System.Runtime.InteropServices.Marshal]::SizeOf($mbi)
while ($true) {
  $r = [VM]::VirtualQueryEx($h, [IntPtr]::new([int64]$cur), [ref]$mbi, [IntPtr]$sz)
  if ($r -eq [IntPtr]::Zero) { break }
  if ($mbi.State -eq 0x1000 -and $mbi.Protect -ne 0x01 -and $mbi.Protect -ne 0) {
    $mb = $mbi.RegionSize / 1MB
    if ($mb -ge $MinMB -and $mb -le $MaxMB) {
      $regions += [pscustomobject]@{ Base = [uint64]$mbi.BaseAddress; Size = [uint64]$mbi.RegionSize; Protect = $mbi.Protect }
    }
  }
  $next = [uint64]$mbi.BaseAddress + [uint64]$mbi.RegionSize
  if ($next -le $cur) { break }
  $cur = $next
}

Write-Host "$($regions.Count) candidate regions"
$i = 0
foreach ($rg in $regions) {
  $path = "$Out.$i.bin"
  $chunk = 4MB
  $left = [int64]$rg.Size
  $off = [uint64]$rg.Base
  $fs = [System.IO.File]::Create($path)
  $buf = New-Object byte[] $chunk
  $ok = $true
  while ($left -gt 0) {
    $want = [int]([Math]::Min([int64]$chunk, $left))
    $read = [IntPtr]::Zero
    $success = [VM]::ReadProcessMemory($h, [IntPtr]::new([int64]$off), $buf, [IntPtr]$want, [ref]$read)
    if (-not $success) { $ok = $false; break }
    $got = $read.ToInt64()
    $fs.Write($buf, 0, [int]$got)
    $off += [uint64]$got
    $left -= $got
    if ($got -le 0) { break }
  }
  $fs.Close()
  $len = (Get-Item $path).Length
  Write-Host ("  [{0}] base=0x{1:X} size={2:N0} protect=0x{3:X} -> {4} ({5:N0} bytes, rp={6})" -f $i, $rg.Base, $rg.Size, $rg.Protect, $path, $len, $ok)
  $i++
}
[VM]::CloseHandle($h) | Out-Null
Write-Host "done"
