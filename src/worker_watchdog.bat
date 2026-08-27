@echo off
rem Nerpatham Hub watchdog - restarts the worker if it ever exits.
cd /d D:\IslamicResourceHub
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
:loop
"D:\IslamicResourceHub\.venv\Scripts\python.exe" src\run_worker.py >> logs\service_out.log 2>&1
echo [%date% %time%] worker exited, restarting in 15s >> logs\service_out.log
timeout /t 15 /nobreak >nul
goto loop
