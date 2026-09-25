@echo off
title Check SHADER7 AI model files
"%~dp0app\python\python.exe" -B "%~dp0app\verify_models.py"
pause
