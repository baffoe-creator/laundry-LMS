# build_exe.ps1 — PowerShell-friendly PyInstaller wrapper (safe temp-file approach)
# Run from project root after activating the venv:
#    .\.venv\Scripts\Activate.ps1
#    powershell -ExecutionPolicy Bypass -File .\build_exe.ps1

$ErrorActionPreference = "Stop"

$EXE_NAME = "LaundryLMS"
$ENTRY = "auth.py"

if (-not (Test-Path $ENTRY)) {
    Write-Host "ERROR: $ENTRY not found. Run this from project root."
    exit 1
}

# Use venv pyinstaller if available
if (Test-Path ".\.venv\Scripts\pyinstaller.exe") {
    $pyinstaller = Join-Path ".\.venv\Scripts" "pyinstaller.exe"
} else {
    $pyinstaller = "pyinstaller"
}

# Create a temporary Python script to probe Qt platforms dir
$rand = Get-Random -Maximum 999999
$tmpPy = Join-Path $env:TEMP ("get_qt_dir_$rand.py")
$pySource = @'
import os
try:
    from PyQt5 import QtCore
    p = os.path.join(os.path.dirname(QtCore.__file__), "Qt", "plugins", "platforms")
    print(p)
except Exception:
    pass
'@

Set-Content -Path $tmpPy -Value $pySource -Encoding UTF8

# Run the probe
$qtPlatformDir = ""
try {
    $out = & python $tmpPy 2>$null
    if ($out) {
        $qtPlatformDir = $out.Trim()
    }
} finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $tmpPy
}

Write-Host "Detected Qt platforms dir: $qtPlatformDir"

# Base PyInstaller args
$baseArgs = @(
    '--onefile'
    '--windowed'
    "--name=$EXE_NAME"
    '--add-data', 'config.json;.'
    '--add-data', 'invoices;invoices'
    '--add-data', 'backups;backups'
    '--hidden-import=reportlab.rl_config'
)

# If qwindows.dll present, add binary
if ($qtPlatformDir -and (Test-Path (Join-Path $qtPlatformDir 'qwindows.dll'))) {
    $qwd = Join-Path $qtPlatformDir 'qwindows.dll'
    Write-Host "Including qwindows.dll from $qwd"
    $args = $baseArgs + @('--add-binary', "$qwd;platforms", $ENTRY)
} else {
    if ($qtPlatformDir) {
        Write-Host "qwindows.dll not found inside detected Qt platform dir: $qtPlatformDir"
    } else {
        Write-Host "Qt platforms dir not detected; building without qwindows.dll"
    }
    $args = $baseArgs + @($ENTRY)
}

# Run PyInstaller
Write-Host "Running PyInstaller..."
Write-Host "$pyinstaller $($args -join ' ')"
& $pyinstaller @args

if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Host "Build finished. Check the dist folder for $EXE_NAME.exe"