@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".source-venv\Scripts\python.exe" goto missing
".source-venv\Scripts\python.exe" -B source_bootstrap.py run %*
exit /b %errorlevel%
:missing
echo First run setup_source.bat. See SOURCE_README_JA.txt.
exit /b 1
