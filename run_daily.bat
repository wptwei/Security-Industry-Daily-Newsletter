@echo off
rem Daily security intel brief runner (called by Windows Task Scheduler)
rem Runs the pipeline once, appends logs to run_log.txt next to this script.

cd /d "%~dp0"
echo. >> "%~dp0run_log.txt"
echo ====== run start ====== >> "%~dp0run_log.txt"
"C:\vscode project\.venv\Scripts\python.exe" -m app.main --once >> "%~dp0run_log.txt" 2>&1
echo ====== run done ====== >> "%~dp0run_log.txt"
