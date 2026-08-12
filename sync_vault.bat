@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python compress_and_sync.py
echo.
echo Press any key to exit...
pause >nul
