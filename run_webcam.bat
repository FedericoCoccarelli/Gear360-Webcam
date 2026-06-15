@echo off
echo ===================================================
echo   Gear 360 Webcam Launcher
echo ===================================================
echo Checking and installing python dependencies...
python -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to verify/install python dependencies.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Starting Gear 360 Webcam...
python gear360_webcam.py
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Program terminated unexpectedly.
    pause
)
