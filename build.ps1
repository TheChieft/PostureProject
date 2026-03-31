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
    Write-Host "=== PyInstaller succeeded ===" -ForegroundColor Green
    Write-Host ("  Exe    : dist\PostureProject\PostureProject.exe") -ForegroundColor White
    Write-Host ("  Size   : {0:F0} MB" -f $size) -ForegroundColor White
    Write-Host ""

    # ── Inno Setup installer ──────────────────────────────────────
    $iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (Test-Path $iscc) {
        Write-Host "Building installer with Inno Setup..." -ForegroundColor Yellow
        & $iscc "installer.iss"
        if ($LASTEXITCODE -eq 0) {
            $setup = Get-Item "dist\PostureProject-Setup-*.exe" -ErrorAction SilentlyContinue
            if ($setup) {
                $setupMB = $setup.Length / 1MB
                Write-Host ""
                Write-Host "=== Installer built ===" -ForegroundColor Green
                Write-Host ("  Installer : " + $setup.Name) -ForegroundColor White
                Write-Host ("  Size      : {0:F0} MB" -f $setupMB) -ForegroundColor White
            }
        } else {
            Write-Host "Inno Setup failed — installer not created." -ForegroundColor Red
        }
    } else {
        Write-Host "Inno Setup not found — skipping installer." -ForegroundColor DarkYellow
        Write-Host "Install from: https://jrsoftware.org/isinfo.php" -ForegroundColor Gray
    }

    Write-Host ""
    Write-Host "To run directly:" -ForegroundColor Cyan
    Write-Host "  .\dist\PostureProject\PostureProject.exe" -ForegroundColor White
} else {
    Write-Host "=== Build FAILED ===" -ForegroundColor Red
    Write-Host "Check the output above for errors." -ForegroundColor Yellow
    exit 1
}
