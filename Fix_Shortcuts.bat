@echo off
title Repair SHADER7 AI launchers
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Repair_Launchers.ps1" -AppDir "%~dp0"
if errorlevel 1 echo Launcher repair failed. Read the error above.
echo.
pause
