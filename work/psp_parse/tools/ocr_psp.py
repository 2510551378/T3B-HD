"""ocr_psp.py -- OCR the newest PPSSPP screenshot (Windows.Media.Ocr via PowerShell helper).

    python tools/ocr_psp.py [image]

Prints the recognised text so the driver of an automated run can decide the next key.
"""
import os
import subprocess
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
SHOT = os.path.join(ROOT, "PSP", "memstick", "PSP", "SCREENSHOT")

PS = r'''
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($t, $rt) { $m = $asTaskGeneric.MakeGenericMethod($rt); $nt = $m.Invoke($null, @($t)); $nt.Wait(-1) | Out-Null; $nt.Result }
[Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType=WindowsRuntime] | Out-Null
$path = "__PATH__"
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync(0)) ([Windows.Storage.Streams.IRandomAccessStream])
$dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$res = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
foreach ($line in $res.Lines) { $line.Text }
'''


def newest():
    fs = [os.path.join(SHOT, f) for f in os.listdir(SHOT)] if os.path.isdir(SHOT) else []
    fs = [f for f in fs if f.endswith(".jpg")]
    return max(fs, key=os.path.getmtime) if fs else None


def ocr(path):
    script = PS.replace("__PATH__", path)
    r = subprocess.run(["pwsh", "-NoProfile", "-Command", script],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "").strip() + (("\n[stderr] " + r.stderr.strip()) if r.returncode else "")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    path = sys.argv[1] if len(sys.argv) > 1 else newest()
    if not path or not os.path.exists(path):
        print("no screenshot found")
        return
    print(f"# {os.path.basename(path)}")
    print(ocr(path))


if __name__ == "__main__":
    main()
