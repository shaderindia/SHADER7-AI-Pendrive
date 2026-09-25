@echo off
title Install SHADER7 AI to PC
echo SHADER7 AI - Install application and models to your Windows user folder.
echo Chats are stored in LocalAI_Workspace. Shared Ollama models are preserved.
echo.
if not exist "%~dp0app\python\python.exe" (
    echo Portable Python is missing. Build the USB drive first.
    pause
    exit /b 1
)
"%~dp0app\python\python.exe" -B "%~dp0app\server.py" --install
set "result=%errorlevel%"
if not "%result%"=="0" echo Installation did not finish. Read the error above.
pause
exit /b %result%
