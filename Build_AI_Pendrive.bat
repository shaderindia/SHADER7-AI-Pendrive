@echo off
title SHADER7 AI - Build Your AI Pendrive
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build_AI_Pendrive.ps1" %*
set "result=%errorlevel%"
if not "%result%"=="0" (
    echo.
    echo ===============================================================
    echo Build did not complete. Please check the messages above.
    echo ===============================================================
)
echo.
pause
exit /b %result%
