@echo off
title Astraeus NOC — ISRO MPLS Predictive Copilot
color 0B
echo.
echo  ==========================================
echo   ASTRAEUS NOC — AIR-GAPPED MPLS COPILOT
echo   ISRO Ground Network Operations System
echo  ==========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

:: Install dependencies if needed
echo [*] Checking dependencies...
pip install -q fastapi uvicorn[standard] pydantic numpy

echo [*] Starting Astraeus NOC Backend...
echo [*] Dashboard URL: http://localhost:8000
echo.
echo  Press Ctrl+C to stop the server.
echo.

:: Run from the ISRO root directory so imports work
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload

pause
