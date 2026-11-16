@echo off
cd /d "%~dp0"
rem Install the optional build dependency first: py -3 -m pip install pyinstaller
py -3 -m PyInstaller --clean --onefile --name phantom-native phantom.py
exit /b %ERRORLEVEL%
