@echo off
start "AI News Web" cmd /d /c "cd /d "%~dp0." && chcp 65001 >nul && echo Веб-интерфейс http://127.0.0.1:5050 && echo Остановка: Ctrl+C && python web.py || pause"
exit
