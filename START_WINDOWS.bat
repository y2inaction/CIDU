@echo off
title VCDP CIDU - Starting Server
color 0A
echo.
echo  ============================================
echo   VCDP CIDU - Climate Information Dissemination & Use
echo   FGN / IFAD-VCDP Programme
echo  ============================================
echo.
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not installed!
    echo  Download from: https://www.python.org/downloads/
    echo  Check "Add Python to PATH" during install.
    pause & exit /b 1
)
echo  [OK] Python found

if not exist "venv" (
    echo  [SETUP] Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate.bat

echo  [SETUP] Upgrading pip...
python -m pip install --upgrade pip --quiet

echo  [SETUP] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [ERROR] Dependency installation failed. See errors above.
    pause & exit /b 1
)
echo  [OK] Dependencies ready

set DATABASE_URL=sqlite:///vcdp_local.db
set FLASK_ENV=development
set NO_SCHEDULER=1

echo  [SETUP] Setting up database...
flask db upgrade >nul 2>&1
if errorlevel 1 (flask db init >nul 2>&1 && flask db migrate -m "init" >nul 2>&1 && flask db upgrade >nul 2>&1)
echo  [OK] Database ready
echo.
start "" http://localhost:5000
echo  ============================================
echo   Server running at: http://localhost:5000
echo   Login: npmu_admin / VCDP@Npmu2026!
echo   Press Ctrl+C to stop
echo  ============================================
echo.
python app.py
pause
