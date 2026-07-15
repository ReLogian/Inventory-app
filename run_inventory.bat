@echo off
setlocal

set "APP_DIR=%~dp0"
set "SCRIPT=%APP_DIR%src\inventorymgmt.py"

if exist "%APP_DIR%python\pythonw.exe" (
    start "" "%APP_DIR%python\pythonw.exe" "%SCRIPT%"
    exit /b
)

if exist "%APP_DIR%python\python.exe" (
    "%APP_DIR%python\python.exe" "%SCRIPT%"
    exit /b
)

where pythonw >nul 2>nul
if %errorlevel% equ 0 (
    start "" pythonw "%SCRIPT%"
    exit /b
)

python "%SCRIPT%"
