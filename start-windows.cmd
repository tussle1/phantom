@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo 64-bit Python 3.11 or newer is required.
  pause
  exit /b 1
)
py -3 phantom.py %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" pause
exit /b %RESULT%
