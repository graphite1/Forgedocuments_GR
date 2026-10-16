@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
if defined FORGE_SOURCE_PYTHON goto specified
py -3.14 -c "import sys,struct;assert sys.version_info[:2]==(3,14) and struct.calcsize('P')==8" >nul 2>&1
if not errorlevel 1 goto launcher
python -c "import sys,struct;assert sys.version_info[:2]==(3,14) and struct.calcsize('P')==8" >nul 2>&1
if not errorlevel 1 goto python
 echo Python 3.14 x64 is required. See SOURCE_README_JA.txt.
exit /b 1
:specified
"%FORGE_SOURCE_PYTHON%" -B source_bootstrap.py setup
exit /b %errorlevel%
:launcher
py -3.14 -B source_bootstrap.py setup
exit /b %errorlevel%
:python
python -B source_bootstrap.py setup
exit /b %errorlevel%
