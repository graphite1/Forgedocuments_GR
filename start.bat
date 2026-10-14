@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
if exist ".venv\Scripts\python.exe" goto launch
call setup.bat
if errorlevel 1 goto failed
:launch
".venv\Scripts\python.exe" "app.py" %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo Startup failed. Please check the error message above.
pause
exit /b 1
