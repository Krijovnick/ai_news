@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Запуск Google News + Hacker News дайджеста...
echo.
python main.py --google-hn
echo.
pause
