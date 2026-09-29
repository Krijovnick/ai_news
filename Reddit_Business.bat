@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Запуск Reddit Business дайджеста...
echo.
python main.py --reddit-business
echo.
pause
