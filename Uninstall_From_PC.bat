@echo off
title Uninstall SHADER7 AI from PC
powershell.exe -NoProfile -File "%~dp0Uninstall_SHADER7_AI.ps1"
if errorlevel 1 echo Uninstall did not finish. Read the error above.
pause
