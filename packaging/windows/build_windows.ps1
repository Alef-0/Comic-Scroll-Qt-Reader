# PowerShell script to build Comic Scroll Reader on Windows
$ErrorActionPreference = "Stop"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host " Building Windows Installer for Comic Scroll Reader" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python.exe"
}

Write-Host "[1/3] Verifying dependencies..." -ForegroundColor Yellow
& $Python -m pip install -r requirements.txt pyinstaller

Write-Host "[2/3] Compiling standalone bundle with PyInstaller..." -ForegroundColor Yellow
& $Python -m PyInstaller `
    --distpath "build\pyinstaller_dist" `
    --workpath "build\pyinstaller_build" `
    -y `
    "packaging\windows\comic-scroll-reader-win.spec"

$ExePath = "build\pyinstaller_dist\comic-scroll-reader\comic-scroll-reader.exe"
if (-not (Test-Path $ExePath)) {
    Write-Error "PyInstaller compilation failed; executable not found at $ExePath"
    exit 1
}

Write-Host "[3/3] Compiling Inno Setup installer..." -ForegroundColor Yellow
$Iscc = Get-Command "iscc" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $Iscc) {
    $Candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )
    foreach ($cand in $Candidates) {
        if (Test-Path $cand) {
            $Iscc = $cand
            break
        }
    }
}

if ($Iscc) {
    & $Iscc "packaging\windows\installer.iss"
    Write-Host "Windows setup installer built successfully in dist\" -ForegroundColor Green
} else {
    Write-Warning "Inno Setup compiler (ISCC.exe) not found. Standalone bundle available in build\pyinstaller_dist\comic-scroll-reader"
}
