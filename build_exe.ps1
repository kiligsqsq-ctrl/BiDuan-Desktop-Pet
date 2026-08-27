$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath ".\.venv\Scripts\python.exe")) {
    py -V:Astral/CPython3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Failed to create Python environment." }
}

.\.venv\Scripts\python.exe -m pip install --upgrade pyinstaller pillow pystray
if ($LASTEXITCODE -ne 0) { throw "Failed to install build dependencies." }

.\.venv\Scripts\python.exe .\tools\build_icon.py
if ($LASTEXITCODE -ne 0) { throw "Failed to build application icons." }

.\.venv\Scripts\python.exe -m unittest discover -s .\tests
if ($LASTEXITCODE -ne 0) { throw "Tests failed." }

.\.venv\Scripts\python.exe -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onefile `
    --name BiDuan `
    --icon ".\assets\branding\biduan.ico" `
    --version-file ".\installer\version_info.txt" `
    --hidden-import "pystray._win32" `
    --add-data ".\assets\branding;assets\branding" `
    --add-data ".\assets\animations;assets\animations" `
    .\src\biduan_pet.py
if ($LASTEXITCODE -ne 0) { throw "Build failed. Make sure dist\BiDuan.exe is not running." }

Write-Host ""
Write-Host "Build complete: dist\BiDuan.exe"
