@echo off
setlocal enabledelayedexpansion

echo ======================================================================
echo  Building Windows Installer for Comic Scroll Reader
echo ======================================================================

set "PROJECT_ROOT=%~dp0..\.."
cd /d "%PROJECT_ROOT%"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found. Please create one:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt pyinstaller
    exit /b 1
)

echo [1/3] Installing / Verifying requirements and PyInstaller...
call .venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller pillow

echo [2/3] Compiling standalone bundle with PyInstaller...
call .venv\Scripts\python.exe -m PyInstaller ^
    --distpath "build\pyinstaller_dist" ^
    --workpath "build\pyinstaller_build" ^
    -y ^
    "packaging\windows\comic-scroll-reader-win.spec"

if not exist "build\pyinstaller_dist\comic-scroll-reader\comic-scroll-reader.exe" (
    echo [ERROR] PyInstaller compilation failed.
    exit /b 1
)

echo [3/3] Compiling Setup Installer with Inno Setup...
set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "!ISCC_PATH!" (
    set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
)

where iscc >nul 2>&1
if %errorlevel% equ 0 (
    iscc "packaging\windows\installer.iss"
) else if exist "!ISCC_PATH!" (
    "!ISCC_PATH!" "packaging\windows\installer.iss"
) else (
    echo [WARNING] Inno Setup compiler (ISCC.exe) not found.
    echo Standalone application built successfully in:
    echo   build\pyinstaller_dist\comic-scroll-reader
    echo Install Inno Setup 6 to compile the setup wizard installer.
    exit /b 0
)

echo ======================================================================
echo  Windows build complete! Installer located in dist\
echo ======================================================================
