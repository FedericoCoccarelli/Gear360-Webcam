@echo off
setlocal

echo ===================================================
echo   Gear 360 Webcam Launcher
echo ===================================================

:: Percorso del venv nella cartella del progetto
set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"

:: --- Ricrea il venv se mancante o rotto (python.exe o pip.exe assenti) ---
if not exist "%VENV_PYTHON%" goto :create_venv
if not exist "%VENV_PIP%"    goto :recreate_venv
echo [SETUP] Virtual environment OK.
goto :install_deps

:recreate_venv
echo [SETUP] Virtual environment is incomplete (pip missing). Recreating...
rmdir /s /q "%VENV_DIR%"

:create_venv
echo [SETUP] Creating virtual environment...
python -m venv --upgrade-deps "%VENV_DIR%"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to create virtual environment.
    echo         Make sure Python is installed and in PATH.
    pause
    exit /b 1
)
echo [SETUP] Virtual environment created at: %VENV_DIR%

:install_deps
:: --- Installa/aggiorna i requirements nel venv ---
echo [SETUP] Installing/verifying dependencies...
"%VENV_PYTHON%" -m pip install -q -r "%SCRIPT_DIR%requirements.txt"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install dependencies from requirements.txt.
    pause
    exit /b 1
)
echo [SETUP] Dependencies OK.

:: --- Lancia il programma con il Python del venv ---
echo.
echo Starting Gear 360 Webcam...
echo.
"%VENV_PYTHON%" "%SCRIPT_DIR%gear360_webcam.py"

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Program terminated with an error (exit code %ERRORLEVEL%).
    pause
)

endlocal
