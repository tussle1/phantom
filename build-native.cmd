@echo off
cd /d "%~dp0"
rem Install dependencies first: py -3 -m pip install pyinstaller -r requirements-gui.txt
py -3 -m PyInstaller --clean --onefile --windowed --add-data "native/assets;native/assets" --name phantom-native phantom.py
exit /b %ERRORLEVEL%
