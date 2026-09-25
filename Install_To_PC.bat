@echo off
title Install SHADER7 AI to PC
echo SHADER7 AI - Install application and models to your Windows user folder.
echo Chats are stored in LocalAI_Workspace. Shared Ollama models are preserved.
echo.
"%~dp0app\python\python.exe" -B "%~dp0app\server.py" --install
if errorlevel 1 echo Installation did not finish. Read the error above.
pause
