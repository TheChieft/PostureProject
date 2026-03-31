# build.ps1
# ---------
# Builds PostureProject.exe using PyInstaller.
# Run from the project root in PowerShell:
#   .\build.ps1
#
# Output: dist\PostureProject\PostureProject.exe

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== PostureProject Build ===" -ForegroundColor Cyan
Write-Host ""

# Verify Python 3.11 x64
$pyver = py -3.11 -c "import sys; print(sys.version)"
Write-Host "Python: $pyver" -ForegroundColor Gray

# Verify model file exists (required to bundle it)
if (-not (Test-Path "pose_landmarker_lite.task")) {
    Write-Host ""
    Write-Host "ERROR: pose_landmarker_lite.task not found." -ForegroundColor Red
    Write-Host "Run first:  py -3.11 download_model.py" -ForegroundColor Yellow
    exit 1
}

# Install / update PyInstaller
Write-Host "Checking PyInstaller..." -ForegroundColor Gray
py -3.11 -m pip install pyinstaller --quiet

# Clean previous builds
Write-Host "Cleaning previous build..." -ForegroundColor Gray
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist")  { Remove-Item -Recurse -Force "dist" }

# Build
Write-Host ""
Write-Host "Building... (this takes 2-5 minutes)" -ForegroundColor Yellow
Write-Host ""
py -3.11 -m PyInstaller PostureProject.spec --noconfirm

# Result
Write-Host ""
if (Test-Path "dist\PostureProject\PostureProject.exe") {
    $size = (Get-ChildItem -Recurse "dist\PostureProject" |
             Measure-Object -Property Length -Sum).Sum / 1MB
    Write-Host "=== Build succeeded ===" -ForegroundColor Green
    Write-Host ""
    Write-Host ("  Output : dist\PostureProject\PostureProject.exe") -ForegroundColor White
    Write-Host ("  Size   : {0:F0} MB (full folder)" -f $size) -ForegroundColor White
    Write-Host ""
    Write-Host "To run:" -ForegroundColor Cyan
    Write-Host "  .\dist\PostureProject\PostureProject.exe" -ForegroundColor White
    Write-Host "  .\dist\PostureProject\PostureProject.exe --preview --bar-x 1920" -ForegroundColor White
    Write-Host ""
    Write-Host "To distribute: copy the entire dist\PostureProject\ folder." -ForegroundColor Gray
} else {
    Write-Host "=== Build FAILED ===" -ForegroundColor Red
    Write-Host "Check the output above for errors." -ForegroundColor Yellow
    exit 1
}
