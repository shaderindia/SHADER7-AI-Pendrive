@echo off
title SHADER7 AI - Build Your AI Pendrive
setlocal enabledelayedexpansion

:: Check for administrative privileges (optional, but helpful for disk access)
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Note: Running without elevation. If writing to protected drives fails,
    echo right-click this script and choose "Run as administrator".
    echo.
)

:: Launch the PowerShell installer engine
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build_AI_Pendrive.ps1"
if %errorlevel% neq 0 (
    echo.
    echo ===============================================================
    echo Build did not complete. Please check the messages above.
    echo ===============================================================
)
echo.
pause
