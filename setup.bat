@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
py -3 -c "import sys;assert sys.version_info >= (3,11)" >nul 2>&1
if not errorlevel 1 goto use_py
python -c "import sys;assert sys.version_info >= (3,11)" >nul 2>&1
if not errorlevel 1 goto use_python
echo Python 3.11 or newer is required.
echo Install Python for Windows:
echo https://www.python.org/downloads/windows/
echo Enable the option: Add python.exe to PATH
pause
exit /b 1
:use_py
py -3 bootstrap.py
exit /b %errorlevel%
:use_python
python bootstrap.py
exit /b %errorlevel%
