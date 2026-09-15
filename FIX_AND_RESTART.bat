@echo off
title VCDP CIDU - Fix & Restart
color 0E
echo.
echo  ============================================
echo   VCDP CIDU - Repair Tool
echo   Removes broken virtual environment and
echo   reinstalls everything fresh.
echo  ============================================
echo.
echo  This will delete the "venv" folder and
echo  recreate it with the corrected packages.
echo.
pause

if exist "venv" (
    echo  [CLEAN] Removing old virtual environment...
    rmdir /s /q venv
)

echo  [SETUP] Running START_WINDOWS.bat...
call START_WINDOWS.bat
