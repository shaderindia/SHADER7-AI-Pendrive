@echo off
if not exist "%~dp0app\python\pythonw.exe" (
    echo Missing portable Python. Restore the app folder and retry.
    pause
    exit /b 1
)
start "SHADER7 AI CPU" "%~dp0app\python\pythonw.exe" -B "%~dp0app\server.py" --cpu
