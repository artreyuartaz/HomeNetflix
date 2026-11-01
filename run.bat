@echo off
cd /d "%~dp0"

rem Find a working Python (the Microsoft Store stub fails the --version check)
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo.
    echo [ERROR] Python is not installed ^(or only the Microsoft Store stub was found^).
    echo.
    echo   1. Download Python 3.10+ from https://www.python.org/downloads/
    echo   2. In the installer, tick "Add python.exe to PATH"
    echo   3. Close this window and run run.bat again
    echo.
    pause
    exit /b 1
)

rem Remove a broken venv left by a failed earlier run
if exist .venv if not exist .venv\Scripts\python.exe rmdir /s /q .venv

if not exist .venv\Scripts\python.exe (
    echo Creating virtual environment...
    %PY% -m venv .venv
    if errorlevel 1 goto :fail
    echo Installing dependencies...
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 (
        rmdir /s /q .venv
        goto :fail
    )
)

.venv\Scripts\python.exe main.py
pause
exit /b 0

:fail
echo.
echo [ERROR] Setup failed. See the messages above.
pause
exit /b 1
