@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "src\biduan_pet.py"
    exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py -V:Astral/CPython3.12 "src\biduan_pet.py"
    if %ERRORLEVEL%==0 exit /b 0
    py "src\biduan_pet.py"
    exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
    python "src\biduan_pet.py"
    exit /b %ERRORLEVEL%
)

echo 未找到可用的 Python。请先安装 Python 3.10 或更高版本。
pause
