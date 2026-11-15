@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 or newer is required. Install Python with the Windows launcher.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:8765 in your browser after startup.
py -3 companion.py
pause
