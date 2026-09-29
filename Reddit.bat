@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Запуск Reddit дайджеста...
echo.
python main.py --reddit-only
echo.
pause
