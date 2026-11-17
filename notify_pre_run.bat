@echo off
"%~dp0.venv\Scripts\python.exe" "%~dp0notify_pre_run.py"
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0notify_pre_run.ps1"
